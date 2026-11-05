"""Persist provider attempts as LLMCall rows (cost, latency, status) and report usage."""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import LLMCall


def record(db: Session, attempts: list[dict], *, task_id: int | None = None, run_id: int | None = None, agent_id: str = "",
           purpose: str = "", fallback_result: Any | None = None) -> None:
    rows = attempts or ([] if fallback_result is None else [{
        "provider": getattr(fallback_result, "provider", "") or "custom", "model": fallback_result.model, "status": "ok",
        "input_tokens": fallback_result.input_tokens, "output_tokens": fallback_result.output_tokens, "cost_usd": fallback_result.cost_usd,
        "latency_ms": getattr(fallback_result, "latency_ms", 0)}])
    for a in rows:
        db.add(LLMCall(task_id=task_id, run_id=run_id, agent_id=agent_id, purpose=purpose, provider=a.get("provider", ""),
                       model=a.get("model", ""), tier=a.get("tier", ""), status=a.get("status", ""), input_tokens=a.get("input_tokens", 0),
                       output_tokens=a.get("output_tokens", 0), cost_usd=a.get("cost_usd", 0.0), latency_ms=a.get("latency_ms", 0),
                       error=a.get("error", "")))
    db.flush()


def spent_today(db: Session) -> float:
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return float(db.scalar(select(func.coalesce(func.sum(LLMCall.cost_usd), 0.0)).where(LLMCall.created_at >= start)) or 0.0)


def usage(db: Session, days: int = 30) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = db.scalars(select(LLMCall).where(LLMCall.created_at >= since)).all()
    by_model: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    by_agent: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    by_day: dict[str, float] = defaultdict(float)
    for r in rows:
        k = f"{r.provider}:{r.model}"
        m = by_model[k]
        m["calls"] += 1
        m[f"status_{r.status}"] += 1
        m["input_tokens"] += r.input_tokens
        m["output_tokens"] += r.output_tokens
        m["cost_usd"] += r.cost_usd
        if r.status == "ok":
            m["latency_ms_total"] += r.latency_ms
        by_agent[r.agent_id or "—"]["cost_usd"] += r.cost_usd
        by_agent[r.agent_id or "—"]["calls"] += 1
        created = r.created_at if r.created_at.tzinfo else r.created_at.replace(tzinfo=UTC)
        by_day[created.date().isoformat()] += r.cost_usd
    for m in by_model.values():
        ok = m.get("status_ok", 0)
        m["avg_latency_ms"] = round(m.pop("latency_ms_total", 0) / ok) if ok else None
        m["cost_usd"] = round(m["cost_usd"], 6)
    return {"days": days, "calls": len(rows), "cost_usd": round(sum(r.cost_usd for r in rows), 6),
            "by_model": {k: dict(v) for k, v in by_model.items()}, "by_agent": {k: dict(v) for k, v in by_agent.items()},
            "by_day": dict(sorted(by_day.items())), "note": "Costs use the registry's list prices; your invoice is authoritative."}
