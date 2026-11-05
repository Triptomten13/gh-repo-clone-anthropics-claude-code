"""L2 (exact) and L3 (semantic) answer cache for VERIFIED answers to stable questions.

Guards, because two similar questions are not automatically the same question:
  * same scope (global vs user:<id> — private answers never cross users), same task category;
  * never for time-sensitive questions (the orchestrator does not consult it for those);
  * semantic matches need a real semantic embedder, cosine ≥ 0.95, IDENTICAL numbers and the same negation;
  * only answers marked verified (grounded in cited sources) are stored; entries expire; size is capped.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import SemanticCacheEntry

THRESHOLD = 0.95
MAX_ENTRIES = 5000
NEG = re.compile(r"\b(not|no|never|without|except|isn't|aren't|doesn't|don't|inte|utan)\b", re.I)
stats = {"l2_hits": 0, "l3_hits": 0, "misses": 0, "stored": 0, "rejected_guard": 0}


def norm(q: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s%.-]", " ", q.lower())).strip()[:500]


def _numbers(q: str) -> list[str]:
    return sorted(re.findall(r"\d+(?:[.,]\d+)?", q))


def _embed(q: str) -> tuple[str, list[float]] | None:
    from ..knowledge.process import embedder

    mid, fn = embedder()
    if not mid.startswith(("gguf:", "ollama:")):
        return None  # the lexical hash embedder is not good enough to call two questions "the same"
    return mid, fn([q], kind="query")[0]


def lookup(db: Session, question: str, *, category: str, scope: str = "global") -> dict[str, Any] | None:
    now = datetime.now(UTC)
    n = norm(question)
    base = select(SemanticCacheEntry).where(SemanticCacheEntry.scope == scope, SemanticCacheEntry.category == category,
                                            SemanticCacheEntry.expires_at > now, SemanticCacheEntry.verified.is_(True))
    e = db.scalars(base.where(SemanticCacheEntry.question_norm == n).order_by(SemanticCacheEntry.id.desc())).first()
    if e:
        e.hits += 1
        db.commit()
        stats["l2_hits"] += 1
        return {"answer": e.answer, "sources": e.sources, "layer": "L2-exact", "similarity": 1.0, "entry_id": e.id}
    try:
        emb = _embed(question)
    except Exception:
        emb = None
    if emb:
        from ..ai.providers import cosine

        mid, v = emb
        best, best_sim = None, 0.0
        for cand in db.scalars(base.where(SemanticCacheEntry.embedding_model == mid).order_by(SemanticCacheEntry.id.desc()).limit(500)):
            sim = cosine(v, cand.embedding)
            if sim > best_sim:
                best, best_sim = cand, sim
        if best and best_sim >= THRESHOLD:
            if _numbers(best.question) != _numbers(question) or bool(NEG.search(best.question)) != bool(NEG.search(question)):
                stats["rejected_guard"] += 1
            else:
                best.hits += 1
                db.commit()
                stats["l3_hits"] += 1
                return {"answer": best.answer, "sources": best.sources, "layer": "L3-semantic", "similarity": round(best_sim, 4),
                        "entry_id": best.id, "matched_question": best.question}
    stats["misses"] += 1
    return None


def store(db: Session, question: str, answer: str, *, category: str, sources: list[dict[str, Any]], verified: bool, ttl_days: float = 7,
          scope: str = "global") -> None:
    if not verified or not answer:
        return
    try:
        emb = _embed(question)
    except Exception:
        emb = None
    db.add(SemanticCacheEntry(scope=scope, category=category, question=question, question_norm=norm(question), answer=answer,
                              sources=sources[:10], verified=True, embedding=emb[1] if emb else [], embedding_model=emb[0] if emb else "",
                              expires_at=datetime.now(UTC) + timedelta(days=ttl_days)))
    db.flush()
    stats["stored"] += 1
    n = db.scalar(select(func.count(SemanticCacheEntry.id))) or 0
    if n > MAX_ENTRIES:
        cutoff = db.scalars(select(SemanticCacheEntry.id).order_by(SemanticCacheEntry.id.desc()).offset(MAX_ENTRIES).limit(1)).first()
        if cutoff:
            db.query(SemanticCacheEntry).filter(SemanticCacheEntry.id <= cutoff).delete(synchronize_session=False)
    db.commit()


def purge_expired(db: Session) -> int:
    n = db.query(SemanticCacheEntry).filter(SemanticCacheEntry.expires_at <= datetime.now(UTC)).delete(synchronize_session=False)
    db.commit()
    return n
