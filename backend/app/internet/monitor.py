"""Continuous monitoring of approved subjects with change detection.

Each monitor has a purpose, a query, sources, a frequency and a request budget. A run fetches only result METADATA from
the chosen official APIs (no page downloads), fingerprints the result set and reports only items not seen before —
so a quiet subject produces no alert at all (no alert fatigue), and an unchanged subject costs one small request per
source per period.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..daemon import telemetry
from ..models import Monitor, MonitorEvent
from . import sources as S
from .http import FetchError, OfflineError

MAX_SEEN = 500
TEMPLATES = [  # suggestions for the UI; nothing is created automatically
    {"name": "Local model releases", "purpose": "new GGUF models that could replace a DAEMON slot", "query": "gguf instruct", "sources": ["hf"], "every_minutes": 1440},
    {"name": "llama.cpp releases", "purpose": "runtime updates and fixes", "query": "llama.cpp", "sources": ["github", "hn"], "every_minutes": 1440},
    {"name": "Dependency vulnerabilities", "purpose": "CVEs affecting our stack", "query": "fastapi", "sources": ["nvd"], "every_minutes": 1440},
    {"name": "Quantization research", "purpose": "papers that could make local models cheaper", "query": "LLM quantization", "sources": ["arxiv"], "every_minutes": 10080},
]


def _items(m: Monitor) -> tuple[list[dict[str, Any]], list[str]]:
    items, errors = [], []
    for src in (m.sources or ["wikipedia"])[: m.max_requests]:
        fn = S.REGISTRY.get(src)
        if fn is None:
            errors.append(f"{src}: unknown source")
            continue
        try:
            items += S.sanitize(fn(m.query, 10) if src not in ("rss",) else fn(["https://feeds.bbci.co.uk/news/technology/rss.xml"], m.query, 10))
        except (FetchError, OfflineError, KeyError, ValueError) as e:
            errors.append(f"{src}: {e}"[:160])
    return items, errors


def run_one(db: Session, m: Monitor) -> dict[str, Any]:
    now = datetime.now(UTC)
    items, errors = _items(m)
    fp = hashlib.sha256("|".join(sorted(i["id"] for i in items)).encode()).hexdigest()
    seen = set(m.seen or [])
    new = [i for i in items if i["id"] not in seen]
    m.last_run_at, m.next_run_at = now, now + timedelta(minutes=max(15, m.every_minutes))
    result: dict[str, Any] = {"monitor": m.id, "items": len(items), "new": len(new), "errors": errors, "changed": fp != m.fingerprint}
    if errors and not items:
        db.add(MonitorEvent(monitor_id=m.id, kind="error", summary="; ".join(errors)[:500]))
    elif new and m.fingerprint:  # the first run only establishes the baseline — no alert flood
        db.add(MonitorEvent(monitor_id=m.id, kind="change", summary=f"{len(new)} new item(s) for '{m.query}'",
                            items=[{k: i.get(k) for k in ("title", "url", "source", "published_at", "reliability")} for i in new[:20]]))
        m.last_change_at = now
    m.fingerprint = fp
    m.seen = (list(seen | {i["id"] for i in items}))[-MAX_SEEN:]
    db.commit()
    telemetry.event("monitor_run", monitor=m.id, new=len(new), errors=len(errors))
    return result


def run_due(db: Session) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    due = db.scalars(select(Monitor).where(Monitor.enabled.is_(True), (Monitor.next_run_at.is_(None)) | (Monitor.next_run_at <= now))).all()
    return [run_one(db, m) for m in due]
