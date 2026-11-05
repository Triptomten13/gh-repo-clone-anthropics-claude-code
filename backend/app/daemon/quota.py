"""Quota intelligence: respect provider rate limits with exponential backoff, manual pauses and spend limits.
Never rotates accounts or credentials to get around a limit — a limited provider is simply skipped until it recovers."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from . import state

BASE_S, MAX_S = 5.0, 900.0


@dataclass
class QuotaState:
    rate_limit_events: int = 0
    level: int = 0
    paused_until: float = 0.0
    last_event: float | None = None
    requests: int = 0
    tokens: int = 0
    reset_hint: str | None = None
    history: list[float] = field(default_factory=list)


_q: dict[str, QuotaState] = {}
_lock = threading.Lock()


def _get(provider: str) -> QuotaState:
    with _lock:
        return _q.setdefault(provider, QuotaState())


def note_success(provider: str, tokens: int = 0) -> None:
    q = _get(provider)
    q.level, q.requests, q.tokens = 0, q.requests + 1, q.tokens + tokens


def note_rate_limited(provider: str, retry_after_s: float | None = None) -> float:
    q = _get(provider)
    q.rate_limit_events += 1
    q.level += 1
    wait = retry_after_s if retry_after_s else min(BASE_S * 2 ** (q.level - 1), MAX_S)
    q.paused_until = time.time() + wait
    q.last_event = time.time()
    q.history = (q.history + [q.last_event])[-50:]
    return wait


def is_rate_limit(err: str) -> bool:
    e = err.lower()
    return "ratelimit" in e or "rate limit" in e or "429" in e or "rate_limited" in e


def blocked_reason(provider: str) -> str | None:
    st = state.load()
    if provider in st.get("paused_providers", []):
        return "paused_by_admin"
    q = _get(provider)
    if q.paused_until > time.time():
        return f"rate_limited_backoff ({int(q.paused_until - time.time())}s left)"
    return None


def snapshot() -> dict[str, Any]:
    now = time.time()
    with _lock:
        return {p: {"rate_limit_events": q.rate_limit_events, "backoff_level": q.level,
                    "paused_for_s": max(0, int(q.paused_until - now)), "requests_since_start": q.requests,
                    "tokens_since_start": q.tokens} for p, q in _q.items()}


def reset() -> None:
    with _lock:
        _q.clear()


# ------------------------------------------------------------------ spending
def spent(provider: str | None, since: datetime) -> float:
    from sqlalchemy import func, select

    from .. import db as dbmod
    from ..models import LLMCall

    s = dbmod.SessionLocal()
    try:
        q = select(func.coalesce(func.sum(LLMCall.cost_usd), 0.0)).where(LLMCall.created_at >= since)
        if provider:
            q = q.where(LLMCall.provider == provider)
        return float(s.scalar(q) or 0.0)
    finally:
        s.close()


def spend_check(provider: str, est_cost_usd: float) -> str | None:
    """None if this paid call fits every configured limit, else the reason it is blocked. Unknown ⇒ blocked."""
    from ..config import get_settings

    st = state.load()
    lim = st["limits"]
    now = datetime.now(UTC)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month = day.replace(day=1)
    try:
        daily = lim.get("daily_usd") if lim.get("daily_usd") is not None else get_settings().daily_cost_limit_usd
        if daily is not None and spent(None, day) + est_cost_usd > daily:
            return f"daily limit ${daily} reached"
        if lim.get("monthly_usd") is not None and spent(None, month) + est_cost_usd > lim["monthly_usd"]:
            return f"monthly limit ${lim['monthly_usd']} reached"
        pp = (lim.get("per_provider") or {}).get(provider) or {}
        if pp.get("daily_usd") is not None and spent(provider, day) + est_cost_usd > pp["daily_usd"]:
            return f"{provider} daily limit ${pp['daily_usd']} reached"
        if pp.get("monthly_usd") is not None and spent(provider, month) + est_cost_usd > pp["monthly_usd"]:
            return f"{provider} monthly limit ${pp['monthly_usd']} reached"
    except Exception as e:  # cannot verify spend ⇒ do not spend
        return f"spend could not be verified ({type(e).__name__})"
    return None


def month_window() -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    nxt = (start + timedelta(days=32)).replace(day=1)
    return start, nxt
