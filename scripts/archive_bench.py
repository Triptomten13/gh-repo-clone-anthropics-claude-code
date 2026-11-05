"""Archive retrieval benchmark: latency of knowledge.search at realistic Archive sizes.

    python scripts/archive_bench.py --label archive-baseline
    python scripts/archive_bench.py --label archive-after-index --compare archive-baseline

Builds a TEMPORARY SQLite database (never the real one) with synthetic documents: ~800-character chunks drawn from a
fixed vocabulary and 768-dimensional unit vectors (the size nomic-embed-text produces), seeded so every run sees the
same data. The query embedder is replaced by a precomputed vector, so the numbers are RETRIEVAL cost only — the real
query embedding (~0.1–0.3 s on this CPU with nomic) comes on top and is unchanged by index work.
Measures per size: first search after a change (cold), warm p50/p95 over the query set, RSS; and records the top-k
chunk ids so an optimisation can be checked for identical rankings (--compare reports any difference).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
OUT = ROOT / "docs" / "perf"
DIMS = 768


def rss_mb() -> float:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return round(int(line.split()[1]) / 1024, 1)
    return 0.0


def unit(rng: random.Random) -> list[float]:
    v = [rng.gauss(0, 1) for _ in range(DIMS)]
    n = math.sqrt(sum(x * x for x in v))
    return [round(x / n, 6) for x in v]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--sizes", default="2000,10000,20000")
    ap.add_argument("--queries", type=int, default=12)
    ap.add_argument("--compare", default="")
    a = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="archive-bench-")
    try:
        return run(a, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run(a: argparse.Namespace, tmp: str) -> int:
    os.environ.update({"DATABASE_URL": f"sqlite:///{tmp}/bench.db", "TELEMETRY_DISABLED": "1", "DAEMON_PREWARM": "0", "SECRET_KEY": "bench"})
    sys.path.insert(0, str(BACKEND))
    from sqlalchemy import insert

    from app.db import Base, SessionLocal, engine
    from app.knowledge import search as S
    from app.models import Document, DocumentChunk

    Base.metadata.create_all(engine)
    rng = random.Random(20261105)
    vocab = [f"w{i}" for i in range(6000)] + ["babylon", "jerusalem", "exile", "temple", "covenant", "prophet", "archive", "lantern", "oracle"]
    weights = [1 / (i + 1) for i in range(len(vocab))]  # Zipf-like: a few frequent words, a long tail
    qvecs = [unit(rng) for _ in range(a.queries)]
    queries = [" ".join(rng.choices(vocab[:800], k=rng.randint(2, 4)) + [rng.choice(vocab[-9:])]) for _ in range(a.queries)]
    it = iter(range(10**9))
    S.embedder = lambda: ("gguf:bench", lambda texts, kind="query": [qvecs[next(it) % len(qvecs)] for _ in texts])  # noqa: E731

    results: dict = {"label": a.label, "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "dims": DIMS, "sizes": {}}
    have = 0
    for size in [int(x) for x in a.sizes.split(",")]:
        db = SessionLocal()
        per_doc = 50
        while have < size:
            d = Document(uid=f"bench-{have}", title=f"Bench document {have // per_doc}", doc_type="txt", content_hash=f"h{have}",
                         status="ready", evidence_class="historical_fact" if have % 3 else "primary_source")
            db.add(d)
            db.flush()
            rows = []
            for o in range(per_doc):
                words = rng.choices(vocab, weights=weights, k=120)
                rows.append({"document_id": d.id, "ordinal": o, "text": " ".join(words), "start_char": 0, "end_char": 800, "embedding": unit(rng),
                             "embedding_model": "gguf:bench", "injection_risk": False})
            db.execute(insert(DocumentChunk), rows)
            have += per_doc
        db.commit()
        db.close()
        S.__dict__.get("invalidate_index", lambda: None)()
        db = SessionLocal()
        t = time.perf_counter()
        S.search(db, queries[0], k=8)
        cold = (time.perf_counter() - t) * 1000
        lat, tops = [], {}
        for qi, q in enumerate(queries):
            it = iter(range(qi, 10**9))
            t = time.perf_counter()
            hits = S.search(db, q, k=8)
            lat.append((time.perf_counter() - t) * 1000)
            tops[q] = [h["chunk_id"] for h in hits]
        filt = []
        for q in queries[:4]:
            t = time.perf_counter()
            S.search(db, q, k=8, filters={"evidence_class": "primary_source"})
            filt.append((time.perf_counter() - t) * 1000)
        db.close()
        lat.sort()
        results["sizes"][str(size)] = {"chunks": have, "cold_first_search_ms": round(cold, 1), "p50_ms": round(statistics.median(lat), 1),
                                       "p95_ms": round(lat[max(0, math.ceil(0.95 * len(lat)) - 1)], 1),
                                       "filtered_p50_ms": round(statistics.median(filt), 1), "rss_mb": rss_mb(), "top_k": tops}
        r = results["sizes"][str(size)]
        print(f"{size:>6} chunks  cold {r['cold_first_search_ms']:>8} ms  p50 {r['p50_ms']:>8} ms  p95 {r['p95_ms']:>8} ms  "
              f"filtered p50 {r['filtered_p50_ms']:>8} ms  RSS {r['rss_mb']} MB", flush=True)

    # after a change: one new document (ORM path, like ingest) and one deleted document (the Archive delete statement)
    db = SessionLocal()
    d = Document(uid="bench-new", title="New document", doc_type="txt", content_hash="new", status="ready")
    db.add(d)
    db.flush()
    for o in range(50):
        db.add(DocumentChunk(document_id=d.id, ordinal=o, text="zanzibarite " + " ".join(rng.choices(vocab, k=119)), embedding=unit(rng),
                             embedding_model="gguf:bench"))
    db.commit()
    t = time.perf_counter()
    found = S.search(db, "zanzibarite", k=3, mode="keyword")
    add_ms = (time.perf_counter() - t) * 1000
    victim = found[0]["document_id"] if found else None
    gone = 1
    db.query(DocumentChunk).filter(DocumentChunk.document_id == 1).execution_options(archive_docs=[1]).delete()
    db.query(Document).filter(Document.id == 1).delete()
    db.commit()
    t = time.perf_counter()
    after = S.search(db, queries[0], k=50)
    del_ms = (time.perf_counter() - t) * 1000
    db.close()
    results["after_change"] = {"first_search_after_adding_50_chunks_ms": round(add_ms, 1), "new_document_found": victim == d.id,
                               "first_search_after_deleting_a_document_ms": round(del_ms, 1),
                               "deleted_document_absent": all(h["document_id"] != gone for h in after)}
    print("after change:", {k: v for k, v in results["after_change"].items()}, flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{a.label}.json").write_text(json.dumps(results, indent=1))
    if a.compare:
        base = json.loads((OUT / f"{a.compare}.json").read_text())
        print(f"\ncompared with {a.compare}:")
        for size, r in results["sizes"].items():
            b = base["sizes"].get(size)
            if not b:
                continue
            same = sum(r["top_k"].get(q) == ids for q, ids in b["top_k"].items())
            print(f"{size:>6}: p50 {b['p50_ms']} → {r['p50_ms']} ms, cold {b['cold_first_search_ms']} → {r['cold_first_search_ms']} ms, "
                  f"RSS {b['rss_mb']} → {r['rss_mb']} MB, identical top-k {same}/{len(b['top_k'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
