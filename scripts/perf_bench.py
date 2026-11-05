"""Repeatable performance measurement for DAEMON HYPERINTELLIGENCE optimisation work.

    python scripts/perf_bench.py --label baseline        # before a change
    python scripts/perf_bench.py --label after-<change>  # after; compare with --compare baseline

Runs in-process against a COPY of a database (default backend/rocky.db) with synthetic llm_call rows added to that copy
only (labelled purpose='perf-synthetic'), so dashboard queries are measured at a realistic table size. Measures, per
endpoint: latency p50/p95 over N calls, SQL statements per request; plus process RSS and model load/swap behaviour.
Results: docs/perf/<label>.json. Nothing here is estimated — every number is a measurement on this machine.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import statistics
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
OUT = ROOT / "docs" / "perf"


def rss_mb() -> float:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return round(int(line.split()[1]) / 1024, 1)
    return 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--db", default=str(BACKEND / "rocky.db"))
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--synthetic-calls", type=int, default=20000)
    ap.add_argument("--models", action="store_true", help="also measure local model load/swap churn (slow, real models)")
    ap.add_argument("--compare", help="label of an earlier run to compare against")
    a = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="perf-"))
    db = tmp / "perf.db"
    shutil.copy(a.db, db)
    os.environ.update({"DATABASE_URL": f"sqlite:///{db}", "LLM_ENABLED": "true", "SECRET_KEY": "perf-secret",
                       "ARCHIVE_DIR": str(tmp / "archive"), "API_RATE_PER_MIN": "1000000", "RESUME_TASKS_ON_START": "false"})
    for k in [k for k in os.environ if k.startswith(("ANTHROPIC_", "OLLAMA_"))]:
        os.environ.pop(k)
    sys.path.insert(0, str(BACKEND))
    import subprocess

    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, check=True, capture_output=True)

    from fastapi.testclient import TestClient
    from sqlalchemy import event

    from app import db as dbmod
    from app.main import app
    from app.models import LLMCall, User

    # synthetic rows, this temp copy only
    s = dbmod.SessionLocal()
    now = datetime.now(UTC)
    rnd = random.Random(7)
    s.bulk_save_objects([LLMCall(created_at=now - timedelta(minutes=rnd.randint(0, 60 * 24 * 29)), agent_id=rnd.choice(["ceo", "gsus", "brand_studio", ""]),
                                 purpose="perf-synthetic", provider=rnd.choice(["local", "local", "anthropic"]), model="m", tier=rnd.choice(["fast", "standard", "deep"]),
                                 status=rnd.choice(["ok", "ok", "ok", "unavailable", "not_configured"]), input_tokens=rnd.randint(50, 3000),
                                 output_tokens=rnd.randint(5, 800), cost_usd=rnd.random() / 100, latency_ms=rnd.randint(50, 9000),
                                 locality=rnd.choice(["local", "external"]), workflow=rnd.choice(["chat", "reason", "classify"]))
                         for _ in range(a.synthetic_calls)])
    s.commit()
    email = "perf@example.com"
    if not s.query(User).filter(User.email == email).first():
        from app.security.auth import hash_password

        s.add(User(email=email, password_hash=hash_password("perf-password-123"), role="admin"))
        s.commit()
    s.close()

    stmts = {"n": 0}

    @event.listens_for(dbmod.engine, "before_cursor_execute")
    def _count(*_args, **_kw):  # pragma: no cover - instrumentation
        stmts["n"] += 1

    results: dict = {"label": a.label, "ran_at": now.isoformat(), "n": a.n, "synthetic_llm_calls": a.synthetic_calls, "endpoints": {}}
    endpoints = [("GET", "/api/ai/status"), ("GET", "/api/system/status"), ("GET", "/api/approvals?status=pending"), ("GET", "/api/overview"),
                 ("GET", "/api/daemon/costs?days=30"), ("GET", "/api/daemon/library"), ("GET", "/api/ai/health"), ("GET", "/api/agents"),
                 ("GET", "/api/auth/me"), ("POST", "/api/archive/search"), ("POST", "/api/daemon/proposals/generate")]
    with TestClient(app) as c:
        tok = c.post("/api/auth/login", json={"email": email, "password": "perf-password-123"}).json()["token"]
        c.headers["Authorization"] = f"Bearer {tok}"
        results["rss_mb_after_start"] = rss_mb()
        for method, path in endpoints:
            lat, q, status = [], [], None
            for i in range(a.n):
                stmts["n"] = 0
                t = time.perf_counter()
                r = c.post(path, json={"query": "solar lantern charging", "k": 8}) if method == "POST" else c.get(path)
                lat.append((time.perf_counter() - t) * 1000)
                q.append(stmts["n"])
                status = r.status_code
                if i == 0:
                    first = lat[0]
            lat_sorted = sorted(lat)
            results["endpoints"][f"{method} {path}"] = {
                "status": status, "first_ms": round(first, 1), "p50_ms": round(statistics.median(lat), 1),
                "p95_ms": round(lat_sorted[int(len(lat) * 0.95) - 1], 1), "sql_per_request": round(statistics.mean(q), 1)}
            print(f"{method:4} {path:42} p50 {results['endpoints'][f'{method} {path}']['p50_ms']:8.1f} ms  "
                  f"p95 {results['endpoints'][f'{method} {path}']['p95_ms']:8.1f} ms  sql {statistics.mean(q):6.1f}  [{status}]", flush=True)
        # what one page view costs: the shell's three status calls
        shell = ["/api/system/status", "/api/approvals?status=pending", "/api/ai/status"]
        results["shell_page_view_ms"] = round(sum(results["endpoints"][f"GET {p}"]["p50_ms"] for p in shell), 1)
        results["shell_page_view_sql"] = round(sum(results["endpoints"][f"GET {p}"]["sql_per_request"] for p in shell), 1)
        results["rss_mb_after_endpoints"] = rss_mb()

    if a.models:
        from app.daemon import runtime

        p = runtime.get_local()
        seq = ["chat", "deep", "chat", "eco", "chat", "deep", "eco"]
        t0 = time.perf_counter()
        loads_before = getattr(p, "load_count", None)
        timings = []
        for slot in seq:
            t = time.perf_counter()
            # JSON-schema calls never think, so this measures loading/swapping, not reasoning time
            p.complete(model=slot, system="Reply in JSON.", prompt="Say ok.", effort="low", max_tokens=12,
                       schema={"type": "object", "properties": {"ok": {"type": "string"}}, "required": ["ok"]})
            timings.append({"slot": slot, "ms": round((time.perf_counter() - t) * 1000)})
        results["model_churn"] = {"sequence": seq, "total_ms": round((time.perf_counter() - t0) * 1000), "calls": timings,
                                  "loads": (getattr(p, "load_count", 0) - (loads_before or 0)) if loads_before is not None else "not instrumented",
                                  "rss_mb": rss_mb()}
        print("model churn", results["model_churn"], flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{a.label}.json").write_text(json.dumps(results, indent=2))
    print(f"shell page view: {results['shell_page_view_ms']} ms, {results['shell_page_view_sql']} SQL; RSS {results['rss_mb_after_endpoints']} MB")
    if a.compare and (OUT / f"{a.compare}.json").exists():
        base = json.loads((OUT / f"{a.compare}.json").read_text())
        print(f"\nCOMPARE {a.compare} → {a.label}")
        for k, v in results["endpoints"].items():
            b = base["endpoints"].get(k)
            if b:
                print(f"  {k:48} p50 {b['p50_ms']:8.1f} → {v['p50_ms']:8.1f} ms   sql {b['sql_per_request']:6.1f} → {v['sql_per_request']:6.1f}")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
