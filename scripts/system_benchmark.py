"""DAEMON HYPERINTELLIGENCE system benchmark — 13 representative scenarios against a live server and real local models.

    python scripts/system_benchmark.py            # ~15 min on a 4-vCPU CPU-only host

Per scenario: accuracy / completion, latency (p50/p95), server RSS peak, server CPU seconds, network bytes (from the
server's own HTTP telemetry), tokens and cost (from llm_calls). Fresh database per run (shares the Independence Test
setup). Results: docs/benchmarks/system-<UTC timestamp>.json. Every number is measured; nothing is estimated except
where a field says so (energy).
"""
from __future__ import annotations

import json
import os
import signal
import sqlite3
import statistics
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import independence_test as it  # noqa: E402 - reuse server/setup helpers

ROOT = it.ROOT
OUT = ROOT / "docs" / "benchmarks"


class Probe:
    """Samples the server process (RSS, CPU time) and reads its network/token counters around a scenario."""

    def __init__(self, srv: it.Server, c, work: Path):
        self.pid, self.c, self.work = srv.proc.pid, c, work
        self._stop = threading.Event()
        self.peak = 0

    def _rss(self) -> int:
        try:
            for line in Path(f"/proc/{self.pid}/status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
        except OSError:
            pass
        return 0

    def _cpu(self) -> float:
        f = Path(f"/proc/{self.pid}/stat").read_text().rsplit(")", 1)[1].split()
        return (int(f[11]) + int(f[12])) / os.sysconf("SC_CLK_TCK")

    def _net(self) -> int:
        return sum(h["bytes_in"] + h["bytes_out"] for h in self.c.get("/api/control/overview").json()["network"]["hosts"])

    def _tokens(self) -> tuple[int, float]:
        con = sqlite3.connect(self.work / "daemon.db")
        r = con.execute("SELECT COALESCE(SUM(input_tokens+output_tokens),0), COALESCE(SUM(cost_usd),0) FROM llm_calls WHERE status='ok'").fetchone()
        con.close()
        return int(r[0]), float(r[1])

    def __enter__(self):
        self.cpu0, self.net0, (self.tok0, self.cost0) = self._cpu(), self._net(), self._tokens()
        self.peak = self._rss()

        def loop():
            while not self._stop.wait(0.25):
                self.peak = max(self.peak, self._rss())
        self.t = threading.Thread(target=loop, daemon=True)
        self.t.start()
        self.t0 = time.monotonic()
        return self

    def __exit__(self, *a):
        self._stop.set()
        self.t.join()
        tok, cost = self._tokens()
        self.result = {"wall_s": round(time.monotonic() - self.t0, 1), "server_rss_peak_mb": round(self.peak / 1e6), "server_cpu_s": round(self._cpu() - self.cpu0, 1),
                       "network_bytes": self._net() - self.net0, "tokens": tok - self.tok0, "cost_usd": round(cost - self.cost0, 6)}


def lat(xs: list[float]) -> dict[str, Any]:
    import math

    s = sorted(xs)
    return {"p50_ms": round(statistics.median(s)), "p95_ms": round(s[min(len(s) - 1, math.ceil(len(s) * 0.95) - 1)]),
            "all_ms": [round(x) for x in s] if len(s) <= 5 else None} if s else {}


ONLY = [x.strip() for x in os.getenv("SYSBENCH_ONLY", "").split(",") if x.strip()]


def want(n: str) -> bool:
    return not ONLY or n in ONLY


def scenario(results: list, name: str, srv, c, work, fn) -> None:
    if not want(name.split()[0]):
        return
    print(f"▶ {name}", flush=True)
    try:
        with Probe(srv, c, work) as p:
            r = fn()
        row = {"scenario": name, **r, **p.result}
    except Exception as e:  # a failing scenario is recorded, not hidden
        row = {"scenario": name, "error": f"{type(e).__name__}: {e}"[:300], "completion": 0}
    print("   ", json.dumps(row)[:300], flush=True)
    results.append(row)


def timed(fn):
    t = time.monotonic()
    r = fn()
    return r, (time.monotonic() - t) * 1000


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="sysbench-"))
    it.setup(work)
    results: list[dict[str, Any]] = []
    srv = it.Server(work, DAEMON_PREWARM="0").start()
    c = it.client(*it.ADMIN)
    try:
        def s1():
            cases = [("What is 17*23+4?", "395"), ("25% of 480", "120"), ("100 SEK excluding 25% VAT", "125"),
                     ("How many days between 2026-01-01 and 2026-03-01?", "59"), ("Convert 10 km to miles", "6.2137 mi"), ("2^10", "1024")]
            ok, ls, calls = 0, [], 0
            for q, want in cases:
                r, ms = timed(lambda q=q: c.post("/api/ai/ask", json={"question": q}).json())
                ok += r.get("answer") == want
                calls += r.get("model_calls", 1)
                ls.append(ms)
            return {"cases": len(cases), "accuracy": round(ok / len(cases), 3), "model_calls": calls, **lat(ls)}
        scenario(results, "1 deterministic tasks", srv, c, work, s1)

        def s2():
            cases = [("Arrived broken and two weeks late.", "negative"), ("Works perfectly, love it!", "positive"), ("It is a lamp.", "neutral")]
            ok, ls = 0, []
            for t, want in cases:
                r, ms = timed(lambda t=t: c.post("/api/ai/classify", json={"text": t, "labels": ["positive", "negative", "neutral"], "cache": False}))
                ok += r.status_code == 200 and r.json().get("label") == want
                ls.append(ms)
            return {"cases": len(cases), "accuracy": round(ok / len(cases), 3), "model": "eco (local)", **lat(ls)}
        scenario(results, "2 simple tasks, small local model", srv, c, work, s2)

        def s3():
            cases = [("A lantern costs 240 SEK including 25% VAT. A competitor sells it for 180 SEK excluding VAT. How much cheaper is the competitor "
                      "for a consumer, including VAT? End with the number.", 15),
                     ("A box holds 12 items. How many boxes are needed for 50 items? End with the number.", 5)]
            ok, ls = 0, []
            for q, want in cases:
                r, ms = timed(lambda q=q: c.post("/api/ai/ask", json={"question": q, "strategy": "model_deep"}).json())
                ok += it.last_number(r.get("answer") or "") == want
                ls.append(ms)
            return {"cases": len(cases), "accuracy": round(ok / len(cases), 3), "model": it.MODELS["deep"], **lat(ls)}
        scenario(results, "3 complex reasoning, local reasoning model", srv, c, work, s3)

        def s4():
            out = {}
            r1, ms1 = timed(lambda: c.post("/api/research", json={"query": "What is llama.cpp?", "depth": "quick"}).json())
            r2, ms2 = timed(lambda: c.post("/api/research", json={"query": "Recent research on quantization of large language models", "depth": "standard"}).json())
            r3, ms3 = timed(lambda: c.post("/api/research", json={"query": "What is llama.cpp?", "depth": "quick"}).json())
            out.update({"quick": {"status": r1.get("status"), "sources": len(r1.get("sources", [])), "ms": round(ms1)},
                        "standard": {"status": r2.get("status"), "sources": len(r2.get("sources", [])), "kind": r2.get("answer_kind"), "ms": round(ms2)},
                        "repeat_quick_cached": {"cached": r3.get("cached"), "ms": round(ms3)}})
            out["completion"] = round(sum(x.get("status") == "completed" for x in (r1, r2)) / 2, 3)
            return out
        scenario(results, "4 internet research (quick, standard, cached repeat)", srv, c, work, s4)

        def s5():
            r, ms = timed(lambda: c.post("/api/gsus/runs", json={"objective": "Evaluate the winter commuter pannier and convene a council"}).json())
            return {"completion": 1 if r.get("status") == "completed" else 0, "steps": len(r.get("steps", [])), "ms": round(ms)}
        scenario(results, "5 multi-agent workflow (G-sus)", srv, c, work, s5)

        def s6():
            docs = {"lantern": "Solar panels charge the camping lantern during the day so it lights the tent at night.",
                    "pannier": "The waterproof bicycle pannier clips onto the rear rack with two hooks.",
                    "buns": "Cinnamon buns are baked with cardamom dough and pearl sugar."}
            for k, t in docs.items():
                c.post("/api/archive/text", json={"title": k, "text": t, "evidence_class": "historical_fact"})
            qs = [("sun-powered light for sleeping outdoors", "lantern"), ("bag that attaches to a bike", "pannier"), ("sweet pastry with spice", "buns")]
            ok, ls = 0, []
            for q, want in qs:
                r, ms = timed(lambda q=q: c.post("/api/archive/search", json={"query": q, "mode": "semantic", "k": 1}).json().get("results", []))
                ok += bool(r) and want in json.dumps(r[0]).lower()
                ls.append(ms)
            return {"cases": len(qs), "top1_accuracy": round(ok / len(qs), 3), **lat(ls)}
        scenario(results, "6 semantic retrieval (no shared keywords)", srv, c, work, s6)

        def s7():
            para = ("Section {i}. The supplier delivered {i} pallets of lanterns; inspection found {j} defects. Logistics notes: route {i} via Gothenburg, "
                    "customs code 9405.40, battery class LiFePO4. ")
            text = "".join(para.format(i=i, j=i % 7) for i in range(9000))  # synthetic test document (~1.6 MB), clearly not real data
            r, ms = timed(lambda: c.post("/api/archive/text", json={"title": "synthetic large document", "text": text, "evidence_class": "unclassified"}).json())
            s, ms2 = timed(lambda: c.post("/api/archive/search", json={"query": "inspection defects route 4321", "k": 3}).json().get("results", []))
            return {"bytes": len(text), "ingest_ms": round(ms), "chunks": r.get("chunk_count") or r.get("chunks"), "search_ms": round(ms2),
                    "completion": 1 if r.get("status") in ("ready", "processed", None) and s else 0}
        scenario(results, "7 large document ingest + search", srv, c, work, s7)

        def s8():
            paths = ["/api/ai/status", "/api/agents", "/api/approvals?status=pending"] * 10
            asks = ["What is 17*23+4?", "25% of 480"] * 10

            def call(i):
                t = time.monotonic()
                r = c.get(paths[i]) if i < len(paths) else c.post("/api/ai/ask", json={"question": asks[i - len(paths)]})
                return r.status_code, (time.monotonic() - t) * 1000
            with ThreadPoolExecutor(16) as ex:
                res = list(ex.map(call, range(len(paths) + len(asks))))
            return {"requests": len(res), "concurrency": 16, "errors": sum(s >= 400 for s, _ in res), **lat([ms for _, ms in res])}
        scenario(results, "8 high concurrency (50 mixed requests, 16 parallel)", srv, c, work, s8)

        def s9():
            c.patch("/api/daemon/settings", json={"profile": "LOW_MEMORY"})
            ok = 0
            for q in ("Classify: 'great product' as positive or negative", "Write a one-line slogan for a lantern"):
                r = c.post("/api/ai/ask", json={"question": q})
                ok += r.status_code == 200 and bool(r.json().get("answer"))
            time.sleep(6)  # one telemetry tick enforces the mode's residency
            resident = c.get("/api/control/overview").json()["intelligence"]["resident_models"]
            c.patch("/api/daemon/settings", json={"profile": "BALANCED"})
            return {"completion": round(ok / 2, 3), "resident_models_after": len(resident), "limit": 1}
        scenario(results, "9 low-memory operation (LOW_MEMORY profile)", srv, c, work, s9)

        def s10():
            c.patch("/api/daemon/settings", json={"offline_mode": True})
            a = c.post("/api/ai/ask", json={"question": "25% of 480"}).json()
            b = c.post("/api/ai/ask", json={"question": "What is the latest version of llama.cpp?"}).json()
            r = c.post("/api/research", json={"query": "brand new topic for offline check", "depth": "quick"}).json()
            c.patch("/api/daemon/settings", json={"offline_mode": False})
            return {"deterministic_answer": a.get("answer"), "current_question_strategy": b["plan"]["strategy"], "research_status": r.get("status"),
                    "completion": 1 if a.get("answer") == "120" and b["plan"]["strategy"] == "archive" and r.get("status") == "offline" else 0,
                    "note": "policy-level offline; OS-level network isolation is Independence Test B"}
        scenario(results, "10 offline operation", srv, c, work, s10)
    finally:
        srv.stop()

    # 11 provider failure: an external provider that fails (invalid key) must fall back to local, not fail the request
    if not want("11"):
        return _write(work, results)
    srv = it.Server(work, DAEMON_PREWARM="0", ANTHROPIC_API_KEY="sk-ant-invalid-key-for-failure-test").start()
    c = it.client(*it.ADMIN)
    try:
        def s11():
            c.patch("/api/daemon/settings", json={"profile": "DEEP"})  # DEEP tries the external provider first
            r, ms = timed(lambda: c.post("/api/ai/generate", json={"prompt": "Say hello in five words.", "tier": "standard", "max_tokens": 30}).json())
            c.patch("/api/daemon/settings", json={"profile": "BALANCED"})
            att = [f"{a['provider']}:{a['status']}" for a in r.get("attempts", [])]
            return {"served_by": r.get("provider"), "attempts": att, "ms": round(ms),
                    "completion": 1 if r.get("provider") == "local" and any(x.startswith("anthropic:") and not x.endswith(":ok") for x in att) else 0}
        scenario(results, "11 provider failure → local fallback", srv, c, work, s11)
    finally:
        srv.stop()

    # 12 network failure: all outbound traffic goes to a dead proxy
    srv = it.Server(work, DAEMON_PREWARM="0", HTTPS_PROXY="http://127.0.0.1:9", HTTP_PROXY="http://127.0.0.1:9", https_proxy="http://127.0.0.1:9").start()
    c = it.client(*it.ADMIN)
    try:
        def s12():
            r, ms = timed(lambda: c.post("/api/research", json={"query": "network failure probe topic xyz", "depth": "standard", "force_refresh": True}).json())
            a = c.post("/api/ai/ask", json={"question": "25% of 480"}).json()
            return {"research_status": r.get("status"), "errors": (r.get("stats") or {}).get("errors", [])[:3], "ms": round(ms),
                    "local_still_works": a.get("answer") == "120",
                    "completion": 1 if r.get("status") == "insufficient_evidence" and a.get("answer") == "120" else 0}
        scenario(results, "12 network failure (dead proxy)", srv, c, work, s12)
    finally:
        srv.stop()

    # 13 recovery: crash, restart, first answer
    srv = it.Server(work, DAEMON_PREWARM="0").start()
    c = it.client(*it.ADMIN)
    srv.proc.send_signal(signal.SIGKILL)
    srv.proc.wait()
    t0 = time.monotonic()
    srv = it.Server(work, DAEMON_PREWARM="0").start()
    ready = (time.monotonic() - t0) * 1000
    c = it.client(*it.ADMIN)
    try:
        def s13():
            r, ms = timed(lambda: c.post("/api/ai/ask", json={"question": "Write a one-line slogan for a lantern"}).json())
            return {"restart_to_ready_ms": round(ready), "first_model_answer_ms": round(ms), "completion": 1 if r.get("answer") else 0}
        scenario(results, "13 recovery after crash (SIGKILL)", srv, c, work, s13)
    finally:
        srv.stop()

    return _write(work, results)


def _write(work: Path, results: list) -> int:
    hw = it.json.loads(it.subprocess.run([sys.executable, "-c", "import json,sys;sys.path.insert(0,'.');from app.daemon import hardware;print(json.dumps(hardware._snapshot()))"],
                                         cwd=it.BACKEND, capture_output=True, text=True, env=it.env_for(work)).stdout)
    out = {"ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "hardware": {"cpu": hw["cpu"]["model"], "cores": hw["cpu"]["usable_cores"],
           "ram_gb": round(hw["ram_total_bytes"] / 1e9, 1), "gpu": hw["gpus"] or "none"}, "models": it.MODELS, "scenarios": results}
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"system-{out['ran_at'].replace(':', '')}.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"\nwritten {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
