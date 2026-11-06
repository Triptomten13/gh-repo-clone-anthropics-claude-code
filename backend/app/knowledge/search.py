"""Hybrid retrieval (BM25 + vectors, reciprocal-rank fusion) with metadata filters and citations,
plus grounded answering that never cites a source it did not retrieve."""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.providers import cosine, tokenize
from ..models import Document, DocumentChunk, EntityMention
from ..security import untrusted
from .process import embedder

RRF_K = 60
MIN_COSINE = {"local-hash-256": 0.2, "ollama": 0.35, "gguf": 0.5}  # relevance floors per embedder family (tuned by evals/datasets/retrieval.json)
EVIDENCE_LABEL = {"historical_fact": "historical fact", "primary_source": "primary source", "religious_interpretation": "religious interpretation",
                  "philosophical_theory": "philosophical theory", "scholarly_hypothesis": "scholarly hypothesis", "speculative": "speculative claim",
                  "fiction_canon": "fictional canon (internal worldbuilding)", "unclassified": "unclassified source"}


def _candidates(db: Session, filters: dict[str, Any]) -> list[tuple[DocumentChunk, Document]]:
    q = select(DocumentChunk, Document).join(Document, Document.id == DocumentChunk.document_id).where(Document.status == "ready")
    if filters.get("doc_type"):
        q = q.where(Document.doc_type == filters["doc_type"])
    if filters.get("evidence_class"):
        ev = filters["evidence_class"]
        q = q.where(Document.evidence_class.in_(ev if isinstance(ev, list) else [ev]))
    if filters.get("document_ids"):
        q = q.where(Document.id.in_(filters["document_ids"]))
    rows = list(db.execute(q).all())
    if filters.get("tag"):
        rows = [r for r in rows if filters["tag"] in (r[1].tags or [])]
    return rows


def _snippet(text: str, terms: set[str], width: int = 260) -> str:
    low = text.lower()
    pos = min((low.find(t) for t in terms if t in low), default=0)
    start = max(0, pos - width // 3)
    s = text[start:start + width].replace("\n", " ")
    return ("…" if start else "") + s + ("…" if start + width < len(text) else "")


def _hit(c: DocumentChunk, d: Document, score: float, terms: set[str]) -> dict[str, Any]:
    return {"chunk_id": c.id, "document_id": d.id, "document_uid": d.uid, "title": d.title, "ordinal": c.ordinal, "page": c.page,
            "start_char": c.start_char, "end_char": c.end_char, "snippet": _snippet(c.text, terms), "text": c.text,
            "score": round(score, 5), "evidence_class": d.evidence_class, "evidence_label": EVIDENCE_LABEL[d.evidence_class],
            "source": d.source, "source_url": d.source_url, "author": d.author, "created_date": d.created_date,
            "injection_risk": c.injection_risk, "citation": f"[{d.uid[:8]}§{c.ordinal}]"}


def search(db: Session, query: str, k: int = 8, mode: str = "hybrid", filters: dict[str, Any] | None = None, user: Any = None) -> list[dict[str, Any]]:
    from . import index

    ix = index.get(db)
    if ix is None:
        return _search_scan(db, query, k, mode, filters)
    return _search_indexed(db, ix, query, k, mode, filters or {})


def _allowed_docs(db: Session, filters: dict[str, Any]) -> list[int]:
    """Document visibility is decided live in SQL on every query (status, deletion, filters) — never cached."""
    q = select(Document.id, Document.tags).where(Document.status == "ready")
    if filters.get("doc_type"):
        q = q.where(Document.doc_type == filters["doc_type"])
    if filters.get("evidence_class"):
        ev = filters["evidence_class"]
        q = q.where(Document.evidence_class.in_(ev if isinstance(ev, list) else [ev]))
    if filters.get("document_ids"):
        q = q.where(Document.id.in_(filters["document_ids"]))
    return [i for i, tags in db.execute(q).all() if not filters.get("tag") or filters["tag"] in (tags or [])]


def _search_indexed(db: Session, ix: Any, query: str, k: int, mode: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
    import numpy as np

    from . import index

    if not query.strip():
        return []
    mask = ix.alive & np.isin(ix.doc, np.asarray(_allowed_docs(db, filters), dtype=np.int64))
    if not mask.any():
        return []
    terms = set(tokenize(query))
    ranked: dict[int, float] = {}
    if mode in ("hybrid", "keyword"):
        bm = sorted(index.bm25(ix, mask, terms), key=lambda x: (x[0], int(ix.ids[x[1]])), reverse=True)
        for r, (_s, i) in enumerate(bm):
            ranked[i] = ranked.get(i, 0) + 1 / (RRF_K + r + 1)
    if mode in ("hybrid", "semantic"):
        model_id, embed = embedder()
        qv = embed([query], kind="query")[0]
        floor = MIN_COSINE.get(model_id.split(":")[0], 0.3)
        for r, (_s, i) in enumerate(index.vector(ix, mask, model_id, qv, floor)):
            ranked[i] = ranked.get(i, 0) + 1 / (RRF_K + r + 1)
    top = sorted(ranked.items(), key=lambda x: x[1], reverse=True)[:k]
    if not top:
        return []
    ids = [int(ix.ids[i]) for i, _ in top]
    rows = {c.id: (c, d) for c, d in db.execute(select(DocumentChunk, Document).join(Document, Document.id == DocumentChunk.document_id)
                                                .where(DocumentChunk.id.in_(ids))).all()}
    return [_hit(*rows[cid], score, terms) for cid, (_i, score) in zip(ids, top, strict=True) if cid in rows]


def _search_scan(db: Session, query: str, k: int = 8, mode: str = "hybrid", filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Reference implementation (and fallback without numpy): loads and scores every candidate chunk."""
    rows = _candidates(db, filters or {})
    if not rows or not query.strip():
        return []
    qtok = tokenize(query)
    terms = set(qtok)
    ranked: dict[int, float] = {}
    if mode in ("hybrid", "keyword"):
        docs_tok = [tokenize(c.text) for c, _ in rows]
        n = len(rows)
        avg = sum(len(t) for t in docs_tok) / n or 1
        df = Counter(t for toks in docs_tok for t in set(toks))
        bm = []
        for i, toks in enumerate(docs_tok):
            tf = Counter(toks)
            s = 0.0
            for t in terms:
                if tf[t]:
                    idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                    s += idf * tf[t] * 2.2 / (tf[t] + 1.2 * (0.25 + 0.75 * len(toks) / avg))
            bm.append((s, i))
        for r, (_s, i) in enumerate(sorted((x for x in bm if x[0] > 0), reverse=True)):
            ranked[i] = ranked.get(i, 0) + 1 / (RRF_K + r + 1)
    if mode in ("hybrid", "semantic"):
        model_id, embed = embedder()
        qv = embed([query], kind="query")[0]
        vs = [(cosine(qv, c.embedding) if c.embedding_model == model_id else 0.0, i) for i, (c, _) in enumerate(rows)]
        floor = MIN_COSINE.get(model_id.split(":")[0], 0.3)  # below this a match is noise, not relevance
        for r, (_s, i) in enumerate(sorted((x for x in vs if x[0] >= floor), reverse=True)[:50]):
            ranked[i] = ranked.get(i, 0) + 1 / (RRF_K + r + 1)
    return [_hit(*rows[i], score, terms) for i, score in sorted(ranked.items(), key=lambda x: x[1], reverse=True)[:k]]


def related_documents(db: Session, doc_id: int, k: int = 5) -> list[dict[str, Any]]:
    mine = {m.entity_id for m in db.scalars(select(EntityMention).where(EntityMention.document_id == doc_id)).all()}
    if not mine:
        return []
    scores: Counter = Counter()
    for m in db.scalars(select(EntityMention).where(EntityMention.entity_id.in_(mine), EntityMention.document_id != doc_id)).all():
        scores[m.document_id] += 1
    out = []
    for did, shared in scores.most_common(k):
        d = db.get(Document, did)
        if d and d.status == "ready":
            out.append({"document_id": did, "title": d.title, "shared_entities": shared, "evidence_class": d.evidence_class})
    return out


def grounded_answer(db: Session, question: str, k: int = 6, filters: dict[str, Any] | None = None, llm: Any | None = None,
                    mode_prompt: str = "", strictness: float = 0.8) -> dict[str, Any]:
    """Answer only from retrieved archive passages. Without an LLM: extractive answer grouped by evidence class.
    With an LLM: sources are wrapped as untrusted data; every [n] citation is verified to exist."""
    hits = search(db, question, k=k, filters=filters)
    if not hits:
        return {"answer": "The Archive holds no passages relevant to this question. Nothing will be invented to fill the gap.",
                "citations": [], "method": "extractive", "grounding": {"supported": False, "reason": "no sources"}}
    cites = [{"n": i + 1, **{k_: h[k_] for k_ in ("chunk_id", "document_id", "document_uid", "title", "ordinal", "page", "evidence_class",
                                                   "evidence_label", "source", "source_url", "snippet", "injection_risk")}} for i, h in enumerate(hits)]
    if llm is None:
        by_class: dict[str, list[str]] = {}
        for c, h in zip(cites, hits, strict=True):
            warn = " ⚠ contains instruction-like text — shown as data, not followed" if h["injection_risk"] else ""
            by_class.setdefault(h["evidence_label"], []).append(f"“{h['snippet'].strip()}” [{c['n']}]{warn}")
        parts = [f"{label.capitalize()}:\n" + "\n".join(f"  • {s}" for s in items) for label, items in by_class.items()]
        return {"answer": "From the Archive (quoted, not paraphrased):\n" + "\n".join(parts), "citations": cites, "method": "extractive",
                "grounding": {"supported": True, "cited": len(cites), "invalid_citations": []}}
    sources = "\n".join(untrusted.wrap(h["text"], f"{i + 1}", h["title"], h["evidence_label"]) for i, h in enumerate(hits))
    system = (f"{mode_prompt}\n{untrusted.GUARD}\nAnswer using only the numbered sources. Cite every factual sentence as [n]. "
              "State each source's evidentiary status (e.g. 'a religious interpretation holds…', 'in the internal canon…'). "
              "If the sources do not answer the question, say so. Never invent quotations, references or dates."
              + (" Be strict: omit anything not directly supported." if strictness >= 0.7 else ""))
    res = llm(system, f"Question: {question}\n\nSources:\n{sources}")
    used = {int(n) for n in re.findall(r"\[(\d+)\]", res.text)}
    invalid = sorted(n for n in used if n < 1 or n > len(cites))
    return {"answer": res.text, "citations": [c for c in cites if c["n"] in used] or cites, "method": "llm", "llm_result": res,
            "grounding": {"supported": bool(used) and not invalid, "cited": len(used - set(invalid)), "invalid_citations": invalid,
                          "uncited_answer": not used}}
