"""In-memory retrieval index for the Archive.

Measured reason (docs/perf/archive-baseline.json): the scan loaded, JSON-decoded and tokenised EVERY chunk on every
query — 0.45 s at 2 000 chunks, 2.6 s at 10 000, 5.9 s at 20 000, growing linearly. The index keeps, per chunk, its
id, document id, token count, BM25 postings and embedding (float32, one matrix per embedding model), so a query scores
only the postings of its own terms plus one matrix-vector product. Rankings use the same BM25 / cosine / RRF formulas
as the scan (search._search_scan stays as the fallback and as the reference in tests).

Freshness — never serve a deleted or outdated chunk:
  * every committed change to document_chunks writes a new token to system_state('archive_index') IN THE SAME
    TRANSACTION, with the documents it touched (or "full" for bulk statements);
  * a search reads that token (one primary-key lookup); if it moved, only the touched documents are re-read, or the
    index is rebuilt when the log does not reach back far enough. This works across processes (CLI, workers);
  * document visibility (status, deletion, filters) is checked live in SQL on every query, never cached;
  * updates are copy-on-write: a refreshed index is built beside the published one and swapped in, so concurrent
    searches never read a half-updated structure (tested with readers running during writes).
Memory: about dims × 4 bytes per chunk (768-dim: ~3 KB/chunk, ~61 MB for 20 000 chunks) plus postings; reported in
the Control Center. Disable with ARCHIVE_INDEX=0 (falls back to the scan).
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from typing import Any

from sqlalchemy import event, select
from sqlalchemy.orm import Session

try:  # numpy ships with the local-AI runtime; without it the scan is used
    import numpy as np
except ImportError:  # pragma: no cover - depends on the install
    np = None  # type: ignore[assignment]

KEY = "archive_index"
LOG_MAX = 200
DOCS_MAX = 500
_lock = threading.Lock()
_current: Index | None = None
stats: dict[str, Any] = {"builds": 0, "incremental_updates": 0, "hits": 0, "last_build_ms": None, "rows": 0, "live_rows": 0, "bytes": 0}


def enabled() -> bool:
    return np is not None and os.getenv("ARCHIVE_INDEX", "1") != "0"


# ------------------------------------------------------------------ write side: change tokens, in the same transaction
def _table(obj_or_mapper: Any) -> str:
    t = getattr(obj_or_mapper, "__table__", None)
    if t is None:
        t = getattr(obj_or_mapper, "local_table", None)
    return getattr(t, "name", "")


@event.listens_for(Session, "after_flush")
def _track_objects(session: Session, _ctx: Any) -> None:
    docs = session.info.setdefault("archive_docs", set())
    for o in (*session.new, *session.dirty, *session.deleted):
        if _table(o) == "document_chunks":
            docs.add(getattr(o, "document_id", None))


@event.listens_for(Session, "do_orm_execute")
def _track_bulk(state: Any) -> None:
    if (state.is_insert or state.is_update or state.is_delete) and any(_table(m) == "document_chunks" for m in state.all_mappers):
        # a bulk statement names the documents it touches via execution_options(archive_docs=[...]); otherwise: full refresh
        docs = state.execution_options.get("archive_docs")
        state.session.info.setdefault("archive_docs", set()).update(docs if docs else [None])


@event.listens_for(Session, "before_commit")
def _write_token(session: Session) -> None:
    session.flush()  # commit would flush right after this hook anyway; flushing first lets after_flush see pending chunks
    docs = session.info.pop("archive_docs", set())
    if not docs:
        return
    from ..models import SystemState

    row = session.execute(select(SystemState).where(SystemState.key == KEY).with_for_update()).scalar_one_or_none()
    value = dict(row.value) if row else {"log": []}
    token = uuid.uuid4().hex
    touched = None if None in docs or len(docs) > DOCS_MAX else sorted(docs)
    value["token"] = token
    value["log"] = (list(value.get("log") or []) + [{"t": token, "docs": touched}])[-LOG_MAX:]
    if row:
        row.value = value
    else:
        session.add(SystemState(key=KEY, value=value))
    session.flush()


@event.listens_for(Session, "after_rollback")
def _forget(session: Session) -> None:
    session.info.pop("archive_docs", None)


# ------------------------------------------------------------------ the index
class Index:
    def __init__(self, bind: str) -> None:
        self.bind = bind
        self.token: str | None = None
        self.ids = np.zeros(0, dtype=np.int64)
        self.doc = np.zeros(0, dtype=np.int64)
        self.length = np.zeros(0, dtype=np.float64)
        self.alive = np.zeros(0, dtype=bool)
        self.postings: dict[str, list[tuple[Any, Any]]] = {}  # term → segments of (row indexes, term frequencies)
        self.emb: dict[str, list[tuple[Any, Any]]] = {}  # embedding model → segments of (row indexes, float32 matrix)
        self.rows_of_doc: dict[int, list[int]] = {}

    def add(self, rows: list[Any]) -> None:
        from collections import Counter

        from ..ai.providers import tokenize

        if not rows:
            return
        base = len(self.ids)
        self.ids = np.concatenate([self.ids, np.fromiter((r.id for r in rows), dtype=np.int64, count=len(rows))])
        self.doc = np.concatenate([self.doc, np.fromiter((r.document_id for r in rows), dtype=np.int64, count=len(rows))])
        lengths, post, emb = [], {}, {}
        for j, r in enumerate(rows):
            toks = tokenize(r.text)
            lengths.append(len(toks))
            for t, n in Counter(toks).items():
                p = post.setdefault(t, ([], []))
                p[0].append(base + j)
                p[1].append(n)
            if r.embedding:
                e = emb.setdefault((r.embedding_model, len(r.embedding)), ([], []))
                e[0].append(base + j)
                e[1].append(r.embedding)
            self.rows_of_doc.setdefault(r.document_id, []).append(base + j)
        self.length = np.concatenate([self.length, np.asarray(lengths, dtype=np.float64)])
        self.alive = np.concatenate([self.alive, np.ones(len(rows), dtype=bool)])
        for t, (ix, tf) in post.items():
            self.postings.setdefault(t, []).append((np.asarray(ix, dtype=np.int32), np.asarray(tf, dtype=np.float64)))
        for (model, _dims), (ix, vecs) in emb.items():
            self.emb.setdefault(model, []).append((np.asarray(ix, dtype=np.int32), np.asarray(vecs, dtype=np.float32)))

    def clone(self) -> Index:
        """Copy-on-write: searches keep using the published index while an update is applied to a copy."""
        c = Index(self.bind)
        c.token, c.ids, c.doc, c.length, c.alive = self.token, self.ids, self.doc, self.length, self.alive.copy()
        c.postings = {t: list(segs) for t, segs in self.postings.items()}
        c.emb = {m: list(segs) for m, segs in self.emb.items()}
        c.rows_of_doc = dict(self.rows_of_doc)
        return c

    def drop_docs(self, doc_ids: list[int]) -> None:
        for d in doc_ids:
            for i in self.rows_of_doc.pop(d, []):
                self.alive[i] = False

    @property
    def nbytes(self) -> int:
        n = self.ids.nbytes + self.doc.nbytes + self.length.nbytes + self.alive.nbytes
        n += sum(a.nbytes + b.nbytes for segs in self.postings.values() for a, b in segs)
        return n + sum(a.nbytes + m.nbytes for segs in self.emb.values() for a, m in segs)


def _chunk_rows(db: Session, doc_ids: list[int] | None = None) -> list[Any]:
    from ..models import DocumentChunk as C

    q = select(C.id, C.document_id, C.text, C.embedding, C.embedding_model).order_by(C.id)
    if doc_ids is not None:
        q = q.where(C.document_id.in_(doc_ids))
    return list(db.execute(q).all())


def _token(db: Session) -> dict[str, Any]:
    from ..models import SystemState

    return db.execute(select(SystemState.value).where(SystemState.key == KEY)).scalar() or {}


def get(db: Session) -> Index | None:
    """The current index for this database, refreshed if any chunk changed since it was built."""
    global _current
    if not enabled():
        return None
    bind = str(db.get_bind().url)
    state = _token(db)
    token = state.get("token")
    with _lock:
        cur = _current
        if cur is not None and cur.bind == bind and cur.token == token:
            stats["hits"] += 1
            return cur
        t0 = time.perf_counter()
        log = state.get("log") or []
        pos = next((i for i, e in enumerate(log) if e["t"] == cur.token), None) if cur is not None and cur.bind == bind and cur.token else None
        pending = log[pos + 1:] if pos is not None else None
        dead = (1 - cur.alive.mean()) if cur is not None and len(cur.alive) else 0
        if pending is not None and all(e["docs"] is not None for e in pending) and dead < 0.3:
            docs = sorted({d for e in pending for d in e["docs"]})
            cur = cur.clone()  # never mutate the published index: concurrent searches read it without the lock
            cur.drop_docs(docs)
            cur.add(_chunk_rows(db, docs))
            cur.token = token
            _current = cur
            stats["incremental_updates"] += 1
        else:
            cur = Index(bind)
            cur.add(_chunk_rows(db))
            cur.token = token
            _current = cur
            stats["builds"] += 1
        stats.update(last_build_ms=round((time.perf_counter() - t0) * 1000, 1), rows=int(len(cur.ids)), live_rows=int(cur.alive.sum()),
                     bytes=cur.nbytes)
        return cur


def invalidate() -> None:
    global _current
    with _lock:
        _current = None


def bm25(ix: Index, mask: Any, terms: set[str]) -> list[tuple[float, int]]:
    """Same formula as the scan: statistics over the CANDIDATE rows (mask), k1 = 1.2, b = 0.75."""
    n = int(mask.sum())
    if not n:
        return []
    avg = float(ix.length[mask].sum()) / n or 1
    score: dict[int, float] = {}
    for t in terms:
        segs = ix.postings.get(t)
        if not segs:
            continue
        rows = np.concatenate([s[0] for s in segs])
        tf = np.concatenate([s[1] for s in segs])
        keep = mask[rows]
        rows, tf = rows[keep], tf[keep]
        df = len(rows)
        if not df:
            continue
        idf = np.log(1 + (n - df + 0.5) / (df + 0.5))
        s = idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * ix.length[rows] / avg))
        for r, v in zip(rows.tolist(), s.tolist(), strict=True):
            score[r] = score.get(r, 0.0) + v
    return [(v, r) for r, v in score.items() if v > 0]


def vector(ix: Index, mask: Any, model_id: str, qv: list[float], floor: float, limit: int = 50) -> list[tuple[float, int]]:
    out: list[tuple[float, int]] = []
    q = np.asarray(qv, dtype=np.float32)
    for rows, m in ix.emb.get(model_id, []):
        if m.shape[1] != len(q):
            continue  # the scan scores mismatched dimensions as 0 — below every floor
        keep = mask[rows]
        if not keep.any():
            continue
        sims = m[keep] @ q
        sel = sims >= floor
        out += zip(sims[sel].astype(np.float64).tolist(), rows[keep][sel].tolist(), strict=True)
    out.sort(key=lambda x: (x[0], int(ix.ids[x[1]])), reverse=True)
    return out[:limit]
