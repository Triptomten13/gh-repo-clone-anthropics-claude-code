"""Cost intelligence dashboard data. API costs are list-price computations (your invoice is authoritative);
local costs are ESTIMATES from configured watts × inference time; savings are split into actual (cache) and estimated."""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import registry
from ..models import BenchmarkRun, LLMCall
from . import quota, state

FAILED = {"error", "unavailable", "rate_limited", "refused", "spend_blocked"}
REFERENCE = {"fast": "claude-haiku-5-5", "standard": "claude-sonnet-5-5", "deep": "claude-opus-5-5", "local": "claude-sonnet-5-5"}


def _agg() -> dict[str, float]:
    return defaultdict(float)


def dashboard(db: Session, days: int = 30) -> dict[str, Any]:
    now = datetime.now(UTC)
    since = now - timedelta(days=days)
    st = state.load(db)
    rows = db.scalars(select(LLMCall).where(LLMCall.created_at >= since)).all()
    price_kwh = float(st["energy"]["usd_per_kwh"])
    by: dict[str, dict[str, dict[str, float]]] = {k: defaultdict(_agg) for k in ("agent", "workflow", "project", "model", "day")}
    t = defaultdict(float)
    for r in rows:
        loc = r.locality or ("local" if r.provider in ("local", "ollama") else "external")
        ok = r.status == "ok"
        t["calls"] += 1
        t["failed"] += r.status in FAILED
        t["excluded_by_policy"] += r.status.startswith("excluded") or r.status == "paused"
        t["external_cost_usd"] += r.cost_usd
        t["input_tokens"] += r.input_tokens if ok else 0
        t["output_tokens"] += r.output_tokens if ok else 0
        t["provider_cached_tokens"] += r.cached_input_tokens
        if r.cache_hit:
            t["cache_hits"] += 1
            t["response_cache_tokens"] += r.input_tokens + r.output_tokens
            t["savings_actual_usd"] += r.saved_usd
        if ok and loc in ("local", "lan"):
            t["local_calls"] += 1
            t["local_tokens"] += r.input_tokens + r.output_tokens
            t["energy_wh"] += r.energy_wh
            ref = registry.find("anthropic", REFERENCE.get(r.tier or "standard", "claude-sonnet-5-5"))
            if ref:
                t["savings_estimated_usd"] += ref.cost(r.input_tokens, r.output_tokens)
        if ok and loc == "external":
            t["external_calls"] += 1
        created = r.created_at if r.created_at.tzinfo else r.created_at.replace(tzinfo=UTC)
        for dim, key in (("agent", r.agent_id or "—"), ("workflow", r.workflow or r.purpose or "—"), ("project", r.project or "—"),
                         ("model", f"{r.provider}:{r.model}"), ("day", created.date().isoformat())):
            b = by[dim][key]
            b["calls"] += 1
            b["cost_usd"] += r.cost_usd
            b["tokens"] += (r.input_tokens + r.output_tokens) if ok else 0
            b["local_calls"] += 1 if ok and loc in ("local", "lan") else 0
            b["failed"] += 1 if r.status in FAILED else 0
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    mtd = sum(r.cost_usd for r in rows if (r.created_at if r.created_at.tzinfo else r.created_at.replace(tzinfo=UTC)) >= month_start)
    if month_start < since:
        mtd = quota.spent(None, month_start)
    dim_days = calendar.monthrange(now.year, now.month)[1]
    elapsed = max((now - month_start).total_seconds() / 86400, 1 / 24)
    quality = {}
    for b in db.scalars(select(BenchmarkRun).where(BenchmarkRun.status == "completed").order_by(BenchmarkRun.id)).all():
        quality[f"{b.provider}:{b.model}"] = {"accuracy": b.summary.get("accuracy"), "cost_per_success_usd": b.summary.get("cost_per_success_usd"),
                                              "avg_latency_ms": b.summary.get("avg_latency_ms"), "run_id": b.id, "at": b.finished_at}
    lim = st["limits"]
    rnd = {k: round(v, 6) if isinstance(v, float) else v for k, v in t.items()}
    return {
        "days": days,
        "totals": {**rnd, "local_energy_cost_usd_estimate": round(t["energy_wh"] / 1000 * price_kwh, 6),
                   "local_share": round(t["local_calls"] / max(1, t["local_calls"] + t["external_calls"]), 3)},
        "savings": {"actual_usd": round(t["savings_actual_usd"], 6), "estimated_usd": round(t["savings_estimated_usd"], 6),
                    "basis": "actual = recorded cost of responses served from cache; estimated = list price of the reference Claude model for "
                             "the same tier and tokens, for work done locally (local electricity not subtracted)"},
        "forecast": {"month_to_date_usd": round(mtd, 6), "projected_month_usd": round(mtd / elapsed * dim_days, 4),
                     "method": "linear extrapolation of month-to-date external spend"},
        "limits": {"daily_usd": lim.get("daily_usd"), "monthly_usd": lim.get("monthly_usd"), "per_provider": lim.get("per_provider", {})},
        "by_agent": {k: dict(v) for k, v in by["agent"].items()}, "by_workflow": {k: dict(v) for k, v in by["workflow"].items()},
        "by_project": {k: dict(v) for k, v in by["project"].items()}, "by_model": {k: dict(v) for k, v in by["model"].items()},
        "by_day": dict(sorted((k, dict(v)) for k, v in by["day"].items())),
        "quality": quality, "quotas": quota.snapshot(),
        "note": "API costs use list prices — your provider invoice is authoritative. Local costs are estimates.",
    }
