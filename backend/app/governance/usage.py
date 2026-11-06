"""Atomic budget counters. take() is a single conditional UPDATE — the database decides, so N concurrent callers can
never take more than the limit allows (no check-then-act window)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from ..models import UsageCounter


def today() -> str:
    return datetime.now(UTC).date().isoformat()


def _ensure(db: Session, key: str, day: str) -> None:
    if db.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    db.execute(insert(UsageCounter).values(key=key, day=day, used=0.0).on_conflict_do_nothing())


def take(db: Session, key: str, limit: float, amount: float = 1.0) -> bool:
    day = today()
    _ensure(db, key, day)
    res = db.execute(update(UsageCounter).where(UsageCounter.key == key, UsageCounter.day == day, UsageCounter.used + amount <= limit)
                     .values(used=UsageCounter.used + amount))
    return res.rowcount == 1


def give_back(db: Session, key: str, amount: float = 1.0) -> None:
    db.execute(update(UsageCounter).where(UsageCounter.key == key, UsageCounter.day == today()).values(used=UsageCounter.used - amount))


def used(db: Session, key: str) -> float:
    row = db.get(UsageCounter, (key, today()))
    return float(row.used) if row else 0.0
