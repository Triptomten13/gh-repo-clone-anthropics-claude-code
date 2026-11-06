"""PUBLIC DEMO MODE (`DEMO_MODE=1`) — a safe public playground running the REAL application.

The public demo is a SEPARATE deployment of the same code with its own database: it never shares a database,
credentials or models with the private Control Center. On a demo server:

* Anyone may start a temporary demo session (no account): a throw-away user with the `demo` role — read access to
  sample data, the sample Knowledge Vault (PUBLIC/INTERNAL only), runs, policies, approvals and audit records, and the
  right to run the APPROVED SAMPLE WORKFLOWS below. No approvals, no tools, no settings, no uploads, no admin.
* G-sus runs are limited to the catalog objectives (checked by the backend, not the page); every session has an action
  budget; session creation is rate limited per client and globally.
* Offline mode is forced on: no external AI provider, research API or paid service is ever called, whatever the
  settings say — nobody's money can be spent from the public internet.
* First-run setup is disabled (nobody can claim the administrator account through the browser).
* A visitor sees only their own runs. All data is synthetic sample data or the platform's own documentation.
* The whole demo database is reset every DEMO_RESET_HOURS (default 6) and reseeded — temporary data does not pile up.
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..security.ratelimit import SlidingWindow

log = logging.getLogger(__name__)
SAMPLE_DIR = Path(__file__).parent / "sample_vault"
SAMPLE_COLLECTION = "sample-vault"


def enabled() -> bool:
    return os.getenv("DEMO_MODE", "").strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def session_minutes() -> int:
    return _int("DEMO_SESSION_TTL_MIN", 120)


def actions_per_session() -> int:
    return _int("DEMO_ACTIONS_PER_SESSION", 30)


def reset_hours() -> int:
    return _int("DEMO_RESET_HOURS", 6)


# Approved sample workflows. `kind` decides which REAL endpoint the page calls; G-sus objectives are enforced here.
CATALOG: list[dict[str, Any]] = [
    {"key": "evaluate", "kind": "gsus", "title": "Evaluate a sample product",
     "objective": "Evaluate the winter commuter pannier and create brand concepts", "mode": "gsus",
     "shows": "G-sus plans the work, delegates to the CEO agent and the creative council (several agents), compares the "
              "results and verifies them. Real agents and orchestration on sample products; scoring is heuristic — no AI "
              "model is used on this server.", "expect": "completed"},
    {"key": "risk", "kind": "gsus", "title": "Risk review with contradictions",
     "objective": "Evaluate the magnetic LED reading lamp", "mode": "watchman",
     "shows": "The Watchman mode adds a risk review; G-sus reports a contradiction between the agents' findings instead "
              "of hiding it.", "expect": "completed"},
    {"key": "approval", "kind": "gsus", "title": "Request a product launch (needs a human)",
     "objective": "Launch the hand-crank emergency radio", "mode": "gsus",
     "shows": "A launch is a LEVEL 4 action: the run stops at an approval checkpoint. Your demo session cannot approve it "
              "— the backend refuses, and nothing is launched.", "expect": "waiting_for_approval"},
    {"key": "archive", "kind": "gsus", "title": "Ask the sample Knowledge Vault",
     "objective": "How are consequential actions approved?", "mode": "archivist",
     "shows": "Retrieval over the sample vault (the platform's own documentation) with citations. A RESTRICTED sample "
              "memo exists too — your session is not allowed to read it, so it is filtered out before ranking.",
     "expect": "completed"},
    {"key": "calc", "kind": "ask", "title": "Deterministic answer (no model)", "question": "What is 25% of 480?",
     "shows": "The orchestrator recognises arithmetic and solves it exactly — no model call, with an execution trace.",
     "expect": "answered"},
    {"key": "routing", "kind": "plan", "title": "Model routing decision (dry run)",
     "question": "Summarise the latest research on quantization",
     "shows": "How the router would solve a request and why — strategy, tier and exclusions — without running anything.",
     "expect": "planned"},
    {"key": "evals", "kind": "evals", "title": "Run the offline evaluation suites",
     "shows": "The same suites that gate prompt and model releases: planner, routing, injection detection, anti-generic "
              "gate, retrieval grounding.", "expect": "scores"},
    {"key": "denied", "kind": "tool", "title": "Use a tool without a grant", "tool": "calc", "args": {"expression": "6*7"},
     "shows": "Tools are deny-by-default. Your session has no tool permission, so the Tool Gateway refuses — the refusal "
              "is the result.", "expect": "403"},
]
GSUS_OBJECTIVES = {(c["objective"].strip().lower(), c["mode"]) for c in CATALOG if c["kind"] == "gsus"}


def is_demo_user(user: Any) -> bool:
    return getattr(user, "role", None) == "demo"


def check_gsus(user: Any, objective: str, mode: str) -> None:
    """A demo session may start only the approved sample G-sus workflows (server-side check)."""
    from fastapi import HTTPException

    if is_demo_user(user) and (objective.strip().lower(), mode) not in GSUS_OBJECTIVES:
        raise HTTPException(403, "the public demo runs the approved sample workflows only (see Demo Center)")


def take_action(db: Session, user: Any) -> None:
    """Per-session action budget (atomic counter). Raises 429 when used up."""
    if not is_demo_user(user):
        return
    from fastapi import HTTPException

    from ..governance import usage

    if not usage.take(db, f"demo:{user.email}", actions_per_session(), 1, "day"):
        db.rollback()
        raise HTTPException(429, f"this demo session has used its {actions_per_session()} actions — start a new session later")
    db.commit()  # counted at once and in its own commit: traces open their own transaction next (SQLite lock order)


# ------------------------------------------------------------------ sessions
_per_client = SlidingWindow()
_total = SlidingWindow()


def reset_limits() -> None:
    global _per_client, _total
    _per_client, _total = SlidingWindow(), SlidingWindow()


def create_session(db: Session, client: str) -> dict[str, Any]:
    """A throw-away visitor account. Limits: DEMO_SESSIONS_PER_CLIENT_HOUR per client address (best effort: behind
    proxies the address can be shared or forged) and DEMO_SESSIONS_PER_HOUR in total (the hard cap)."""
    from fastapi import HTTPException

    from ..governance import core as gov
    from ..models import User
    from ..security.auth import hash_password, issue_token

    ok, retry = _per_client.hit(f"c:{client}", _int("DEMO_SESSIONS_PER_CLIENT_HOUR", 10), 3600)
    if ok:
        ok, retry = _total.hit("all", _int("DEMO_SESSIONS_PER_HOUR", 300), 3600)
    if not ok:
        raise HTTPException(429, f"too many demo sessions right now — try again in {retry} s", headers={"Retry-After": str(retry)})
    u = User(email=f"visitor-{secrets.token_hex(6)}@demo.invalid", password_hash=hash_password(secrets.token_urlsafe(32)), role="demo")
    db.add(u)
    db.flush()
    gov.audit(db, u.email, "demo.session", f"user:{u.id}")
    db.commit()
    minutes = session_minutes()
    return {"token": issue_token(u, ttl_s=minutes * 60), "user": {"email": u.email, "role": u.role}, "expires_in_s": minutes * 60,
            "actions": actions_per_session()}


# ------------------------------------------------------------------ sample data
def _sample_docs() -> list[dict[str, Any]]:
    out = []
    for p in sorted(SAMPLE_DIR.glob("*.md")):
        head, _, body = p.read_text(encoding="utf-8").partition("\n---\n")
        meta = dict(line.split(": ", 1) for line in head.strip().splitlines() if ": " in line)
        out.append({"title": meta.get("title", p.stem), "classification": meta.get("classification", "PUBLIC"),
                    "evidence_class": meta.get("evidence_class", "primary_source"), "description": meta.get("description", ""),
                    "text": body.strip(), "access": {"roles": ["admin"]} if meta.get("classification") in ("RESTRICTED", "CONFIDENTIAL") else {}})
    return out


def seed(db: Session) -> dict[str, int]:
    """Synthetic sample products (the existing DEMO data set) and the sample Knowledge Vault. Idempotent."""
    from ..knowledge import process
    from ..knowledge.extract import Extracted
    from ..models import Collection, Document, Product
    from ..services import data_import

    out = {"products": 0, "documents": 0}
    if not db.scalar(select(func.count(Product.id)).where(Product.is_demo.is_(True))):
        out["products"] = data_import.load_demo(db).get("products", 0)
    if db.get(Collection, SAMPLE_COLLECTION) is None:
        db.add(Collection(name=SAMPLE_COLLECTION, description="Public demo: the platform's own documentation + one synthetic restricted memo",
                          classification="PUBLIC", access={}, owner="system"))
        db.flush()
    have = set(db.scalars(select(Document.title).where(Document.collection == SAMPLE_COLLECTION)))
    for d in _sample_docs():
        if d["title"] in have:
            continue
        process.ingest(db, Extracted("markdown", "text/markdown", d["text"]),
                       {"title": d["title"], "description": d["description"], "source": "Demonkoncernen documentation (sample vault)",
                        "tags": ["sample", "demo"], "evidence_class": d["evidence_class"], "classification": d["classification"],
                        "collection": SAMPLE_COLLECTION, "access": d["access"]})
        out["documents"] += 1
    db.commit()
    return out


# ------------------------------------------------------------------ reset
def reset() -> dict[str, Any]:
    """Drop and recreate every table, then reseed — the scheduled cleanup of all temporary demo data (visitor accounts,
    runs, approvals, audit records of the demo). Refuses while a task is running."""
    from .. import db as dbmod
    from ..models import Base, Task

    s = dbmod.SessionLocal()
    try:
        if s.scalar(select(func.count(Task.id)).where(Task.status == "running")):
            return {"reset": False, "reason": "a task is running — retried at the next interval"}
    finally:
        s.close()
    Base.metadata.drop_all(dbmod.engine)
    dbmod.init_db()
    _invalidate_caches()
    bootstrap()
    return {"reset": True, "at": datetime.now(UTC).isoformat()}


def _invalidate_caches() -> None:
    from ..daemon import cache as l1
    from ..daemon import credentials, state
    from ..governance import egress, observability
    from ..knowledge import index as archive_index

    state.invalidate()
    credentials.invalidate()
    l1.invalidate()
    archive_index.invalidate()
    egress.invalidate()
    with observability._lock:
        observability._buf.clear()
        observability._seq.clear()


def bootstrap() -> dict[str, Any]:
    """What a demo server needs on start and after a reset: the platform's seed rows, then the sample data."""
    from .. import db as dbmod
    from ..agents.catalog import build_orchestrator
    from ..daemon import library, prompts, registry_seed
    from ..governance import gates
    from ..governance.tool_gateway import ensure_default_grants

    s = dbmod.SessionLocal()
    try:
        build_orchestrator().sync_agents(s)
        library.ensure_rows(s)
        prompts.seed(s)
        registry_seed.seed(s)
        ensure_default_grants(s)
        gates.ensure_defaults(s)
        s.commit()
        return seed(s)
    finally:
        s.close()


async def reset_loop() -> None:
    import asyncio

    while True:
        await asyncio.sleep(max(1, reset_hours()) * 3600)
        try:
            out = await asyncio.to_thread(reset)
            log.info("public demo reset: %s", out)
        except Exception:  # noqa: BLE001 — a failed reset must not stop the server; it is retried next interval
            log.exception("public demo reset failed")
