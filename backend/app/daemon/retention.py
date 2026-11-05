"""Retention: nothing grows without bound. Each rule says what is removed and why; counts are returned and logged."""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from ..models import LLMCall, MonitorEvent, ResearchRun, ResponseCache, SemanticCacheEntry, WebResource
from . import telemetry

RULES = {
    "response_cache": "expired entries",
    "semantic_cache": "expired entries",
    "web_resources": "expired excerpts not promoted to the Archive (raw web material is not kept)",
    "research_runs": f"older than {os.getenv('RESEARCH_KEEP_DAYS', '90')} days",
    "monitor_events": "acknowledged, older than 30 days",
    "llm_calls": f"older than {os.getenv('LLM_CALLS_KEEP_DAYS', '400')} days (13 months of cost history kept)",
}


def run(db: Session) -> dict[str, Any]:
    now = datetime.now(UTC)
    out = {
        "response_cache": db.query(ResponseCache).filter(ResponseCache.expires_at <= now).delete(synchronize_session=False),
        "semantic_cache": db.query(SemanticCacheEntry).filter(SemanticCacheEntry.expires_at <= now).delete(synchronize_session=False),
        "web_resources": db.query(WebResource).filter(WebResource.expires_at <= now - timedelta(days=1),
                                                      WebResource.promoted_document_id.is_(None)).delete(synchronize_session=False),
        "research_runs": db.query(ResearchRun).filter(ResearchRun.created_at <= now - timedelta(days=int(os.getenv("RESEARCH_KEEP_DAYS", "90"))))
        .delete(synchronize_session=False),
        "monitor_events": db.query(MonitorEvent).filter(MonitorEvent.acknowledged.is_(True), MonitorEvent.created_at <= now - timedelta(days=30))
        .delete(synchronize_session=False),
        "llm_calls": db.query(LLMCall).filter(LLMCall.created_at <= now - timedelta(days=int(os.getenv("LLM_CALLS_KEEP_DAYS", "400"))))
        .delete(synchronize_session=False),
    }
    db.commit()
    telemetry.event("retention", **out)
    return {"deleted": out, "rules": RULES}
