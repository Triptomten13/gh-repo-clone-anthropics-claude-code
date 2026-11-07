"""DAEMON RESOURCE & COST INTELLIGENCE — hard budgets for model use.

Before a model call, one unit of every applicable `model_calls` limit and the ESTIMATED tokens / dollars are taken
from atomic counters (usage.take); if any limit would be exceeded the call is refused BEFORE it runs — never silently
bypassed. Afterwards the reservation is settled with the measured usage. Scopes: user, agent, workflow, global (per
day or month). Provider/model scopes are checked after routing chose the provider (the plan is only known then).
Existing limits stay in force too: the global daily/monthly USD limits and each agent's daily token budget.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import BudgetRule
from . import usage


class BudgetExceeded(Exception):
    pass


@dataclass
class Reservation:
    held: list[tuple[str, float, str, str]] = field(default_factory=list)  # key, amount, metric, period


def reserve(db: Session, *, user_email: str | None = None, agent_id: str | None = None, workflow: str | None = None,
            est_tokens: int = 0, est_usd: float = 0.0) -> Reservation:
    scopes = {"user": user_email, "agent": agent_id, "workflow": workflow, "global": "*"}
    res = Reservation()
    rules = db.scalars(select(BudgetRule).where(BudgetRule.enabled.is_(True), BudgetRule.metric.in_(("model_calls", "tokens", "usd")))).all()
    for r in rules:
        sid = scopes.get(r.scope_kind)
        if sid is None or r.scope_id not in ("*", sid):
            continue
        amount = {"model_calls": 1.0, "tokens": float(est_tokens), "usd": float(est_usd)}[r.metric]
        key = f"budget:{r.id}:{sid}"
        if not usage.take(db, key, r.limit, amount, r.period):
            release(db, res)
            raise BudgetExceeded(f"budget #{r.id} ({r.scope_kind} {sid}, {r.metric} per {r.period}: limit {r.limit:g}) would be exceeded — "
                                 "the call was not made")
        res.held.append((key, amount, r.metric, r.period))
    return res


def release(db: Session, res: Reservation) -> None:
    for key, amount, _m, period in res.held:
        usage.give_back(db, key, amount, period)
    res.held.clear()


def settle(db: Session, res: Reservation, *, tokens: int, usd: float) -> None:
    """Replace the estimate with what was measured (may end slightly above a limit — reported, and the next call stops)."""
    for key, amount, metric, period in res.held:
        actual = {"model_calls": 1.0, "tokens": float(tokens), "usd": float(usd)}[metric]
        if actual != amount:
            usage.give_back(db, key, amount - actual, period)
