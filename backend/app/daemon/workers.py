"""Distributed inference workers: OpenAI-compatible endpoints (llama.cpp server, vLLM, LM Studio …) on machines you control."""
from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ModelWorker
from .runtime import OpenAICompatProvider, locality_of_url

_cache: tuple[float, dict[str, Any]] | None = None
_lock = threading.Lock()


def invalidate() -> None:
    global _cache
    with _lock:
        _cache = None


def _make(w: ModelWorker) -> OpenAICompatProvider:
    from .credentials import secret_for

    p = OpenAICompatProvider(f"worker:{w.name}", w.base_url, api_key=secret_for(f"worker:{w.name}"))
    p.default_model = (w.models or [""])[0]  # type: ignore[attr-defined]
    return p


def provider_for(db: Session, name: str) -> OpenAICompatProvider:
    w = db.scalars(select(ModelWorker).where(ModelWorker.name == name)).first()
    if not w:
        raise LookupError(name)
    return _make(w)


def active_worker_providers() -> dict[str, Any]:
    global _cache
    now = time.monotonic()
    with _lock:
        if _cache and now - _cache[0] < 10:
            return _cache[1]
    from .. import db as dbmod

    s = dbmod.SessionLocal()
    try:
        rows = s.scalars(select(ModelWorker).where(ModelWorker.enabled.is_(True))).all()
        out = {f"worker:{w.name}": _make(w) for w in rows if w.status != "unreachable" and w.models}
    except Exception:
        out = {}
    finally:
        s.close()
    with _lock:
        _cache = (now, out)
    return out


def register(db: Session, name: str, base_url: str, models: list[str], actor: str) -> ModelWorker:
    w = db.scalars(select(ModelWorker).where(ModelWorker.name == name)).first() or ModelWorker(name=name)
    w.base_url, w.models, w.locality, w.registered_by, w.enabled = base_url.rstrip("/"), models, locality_of_url(base_url), actor, True
    db.add(w)
    db.flush()
    invalidate()
    return w


def check(db: Session, w: ModelWorker) -> dict[str, Any]:
    h = _make(w).health()
    w.status = "healthy" if h.get("reachable") else "unreachable"
    if h.get("reachable"):
        w.last_heartbeat = datetime.now(UTC)
        if h.get("models"):
            w.models = [m for m in h["models"] if m] or w.models
    db.flush()
    invalidate()
    return h
