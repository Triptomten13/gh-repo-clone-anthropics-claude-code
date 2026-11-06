"""The internal AI gateway: one call path for the internal AI API with response caching, tracing,
privacy/profile routing and honest failure (LLMUnavailable is raised, never papered over)."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import llm, tracing
from ..ai.router import LLMRouter, LLMUnavailable
from ..models import ResponseCache
from . import state


def request_key(system: str, prompt: str, schema: dict | None, tier: str, max_tokens: int) -> str:
    return hashlib.sha256(json.dumps({"s": system, "p": prompt, "j": schema, "t": tier, "m": max_tokens}, sort_keys=True).encode()).hexdigest()


def prompt_hash(system: str, prompt: str) -> str:
    return hashlib.sha256(f"{system}\x00{prompt}".encode()).hexdigest()[:32]


def complete(db: Session, *, system: str, prompt: str, tier: str = "standard", schema: dict | None = None, max_tokens: int = 2048,
             sensitivity: str = "normal", profile: str | None = None, cacheable: bool = False, agent_id: str = "", purpose: str = "api",
             workflow: str = "", project: str = "", task_id: int | None = None, run_id: int | None = None) -> dict[str, Any]:
    st = state.load(db)  # the observability run is attached by tracing.record (trace_id); run_id stays a G-sus run
    prof = (profile or st["profile"]).upper()
    ph = prompt_hash(system, prompt)
    key = request_key(system, prompt, schema, tier, max_tokens)
    meta = {"agent_id": agent_id, "purpose": purpose, "workflow": workflow, "project": project, "profile": prof, "prompt_hash": ph,
            "task_id": task_id, "run_id": run_id}
    use_cache = cacheable and st["cache"]["enabled"]
    now = datetime.now(UTC)
    if use_cache:
        row = db.scalars(select(ResponseCache).where(ResponseCache.key == key)).first()
        if row and row.expires_at.replace(tzinfo=row.expires_at.tzinfo or UTC) > now:
            row.hits += 1
            att = {"provider": "cache", "model": row.model, "tier": tier, "status": "cache_hit", "cache_hit": True, "locality": "cache",
                   "input_tokens": row.input_tokens, "output_tokens": row.output_tokens, "saved_usd": row.original_cost_usd}
            tracing.record(db, [att], **meta)
            db.commit()
            return {"text": row.text, "data": row.data, "provider": "cache", "model": row.model, "served_from_cache": True,
                    "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "latency_ms": 0, "attempts": [att],
                    "saved_usd": row.original_cost_usd}
    from ..governance import budgets

    # hard budgets: refused BEFORE the call, never bypassed; settled with measured usage afterwards
    hold = budgets.reserve(db, agent_id=agent_id or None, workflow=workflow or purpose, est_tokens=len(system + prompt) // 4 + max_tokens)
    provider = llm.get_provider()
    try:
        if isinstance(provider, LLMRouter):
            r = provider.complete(system=system, prompt=prompt, tier=tier, schema=schema, max_tokens=max_tokens,
                                  sensitivity=sensitivity, profile=prof)
        else:
            r = provider.complete(system=system, prompt=prompt, tier=tier, schema=schema, max_tokens=max_tokens)
    except LLMUnavailable as e:
        budgets.release(db, hold)
        tracing.record(db, e.attempts, **meta)
        db.commit()
        raise
    except Exception as e:
        budgets.release(db, hold)
        tracing.record(db, getattr(e, "attempts", []) or [], **meta)
        db.commit()
        raise
    budgets.settle(db, hold, tokens=r.input_tokens + r.output_tokens, usd=r.cost_usd)
    attempts = getattr(r, "attempts", None) or []
    tracing.record(db, attempts, fallback_result=None if attempts else r, **meta)
    if use_cache and (r.text or r.data is not None):
        row = db.scalars(select(ResponseCache).where(ResponseCache.key == key)).first() or ResponseCache(key=key)
        row.provider, row.model, row.text, row.data = getattr(r, "provider", ""), r.model, r.text, r.data
        row.input_tokens, row.output_tokens, row.original_cost_usd = r.input_tokens, r.output_tokens, r.cost_usd
        row.created_at, row.expires_at, row.hits = now, now + timedelta(seconds=int(st["cache"]["ttl_s"])), 0
        db.add(row)
    db.commit()
    return {"text": r.text, "data": r.data, "provider": getattr(r, "provider", ""), "model": r.model, "served_from_cache": False,
            "input_tokens": r.input_tokens, "output_tokens": r.output_tokens, "cost_usd": r.cost_usd,
            "latency_ms": getattr(r, "latency_ms", 0), "attempts": attempts, "reasoning": getattr(r, "reasoning", "") or "",
            "reasoning_truncated": bool(getattr(r, "reasoning_truncated", False))}


def purge_cache(db: Session) -> int:
    rows = db.scalars(select(ResponseCache)).all()
    for r in rows:
        db.delete(r)
    db.commit()
    return len(rows)
