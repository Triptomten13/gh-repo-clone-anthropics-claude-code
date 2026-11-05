"""Persisted DAEMON settings (SystemState key "daemon") with a short in-process cache.

Settings are changed only by human admins through the API/CLI; agents have no write path.
"""
from __future__ import annotations

import copy
import threading
import time
from typing import Any

PROFILES = ("ECO", "BALANCED", "DEEP", "SPECIALIST", "OFFLINE", "EMERGENCY")

DEFAULTS: dict[str, Any] = {
    "offline_mode": False,          # True ⇒ no external provider is ever called, not even as a fallback
    "profile": "BALANCED",
    "external_allowed": True,       # master switch for paid/external providers (offline_mode overrides)
    "active": {"chat": None, "eco": None, "embedding": None},   # LocalModel.key per slot
    "history": [],                  # activation history for rollback: {slot, previous, new, at, by}
    "limits": {"daily_usd": None, "monthly_usd": 50.0, "per_provider": {}},  # None daily ⇒ use DAILY_COST_LIMIT_USD
    "paused_providers": [],
    "cache": {"enabled": True, "ttl_s": 86400},
    "energy": {"watts": 65.0, "usd_per_kwh": 0.20},  # ESTIMATE inputs for local inference cost; edit to match your hardware/tariff
    "local": {"n_threads": None, "n_ctx": 4096},
}

_lock = threading.Lock()
_cache: tuple[float, dict[str, Any]] | None = None
TTL_S = 2.0


def _merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(db=None) -> dict[str, Any]:
    """Current settings. Uses the given session, or opens a short-lived one."""
    global _cache
    now = time.monotonic()
    with _lock:
        if _cache and now - _cache[0] < TTL_S and db is None:
            return copy.deepcopy(_cache[1])
    from ..governance.core import get_state

    if db is not None:
        val = _merge(DEFAULTS, get_state(db, "daemon"))
    else:
        from .. import db as dbmod

        s = dbmod.SessionLocal()
        try:
            val = _merge(DEFAULTS, get_state(s, "daemon"))
        except Exception:  # table missing during early startup / tests without DB
            val = copy.deepcopy(DEFAULTS)
        finally:
            s.close()
    with _lock:
        _cache = (now, val)
    return copy.deepcopy(val)


def save(db, value: dict[str, Any]) -> dict[str, Any]:
    from ..governance.core import set_state

    merged = _merge(DEFAULTS, value)
    set_state(db, "daemon", merged)
    invalidate()
    return merged


def update(db, **changes: Any) -> dict[str, Any]:
    cur = load(db)
    return save(db, _merge(cur, changes))


def invalidate() -> None:
    global _cache
    with _lock:
        _cache = None
