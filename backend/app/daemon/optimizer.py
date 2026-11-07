"""Autonomous optimisation — proposals only. Detects waste and suggests cheaper adequate routes; anything that changes
spending, credentials, accounts or provider terms needs an admin decision, and approval never auto-applies config."""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..governance import core as gov
from ..models import BenchmarkRun, LLMCall, OptimizationProposal, ProviderRecord
from . import library


def _fp(*parts: Any) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:32]


def generate(db: Session, days: int = 14) -> list[OptimizationProposal]:
    """Grouped SQL queries only (before: every row of the window was loaded into Python — 172 ms at 20k rows)."""
    from sqlalchemy import func

    since = datetime.now(UTC) - timedelta(days=days)
    W = LLMCall.created_at >= since
    label = func.coalesce(func.nullif(LLMCall.purpose, ""), func.nullif(LLMCall.workflow, ""), "—")
    props: list[dict[str, Any]] = []

    for purpose, n, cost in db.execute(select(label, func.count(LLMCall.id), func.sum(LLMCall.cost_usd)).where(
            W, LLMCall.status == "ok", LLMCall.tier == "deep", LLMCall.locality == "external", LLMCall.output_tokens < 300).group_by(label)):
        if n >= 3:
            props.append({"kind": "downgrade_tier", "title": f"'{purpose}' uses the deep tier for short answers",
                          "detail": f"{n} deep-tier calls produced < 300 output tokens. Try the standard tier (or a local model) and compare with the benchmark.",
                          "evidence": {"calls": n, "cost_usd": round(cost or 0, 6)}, "estimated_saving_usd": round((cost or 0) * 0.5, 6),
                          "fp": _fp("downgrade", purpose)})

    for ph, n, cost, first_cost, purpose in db.execute(
            select(LLMCall.prompt_hash, func.count(LLMCall.id), func.sum(LLMCall.cost_usd), func.min(LLMCall.cost_usd), func.max(label))
            .where(W, LLMCall.prompt_hash != "", LLMCall.status == "ok", LLMCall.cache_hit.is_(False), LLMCall.cost_usd > 0)
            .group_by(LLMCall.prompt_hash).having(func.count(LLMCall.id) >= 3)):
        props.append({"kind": "enable_cache", "title": f"Identical prompt sent {n}× to a paid model ({purpose})",
                      "detail": "Mark this call cacheable (response cache) or move the stable prefix into the system prompt for provider-side caching.",
                      "evidence": {"prompt_hash": ph, "repeats": n}, "estimated_saving_usd": round((cost or 0) - (first_cost or 0), 6),
                      "fp": _fp("cache", ph)})

    best_local = None
    for b in db.scalars(select(BenchmarkRun).where(BenchmarkRun.status == "completed", BenchmarkRun.provider == "local")).all():
        if best_local is None or (b.summary.get("accuracy") or 0) > (best_local.summary.get("accuracy") or 0):
            best_local = b
    if best_local and (best_local.summary.get("accuracy") or 0) >= 0.8:
        for purpose, n, cost in db.execute(select(label, func.count(LLMCall.id), func.sum(LLMCall.cost_usd)).where(
                W, LLMCall.status == "ok", LLMCall.locality == "external", LLMCall.tier.in_(("fast", "standard"))).group_by(label)):
            props.append({"kind": "move_local", "title": f"Run '{purpose}' on the local model {best_local.model}",
                          "detail": f"Local benchmark accuracy {best_local.summary['accuracy']:.0%}. Verify on real '{purpose}' samples before switching.",
                          "evidence": {"calls": n, "cost_usd": round(cost or 0, 6), "benchmark_run": best_local.id},
                          "estimated_saving_usd": round(cost or 0, 6), "fp": _fp("local", purpose, best_local.id)})

    for prov, n in db.execute(select(LLMCall.provider, func.count(LLMCall.id)).where(W, LLMCall.status == "rate_limited").group_by(LLMCall.provider)):
        if n >= 3:
            props.append({"kind": "rate_limits", "title": f"{prov} hit its rate limit {n}× in {days} days",
                          "detail": "Reduce concurrency or batch requests. Never add accounts or rotate keys to get around limits.",
                          "evidence": {"events": n}, "estimated_saving_usd": None, "fp": _fp("rl", prov, n // 10)})

    for purpose, n, avg in db.execute(select(label, func.count(LLMCall.id), func.avg(LLMCall.input_tokens)).where(
            W, LLMCall.status == "ok", LLMCall.input_tokens > 20000).group_by(label)):
        props.append({"kind": "context_size", "title": f"'{purpose}' sends very large prompts (avg {int(avg or 0):,} tokens)",
                      "detail": "Use Archive retrieval + context assembly instead of whole documents; required evidence is kept, duplicates dropped.",
                      "evidence": {"calls": n}, "estimated_saving_usd": None, "fp": _fp("ctx", purpose)})

    if library.resolve(db, "chat") is None:
        props.append({"kind": "install_local", "title": "No local chat model is active",
                      "detail": "Install and activate a catalogued local model so routine tasks stop depending on external providers.",
                      "evidence": {}, "estimated_saving_usd": None, "fp": _fp("install_local")})

    stale = datetime.now(UTC) - timedelta(days=90)
    for p in db.scalars(select(ProviderRecord)).all():
        lv = p.last_verified_at.replace(tzinfo=p.last_verified_at.tzinfo or UTC) if p.last_verified_at else None
        if p.adapter and (lv is None or lv < stale):
            props.append({"kind": "reverify_provider", "title": f"Re-verify {p.name} from its official documentation",
                          "detail": "Facts older than 90 days (or never verified) must not drive routing or spending decisions.",
                          "evidence": {"last_verified_at": str(lv) if lv else None}, "estimated_saving_usd": None, "fp": _fp("verify", p.id, str(lv))})

    created = []
    for p in props:
        if db.scalars(select(OptimizationProposal).where(OptimizationProposal.fingerprint == p["fp"])).first():
            continue
        o = OptimizationProposal(kind=p["kind"], title=p["title"], detail=p["detail"], evidence=p["evidence"],
                                 estimated_saving_usd=p["estimated_saving_usd"], fingerprint=p["fp"])
        db.add(o)
        created.append(o)
    db.flush()
    return created


def decide(db: Session, pid: int, approve: bool, actor: str) -> OptimizationProposal:
    o = db.get(OptimizationProposal, pid)
    if not o:
        raise LookupError("no such proposal")
    if o.status != "proposed":
        raise ValueError(f"already {o.status}")
    o.status, o.decided_by, o.decided_at = ("approved" if approve else "rejected"), actor, datetime.now(UTC)
    gov.audit(db, actor, "optimization.decide", f"proposal:{o.id}", status=o.status, kind=o.kind)
    db.flush()
    return o
