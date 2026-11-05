"""Autonomous optimisation — proposals only. Detects waste and suggests cheaper adequate routes; anything that changes
spending, credentials, accounts or provider terms needs an admin decision, and approval never auto-applies config."""
from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
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
    since = datetime.now(UTC) - timedelta(days=days)
    rows = db.scalars(select(LLMCall).where(LLMCall.created_at >= since)).all()
    props: list[dict[str, Any]] = []

    deep_short = defaultdict(list)
    for r in rows:
        if r.status == "ok" and r.tier == "deep" and r.locality == "external" and r.output_tokens < 300:
            deep_short[r.purpose or r.workflow or "—"].append(r)
    for purpose, rs in deep_short.items():
        if len(rs) >= 3:
            props.append({"kind": "downgrade_tier", "title": f"'{purpose}' uses the deep tier for short answers",
                          "detail": f"{len(rs)} deep-tier calls produced < 300 output tokens. Try the standard tier (or a local model) and compare with the benchmark.",
                          "evidence": {"calls": len(rs), "cost_usd": round(sum(r.cost_usd for r in rs), 6)},
                          "estimated_saving_usd": round(sum(r.cost_usd for r in rs) * 0.5, 6), "fp": _fp("downgrade", purpose)})

    dup = Counter(r.prompt_hash for r in rows if r.prompt_hash and r.status == "ok" and not r.cache_hit and r.cost_usd > 0)
    for ph, n in dup.items():
        if n >= 3:
            rs = [r for r in rows if r.prompt_hash == ph and r.status == "ok"]
            props.append({"kind": "enable_cache", "title": f"Identical prompt sent {n}× to a paid model ({rs[0].purpose or rs[0].workflow or '—'})",
                          "detail": "Mark this call cacheable (response cache) or move the stable prefix into the system prompt for provider-side caching.",
                          "evidence": {"prompt_hash": ph, "repeats": n}, "estimated_saving_usd": round(sum(r.cost_usd for r in rs[1:]), 6),
                          "fp": _fp("cache", ph)})

    best_local = None
    for b in db.scalars(select(BenchmarkRun).where(BenchmarkRun.status == "completed", BenchmarkRun.provider == "local")).all():
        if best_local is None or (b.summary.get("accuracy") or 0) > (best_local.summary.get("accuracy") or 0):
            best_local = b
    if best_local and (best_local.summary.get("accuracy") or 0) >= 0.8:
        ext = defaultdict(list)
        for r in rows:
            if r.status == "ok" and r.locality == "external" and r.tier in ("fast", "standard"):
                ext[r.purpose or r.workflow or "—"].append(r)
        for purpose, rs in ext.items():
            props.append({"kind": "move_local", "title": f"Run '{purpose}' on the local model {best_local.model}",
                          "detail": f"Local benchmark accuracy {best_local.summary['accuracy']:.0%}. Verify on real '{purpose}' samples before switching.",
                          "evidence": {"calls": len(rs), "cost_usd": round(sum(r.cost_usd for r in rs), 6), "benchmark_run": best_local.id},
                          "estimated_saving_usd": round(sum(r.cost_usd for r in rs), 6), "fp": _fp("local", purpose, best_local.id)})

    rl = Counter(r.provider for r in rows if r.status == "rate_limited")
    for prov, n in rl.items():
        if n >= 3:
            props.append({"kind": "rate_limits", "title": f"{prov} hit its rate limit {n}× in {days} days",
                          "detail": "Reduce concurrency or batch requests. Never add accounts or rotate keys to get around limits.",
                          "evidence": {"events": n}, "estimated_saving_usd": None, "fp": _fp("rl", prov, n // 10)})

    big = defaultdict(list)
    for r in rows:
        if r.status == "ok" and r.input_tokens > 20000:
            big[r.purpose or r.workflow or "—"].append(r.input_tokens)
    for purpose, toks in big.items():
        props.append({"kind": "context_size", "title": f"'{purpose}' sends very large prompts (avg {sum(toks) // len(toks):,} tokens)",
                      "detail": "Use Archive retrieval + context assembly instead of whole documents; required evidence is kept, duplicates dropped.",
                      "evidence": {"calls": len(toks)}, "estimated_saving_usd": None, "fp": _fp("ctx", purpose)})

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
