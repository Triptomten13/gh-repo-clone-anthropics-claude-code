"""Public, unauthenticated endpoints — safe to expose on the internet.

* GET /ready            — 200 only when the database answers and its schema is at the newest migration (load balancers)
* GET /api/version      — version and build commit
* GET /api/status       — component and feature status for the public status page: states only, no host names,
                          paths, keys, model files, user data or error text
* POST /api/demo/session — public demo servers only: a temporary visitor session (see app/demo/public.py)
* GET /api/demo/catalog  — the approved sample workflows (signed-in)
GET /health (liveness) lives in main.py.
"""
from __future__ import annotations

import os
import subprocess
import time
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..demo import public as demo
from ..models import User
from ..security.auth import current_user

router = APIRouter()
STARTED = time.time()
VERSION = "0.3.0"


@lru_cache(maxsize=1)
def _commit() -> str:
    """Build commit: GIT_SHA (image build arg) or the platform's variable (Render: RENDER_GIT_COMMIT), else the
    checkout's HEAD; 'unknown' otherwise."""
    for var in ("GIT_SHA", "RENDER_GIT_COMMIT", "SOURCE_COMMIT"):
        v = os.getenv(var, "").strip()
        if v and v != "unknown":
            return v[:12]
    try:
        out = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=Path(__file__).resolve().parents[2],  # noqa: S603,S607 — fixed argv
                             capture_output=True, text=True, timeout=3)
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


@lru_cache(maxsize=1)
def _head() -> str | None:
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        return ScriptDirectory.from_config(Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))).get_current_head()
    except Exception:  # noqa: BLE001 — alembic files missing from a slim image
        return None


def _migration_state(db: Session) -> tuple[str, str | None, str | None]:
    """(state, current, head): 'current' | 'behind' | 'unmanaged' (tables created without Alembic, e.g. tests)."""
    head = _head()
    if head is None:
        return "unknown", None, None
    try:
        cur = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:  # noqa: BLE001
        db.rollback()
        return "unmanaged", None, head
    return ("current" if cur == head else "behind"), cur, head


@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    t0 = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 — never leak the driver error to the public
        return JSONResponse({"ready": False, "database": "unreachable"}, status_code=503)
    mig, _, _ = _migration_state(db)
    ok = mig in ("current", "unmanaged", "unknown")
    return JSONResponse({"ready": ok, "database": "ok", "db_ms": round((time.perf_counter() - t0) * 1000, 1), "schema": mig},
                        status_code=200 if ok else 503)


@router.get("/api/version")
def version():
    s = get_settings()
    return {"name": s.company_name, "version": VERSION, "commit": _commit(), "environment": _env_label()}


def _env_label() -> str:
    if demo.enabled():
        return "public-demo"
    return {"production": "production", "staging": "staging", "test": "test"}.get(get_settings().env, "development")


@router.get("/api/status")
def status(db: Session = Depends(get_db)):
    from ..governance import core as gov

    comps: list[dict[str, Any]] = [{"id": "backend", "name": "Backend API", "status": "operational", "kind": "core"}]
    t0 = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db.rollback()
        db_ok = False
    db_ms = round((time.perf_counter() - t0) * 1000, 1)
    mig, _, _ = _migration_state(db) if db_ok else ("unknown", None, None)
    comps.append({"id": "database", "name": "Database", "kind": "core", "status": "operational" if db_ok and mig != "behind" else "failed",
                  "detail": (f"responds in {db_ms} ms; schema {mig}" if db_ok else "not reachable")})
    agents_active = 0
    kill = False
    st: dict[str, Any] = {"offline_mode": False, "external_allowed": False}
    models: dict[str, Any] = {}
    if db_ok:
        from ..daemon import library
        from ..daemon import state as dstate
        from ..models import Agent

        agents_active = db.scalar(select(func.count(Agent.id)).where(Agent.status == "active")) or 0
        kill = gov.kill_switch_engaged(db)
        st = dstate.load(db)
        models = {slot: bool(library.resolve(db, slot)) for slot in ("chat", "eco", "deep", "embedding")}
    comps.append({"id": "agents", "name": "Agent runtime", "kind": "core",
                  "status": "paused" if kill else ("operational" if agents_active else "failed"),
                  "detail": "emergency stop engaged — new tasks are refused" if kill else f"{agents_active} agents registered and active"})
    n_models = sum(1 for v in models.values() if v)
    comps.append({"id": "local_models", "name": "Local AI models", "kind": "optional",
                  "status": "operational" if models.get("chat") else "not_configured",
                  "detail": f"{n_models} model slot(s) active" if n_models else
                  "no local model installed on this server — model-backed answers are unavailable; rule-based and retrieval features work"})
    s = get_settings()
    ext = ("disabled" if st.get("offline_mode") else "operational" if (s.anthropic_api_key_present and st.get("external_allowed")) else "not_configured")
    comps.append({"id": "external_ai", "name": "External AI providers", "kind": "optional", "status": ext,
                  "detail": {"disabled": "offline mode — no external AI service is ever called" + (" (always, on the public demo)" if demo.enabled() else ""),
                             "operational": "an external provider is configured", "not_configured": "no provider key configured"}[ext]})
    comps.append({"id": "research", "name": "Internet research (official APIs)", "kind": "optional",
                  "status": "disabled" if st.get("offline_mode") else "operational",
                  "detail": "offline mode" if st.get("offline_mode") else "keyless official sources; keyed ones need configuration"})
    core_ok = all(c["status"] == "operational" for c in comps if c["kind"] == "core")
    return {"name": s.company_name, "version": VERSION, "commit": _commit(), "environment": _env_label(), "demo_mode": demo.enabled(),
            "overall": "operational" if core_ok else ("degraded" if db_ok else "failed"),
            "checked_at": datetime.now(UTC).isoformat(), "uptime_s": int(time.time() - STARTED), "components": comps,
            "features": _features(models, st, kill)}


def _features(models: dict[str, Any], st: dict[str, Any], kill: bool) -> list[dict[str, str]]:
    """What a visitor can actually use here. Statuses: available · demo (works on sample data) · config_required ·
    unavailable · planned. Nothing is listed as available that this server cannot do."""
    d = demo.enabled()
    has_model = bool(models.get("chat"))
    data = "demo" if d else "available"
    return [
        {"name": "Agent directory, permissions and policies", "status": data, "where": "/agents"},
        {"name": "G-sus orchestration (plan → delegate → verify)", "status": data, "where": "/chamber",
         "note": "sample workflows only on the public demo" if d else ""},
        {"name": "Human approval checkpoints (LEVEL 4–5)", "status": data, "where": "/approvals",
         "note": "visible; deciding requires an approver account" if d else ""},
        {"name": "Knowledge Vault search with citations and access control", "status": data, "where": "/archive"},
        {"name": "Deterministic answers and routing plans", "status": data, "where": "/control"},
        {"name": "Execution traces and replay", "status": data, "where": "/governance#runs"},
        {"name": "Tamper-evident audit trail", "status": data, "where": "/governance#audit"},
        {"name": "Offline evaluation suites and release gates", "status": data, "where": "/governance#gates"},
        {"name": "Cost and resource dashboards", "status": data, "where": "/daemon", "note": "sample/measured values, labelled"},
        {"name": "Model-backed chat and drafting", "status": "available" if has_model or not st.get("offline_mode") else "unavailable",
         "note": "" if has_model else "no AI model on this server"},
        {"name": "Document upload", "status": "unavailable" if d else "available", "note": "disabled for public visitors" if d else ""},
        {"name": "Internet research", "status": "unavailable" if st.get("offline_mode") else "available"},
        {"name": "External actions (publishing, purchases, messages)", "status": "unavailable" if d else "config_required",
         "note": "never from the public demo" if d else "needs connector credentials and a human approval per action"},
        {"name": "Single sign-on (OIDC/SAML)", "status": "planned"},
    ] + ([{"name": "Emergency stop engaged", "status": "unavailable", "note": "agent work is paused"}] if kill else [])


# ------------------------------------------------------------------ public demo
def _client(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() or (request.client.host if request.client else "unknown"))[:64]


@router.post("/api/demo/session")
def demo_session(request: Request, db: Session = Depends(get_db)):
    if not demo.enabled():
        raise HTTPException(404, "this server is not a public demo")
    return demo.create_session(db, _client(request))


@router.get("/api/demo/catalog")
def demo_catalog(db: Session = Depends(get_db), user: User = Depends(current_user)):
    from ..governance import usage

    left = None
    if demo.is_demo_user(user):
        left = max(0, demo.actions_per_session() - int(usage.used(db, f"demo:{user.email}")))
    return {"demo_mode": demo.enabled(), "workflows": demo.CATALOG, "actions_left": left,
            "reset_hours": demo.reset_hours() if demo.enabled() else None,
            "labels": {"LIVE DATA": "read from this server's database", "DEMO DATA": "synthetic sample records",
                       "SIMULATED OUTPUT": "not produced by a model or tool — never shown as if it were",
                       "CONNECTED SERVICE": "a service this server actually reached",
                       "UNAVAILABLE SERVICE": "not configured or disabled here"}}
