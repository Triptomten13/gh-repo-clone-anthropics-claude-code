"""Cost intelligence dashboard data. API costs are list-price computations (your invoice is authoritative);
local costs are ESTIMATES from configured watts × inference time; savings are split into actual (cache) and estimated."""
from __future__ import annotations

import calendar
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import registry
from ..models import BenchmarkRun, LLMCall
from . import quota, state

FAILED = {"error", "unavailable", "rate_limited", "refused", "spend_blocked"}
REFERENCE = {"fast": "claude-haiku-5-5", "standard": "claude-sonnet-5-5", "deep": "claude-opus-5-5", "local": "claude-sonnet-5-5"}


def _cases():
    """SQL CASE expressions shared by every aggregation (portable SQLite/PostgreSQL)."""
    from sqlalchemy import and_, case, func, or_

    ok = LLMCall.status == "ok"
    local = or_(LLMCall.locality.in_(("local", "lan")), and_(LLMCall.locality == "", LLMCall.provider.in_(("local", "ollama"))))
    failed = LLMCall.status.in_(tuple(FAILED))
    return {
        "calls": func.count(LLMCall.id),
        "cost_usd": func.coalesce(func.sum(LLMCall.cost_usd), 0.0),
        "tokens": func.coalesce(func.sum(case((ok, LLMCall.input_tokens + LLMCall.output_tokens), else_=0)), 0),
        "local_calls": func.coalesce(func.sum(case((and_(ok, local), 1), else_=0)), 0),
        "failed": func.coalesce(func.sum(case((failed, 1), else_=0)), 0),
    }, ok, local, failed


def _by(db: Session, col: Any, since: datetime) -> dict[str, dict[str, float]]:
    agg, *_ = _cases()
    rows = db.execute(select(col.label("k"), *[v.label(k) for k, v in agg.items()]).where(LLMCall.created_at >= since).group_by(col)).all()
    return {str(r.k) if r.k not in (None, "") else "—": {k: (round(float(getattr(r, k)), 6) if k == "cost_usd" else int(getattr(r, k))) for k in agg}
            for r in rows}


def dashboard(db: Session, days: int = 30) -> dict[str, Any]:
    """All aggregation happens in SQL (one grouped query per dimension). Before: every row in the window was loaded
    into Python — 563 ms at 20k rows (docs/perf/baseline.json)."""
    from sqlalchemy import and_, case, func

    now = datetime.now(UTC)
    since = now - timedelta(days=days)
    st = state.load(db)
    price_kwh = float(st["energy"]["usd_per_kwh"])
    agg, ok, local, failed = _cases()
    tot = db.execute(select(
        *[v.label(k) for k, v in agg.items()],
        func.coalesce(func.sum(case((ok, LLMCall.input_tokens), else_=0)), 0).label("input_tokens"),
        func.coalesce(func.sum(case((ok, LLMCall.output_tokens), else_=0)), 0).label("output_tokens"),
        func.coalesce(func.sum(LLMCall.cached_input_tokens), 0).label("provider_cached_tokens"),
        func.coalesce(func.sum(case((LLMCall.cache_hit.is_(True), 1), else_=0)), 0).label("cache_hits"),
        func.coalesce(func.sum(case((LLMCall.cache_hit.is_(True), LLMCall.input_tokens + LLMCall.output_tokens), else_=0)), 0).label("response_cache_tokens"),
        func.coalesce(func.sum(LLMCall.saved_usd), 0.0).label("savings_actual_usd"),
        func.coalesce(func.sum(case((and_(ok, local), LLMCall.energy_wh), else_=0.0)), 0.0).label("energy_wh"),
        func.coalesce(func.sum(case((and_(ok, ~local, LLMCall.provider != "cache"), 1), else_=0)), 0).label("external_calls"),
        func.coalesce(func.sum(case((LLMCall.status.like("excluded%") | (LLMCall.status == "paused"), 1), else_=0)), 0).label("excluded_by_policy"),
    ).where(LLMCall.created_at >= since)).one()
    t: dict[str, Any] = dict(tot._mapping)
    t["external_cost_usd"] = round(float(t.pop("cost_usd")), 6)
    t.pop("tokens", None)
    # estimated savings: local work priced at the reference Claude model for its tier (pricing is linear in tokens)
    est = 0.0
    for tier, i, o in db.execute(select(LLMCall.tier, func.sum(LLMCall.input_tokens), func.sum(LLMCall.output_tokens))
                                 .where(LLMCall.created_at >= since, ok, local).group_by(LLMCall.tier)):
        ref = registry.find("anthropic", REFERENCE.get(tier or "standard", "claude-sonnet-5-5"))
        est += ref.cost(int(i or 0), int(o or 0)) if ref else 0.0
    t["savings_estimated_usd"] = round(est, 6)
    t = {k: (round(float(v), 6) if isinstance(v, float) else int(v)) for k, v in t.items()}
    day = func.date(LLMCall.created_at)
    by_day = _by(db, day, since)
    workflow = case((LLMCall.workflow != "", LLMCall.workflow), else_=LLMCall.purpose)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    mtd = quota.spent(None, month_start)
    dim_days = calendar.monthrange(now.year, now.month)[1]
    elapsed = max((now - month_start).total_seconds() / 86400, 1 / 24)
    quality = {}
    for b in db.scalars(select(BenchmarkRun).where(BenchmarkRun.status == "completed").order_by(BenchmarkRun.id)).all():
        quality[f"{b.provider}:{b.model}"] = {"accuracy": b.summary.get("accuracy"), "cost_per_success_usd": b.summary.get("cost_per_success_usd"),
                                              "avg_latency_ms": b.summary.get("avg_latency_ms"), "run_id": b.id, "at": b.finished_at}
    lim = st["limits"]
    return {
        "days": days,
        "totals": {**t, "local_energy_cost_usd_estimate": round(t["energy_wh"] / 1000 * price_kwh, 6),
                   "local_share": round(t["local_calls"] / max(1, t["local_calls"] + t["external_calls"]), 3)},
        "savings": {"actual_usd": round(t["savings_actual_usd"], 6), "estimated_usd": round(t["savings_estimated_usd"], 6),
                    "basis": "actual = recorded cost of responses served from cache; estimated = list price of the reference Claude model for "
                             "the same tier and tokens, for work done locally (local electricity not subtracted)"},
        "forecast": {"month_to_date_usd": round(mtd, 6), "projected_month_usd": round(mtd / elapsed * dim_days, 4),
                     "method": "linear extrapolation of month-to-date external spend"},
        "limits": {"daily_usd": lim.get("daily_usd"), "monthly_usd": lim.get("monthly_usd"), "per_provider": lim.get("per_provider", {})},
        "by_agent": _by(db, LLMCall.agent_id, since), "by_workflow": _by(db, workflow, since),
        "by_project": _by(db, LLMCall.project, since), "by_model": _by(db, LLMCall.provider + ":" + LLMCall.model, since),
        "by_day": dict(sorted(by_day.items())),
        "quality": quality, "quotas": quota.snapshot(),
        "note": "API costs use list prices — your provider invoice is authoritative. Local costs are estimates.",
    }
