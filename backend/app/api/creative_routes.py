"""CREATIVE INTELLIGENCE CENTER API — tournaments, routing decisions, model profiles, provider health, costs, discovery.

Permissions: `creative.run` starts tournaments/benchmarks and asks for routing decisions; `runs.read` reads results
(your own; all with `audit.read`; CONFIDENTIAL and above only for the requester or a knowledge administrator);
`knowledge.write` saves a result to the Vault; `models.manage` runs online discovery. Agents have no API access —
they use the Creative Director agent through the orchestrator.
"""
from __future__ import annotations

import logging
import threading
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..creative import perf, providers as P, quality as Q, tournament as T
from ..db import SessionLocal, get_db
from ..governance import core as gov
from ..models import CreativeEntry, CreativeTournament, LLMCall, ProviderRecord, User
from ..security.rbac import has, require_permission

router = APIRouter(prefix="/api/creative")
log = logging.getLogger(__name__)
CLASSES = Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", "HIGHLY_SENSITIVE"]


def _cols(o: Any) -> dict[str, Any]:
    return {c.key: getattr(o, c.key) for c in o.__table__.columns}


@router.get("/overview")
def overview(db: Session = Depends(get_db), _: User = Depends(require_permission("runs.read"))):
    rows = db.scalars(select(CreativeTournament)).all()
    return {"modes": P.MODE_INFO, "strategies": T.STRATEGIES, "hard_caps": T.HARD, "default_budget": T.Budget().__dict__,
            "autonomous_usd": T.autonomous_usd(), "cost_classes": P.COST_CLASSES, "categories": P.CATEGORIES,
            "rubrics": Q.RUBRICS, "deterministic_weight": Q.DETERMINISTIC_WEIGHT,
            "tournaments": {"total": len(rows), **{s: sum(1 for r in rows if r.status == s) for s in ("completed", "stopped", "failed", "running", "pending_approval")}}}


class SelectIn(BaseModel):
    brief: str = Field(min_length=3, max_length=20_000)
    mode: str = "FREE_FIRST"
    n: int = Field(3, ge=1, le=6)
    classification: CLASSES = "INTERNAL"
    max_usd_per_call: float | None = None


@router.post("/select")
def select_models(b: SelectIn, db: Session = Depends(get_db), _: User = Depends(require_permission("creative.run"))):
    """Routing intelligence (dry run): which models would do this, under which mode, and why the others would not."""
    from ..knowledge.vault import sensitivity_for

    try:
        return P.choose_models(db, b.brief, mode=b.mode, n=b.n, sensitivity=sensitivity_for(b.classification),
                               max_usd_per_call=b.max_usd_per_call)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


class RunIn(BaseModel):
    brief: str = Field(min_length=3, max_length=20_000)
    mode: str = "FREE_FIRST"
    strategy: str = "AUTOMATIC"
    category: str | None = None
    quality_target: float = Field(0.75, ge=0, le=1)
    budget: dict[str, Any] = {}
    allow_parallel: bool = True
    classification: CLASSES = "INTERNAL"
    min_gain: float = Field(0.02, ge=0, le=1)
    use_cache: bool = True
    approval_id: int | None = None
    wait: bool = False  # true: run in this request (tests, scripts); false: run in the background and poll


def _execute_in_background(tid: int, user_id: int, allow_parallel: bool, min_gain: float) -> None:
    s = SessionLocal()
    try:
        t = s.get(CreativeTournament, tid)
        T.execute(s, t, user=s.get(User, user_id), allow_parallel=allow_parallel, min_gain=min_gain)
    except Exception as e:  # noqa: BLE001 — recorded on the tournament, never hidden
        log.exception("creative tournament %s failed", tid)
        s.rollback()
        t = s.get(CreativeTournament, tid)
        if t is not None and t.status in ("ready", "running"):
            t.status, t.stop_reason, t.finished_at = "failed", f"{type(e).__name__}: {str(e)[:300]}", datetime.now(UTC)
            s.commit()
    finally:
        s.close()


@router.post("/tournaments")
def start(b: RunIn, db: Session = Depends(get_db), user: User = Depends(require_permission("creative.run"))):
    from fastapi.responses import JSONResponse

    from ..governance.policy import PolicyDenied

    try:
        t = T.prepare(db, b.brief, user=user, mode=b.mode, strategy=b.strategy, category=b.category, quality_target=b.quality_target,
                      budget=b.budget, classification=b.classification, use_cache=b.use_cache, approval_id=b.approval_id)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except PolicyDenied as e:
        db.commit()
        raise HTTPException(403, {"category": e.decision.category_name, "reasons": e.decision.reasons}) from None
    if t.status == "pending_approval":
        return JSONResponse({"status": "pending_approval", "approval_id": t.approval_id, "tournament": t.id, "reason": t.stop_reason},
                            status_code=202)
    if t.status == "ready":
        if b.wait:
            T.execute(db, t, user=user, allow_parallel=b.allow_parallel, min_gain=b.min_gain)
        else:
            threading.Thread(target=_execute_in_background, args=(t.id, user.id, b.allow_parallel, b.min_gain), daemon=True).start()
    return detail(t.id, db, user)


def _visible(t: CreativeTournament, user: User) -> bool:
    if t.created_by == user.email or has(user, "audit.read") and t.classification in ("PUBLIC", "INTERNAL"):
        return True
    return has(user, "knowledge.admin")


@router.get("/tournaments")
def tournaments(limit: int = 50, db: Session = Depends(get_db), user: User = Depends(require_permission("runs.read"))):
    rows = db.scalars(select(CreativeTournament).order_by(CreativeTournament.id.desc()).limit(min(limit, 200)))
    return [{k: v for k, v in _cols(t).items() if k not in ("plan",)} for t in rows if _visible(t, user)]


@router.get("/tournaments/{tid}")
def detail(tid: int, db: Session = Depends(get_db), user: User = Depends(require_permission("runs.read"))):
    t = db.get(CreativeTournament, tid)
    if t is None or not _visible(t, user):
        raise HTTPException(404, "tournament not found")
    plan = {k: v for k, v in (t.plan or {}).items() if k != "ranked"}
    entries = [_cols(e) for e in db.scalars(select(CreativeEntry).where(CreativeEntry.tournament_id == tid).order_by(CreativeEntry.id))]
    return {**_cols(t), "plan": plan, "entries": entries}


@router.post("/tournaments/{tid}/save")
def save(tid: int, db: Session = Depends(get_db), user: User = Depends(require_permission("knowledge.write"))):
    t = db.get(CreativeTournament, tid)
    if t is None or not _visible(t, user):
        raise HTTPException(404, "tournament not found")
    if t.saved_document_id:
        return {"document_id": t.saved_document_id, "already_saved": True}
    try:
        return {"document_id": T.save_to_vault(db, t, user)}
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


# ------------------------------------------------------------------ model performance intelligence
@router.get("/models")
def models(db: Session = Depends(get_db), _: User = Depends(require_permission("runs.read"))):
    observed: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for e, cat in db.execute(select(CreativeEntry, CreativeTournament.category).join(CreativeTournament,
                                                                                      CreativeTournament.id == CreativeEntry.tournament_id)
                             .where(CreativeEntry.score.is_not(None))):
        observed[e.model_id][cat].append(e.score)
    return {**perf.table(db), "due": perf.due(db), "tasks": [{k: t[k] for k in ("id", "category", "prompt")} for t in perf.TASKS],
            "observed_in_tournaments": {m: {c: {"n": len(v), "avg": round(sum(v) / len(v), 3)} for c, v in cats.items()}
                                        for m, cats in observed.items()},
            "note": "Benchmark scores are deterministic on a fixed dataset; tournament observations are not reproducible and are shown apart."}


class BenchIn(BaseModel):
    models: list[str] = Field(min_length=1, max_length=8)
    categories: list[str] | None = None
    wait: bool = False


def _bench_bg(models_: list[str], cats: list[str] | None, actor: str) -> None:
    s = SessionLocal()
    try:
        perf.run(s, models_, categories=cats, actor=actor)
    except Exception:  # noqa: BLE001
        log.exception("benchmark failed")
    finally:
        s.close()


@router.post("/benchmarks")
def benchmark(b: BenchIn, db: Session = Depends(get_db), user: User = Depends(require_permission("creative.run"))):
    from ..governance.policy import PolicyDenied, Request, enforce

    try:
        enforce(db, Request(action="creative.benchmark", user_email=user.email, user_role=user.role, payload={"models": b.models}))
    except PolicyDenied as e:
        db.commit()
        raise HTTPException(403, {"reasons": e.decision.reasons}) from None
    db.commit()
    if b.wait:
        return perf.run(db, b.models, categories=b.categories, actor=user.email)
    threading.Thread(target=_bench_bg, args=(b.models, b.categories, user.email), daemon=True).start()
    return {"status": "started", "models": b.models, "dataset": perf.DATASET_VERSION}


# ------------------------------------------------------------------ provider health + discovery
@router.get("/providers")
def provider_health(db: Session = Depends(get_db), _: User = Depends(require_permission("runs.read"))):
    from ..daemon import quota

    since = datetime.now(UTC) - timedelta(hours=24)
    stats: dict[str, dict[str, Any]] = {}
    for c in db.scalars(select(LLMCall).where(LLMCall.created_at >= since)):
        k = f"{c.provider}:{c.model}"
        s = stats.setdefault(k, {"calls": 0, "ok": 0, "errors": 0, "rate_limited": 0, "excluded": 0, "latency": []})
        s["calls"] += 1
        if c.status in ("ok", "cache_hit"):
            s["ok"] += 1
            s["latency"].append(c.latency_ms)
        elif c.status == "rate_limited":
            s["rate_limited"] += 1
        elif c.status.startswith("excluded") or c.status in ("not_configured", "paused", "spend_blocked", "circuit_open"):
            s["excluded"] += 1
        else:
            s["errors"] += 1
    for s in stats.values():
        lat = sorted(s.pop("latency"))
        s["p50_latency_ms"] = lat[len(lat) // 2] if lat else None
        tried = s["ok"] + s["errors"] + s["rate_limited"]
        s["error_rate"] = round((s["errors"] + s["rate_limited"]) / tried, 3) if tried else None
    router_ = P.active_router()
    cands = P.available_models(db)
    return {"models": [{**c.as_dict(), "last_24h": stats.get(c.id)} for c in cands],
            "runtimes": router_.health(), "quota": quota.snapshot() if hasattr(quota, "snapshot") else None,
            "registry": [{"id": r.id, "name": r.name, "kind": r.kind, "status": r.status, "adapter": r.adapter,
                          "free_tier": (r.facts or {}).get("free_tier", "unknown"), "last_verified_at": r.last_verified_at}
                         for r in db.scalars(select(ProviderRecord).order_by(ProviderRecord.id))],
            "note": "Free tiers, quotas and prices are recorded only when verified from the provider's official documentation."}


@router.get("/discovery")
def discovery(db: Session = Depends(get_db), user: User = Depends(require_permission("creative.run"))):
    """What could be added — never routable until validated: unverified providers, catalogued models not installed,
    installed models not yet benchmarked."""
    from ..daemon import catalog
    from ..models import LocalModel

    installed = {m.key for m in db.scalars(select(LocalModel).where(LocalModel.status == "installed"))}
    out = {"unverified_providers": [{"id": r.id, "name": r.name, "website": r.website, "missing": [k for k, v in (r.facts or {}).items()
                                                                                                   if str(v).startswith("unknown")]}
                                    for r in db.scalars(select(ProviderRecord).where(ProviderRecord.status != "operational"))],
           "catalog_not_installed": [{"key": e.key, "name": e.display_name, "licence": e.license, "commercial_use": catalog.commercial_use(e.license),
                                      "size_gb": round(e.size_bytes / 1e9, 2), "languages": list(e.languages)}
                                     for e in catalog.CATALOG if e.kind == "chat" and e.key not in installed],
           "benchmark_due": perf.due(db),
           "validation_path": ["discovered", "facts verified from official docs (registry)", "adapter exists", "benchmarked on the dataset",
                               "approved for routing by a second person (providers.approve, RESTRICTED)"]}
    gov.audit(db, user.email, "providers.discover", "registry", unverified=len(out["unverified_providers"]))
    db.commit()
    return out


# ------------------------------------------------------------------ cost intelligence
@router.get("/costs")
def costs(days: int = 30, db: Session = Depends(get_db), _: User = Depends(require_permission("runs.read"))):
    from ..ai import registry

    since = datetime.now(UTC) - timedelta(days=min(days, 365))
    by: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    creative_calls = 0
    for c in db.scalars(select(LLMCall).where(LLMCall.created_at >= since, LLMCall.status.in_(("ok", "cache_hit")))):
        k = c.locality or "external"
        by[k]["calls"] += 1
        by[k]["tokens"] += c.input_tokens + c.output_tokens
        by[k]["usd"] += c.cost_usd
        creative_calls += (c.purpose or "").startswith("creative")
    cheapest = min((m for m in registry.ANTHROPIC if m.output_usd_per_mtok), key=lambda m: m.output_usd_per_mtok, default=None)
    local_tok = by["local"]["tokens"] if "local" in by else 0
    saved = round(local_tok / 1e6 * ((cheapest.input_usd_per_mtok + cheapest.output_usd_per_mtok) / 2), 4) if cheapest else None
    ts = db.scalars(select(CreativeTournament).where(CreativeTournament.created_at >= since)).all()
    done = [t for t in ts if t.status == "completed"]
    spent = sum((t.usage or {}).get("usd", 0) for t in ts)
    cvru = [(t.usage or {}).get("creative_value_per_resource_unit") for t in ts if (t.usage or {}).get("creative_value_per_resource_unit") is not None]
    return {"days": days, "by_locality": {k: {kk: round(vv, 6) for kk, vv in v.items()} for k, v in by.items()}, "creative_calls": creative_calls,
            "estimated_savings_usd": saved,
            "estimated_savings_note": (f"ESTIMATE: tokens served locally priced at the cheapest registry model ({cheapest.model_id}); "
                                       "local inference still costs electricity (see DAEMON → Costs)") if cheapest else None,
            "tournaments": {"count": len(ts), "accepted": len(done), "usd": round(spent, 6),
                            "usd_per_accepted_result": round(spent / len(done), 6) if done else None,
                            "avg_creative_value_per_resource_unit": round(sum(cvru) / len(cvru), 4) if cvru else None,
                            "tokens": sum((t.usage or {}).get("tokens", 0) for t in ts), "calls": sum((t.usage or {}).get("calls", 0) for t in ts)}}
