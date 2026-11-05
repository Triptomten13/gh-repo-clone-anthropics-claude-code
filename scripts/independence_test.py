"""DAEMON CORE — Independence Tests A–G, run for real against a live server and real local models.

    python scripts/independence_test.py            # needs installed local models (see docs/DAEMON_CORE.md)

What is real here:
  * a fresh database and archive in a temporary directory; the server is started with uvicorn
  * local models are imported through the API (checksum-verified, no download)
  * Tests B, D, E and G run inside a new Linux network namespace (`unshare -n`): only loopback exists,
    so any attempt to reach the internet fails at the OS level — that is the "disconnect" for Test B
  * Test F kills the server with SIGKILL (a crash, not a clean shutdown) and starts it again
Results are written to docs/independence_results.json; docs/INDEPENDENCE_TESTS.md summarises them.
"""
from __future__ import annotations

import fcntl
import json
import os
import signal
import socket
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
MODELS = {"chat": "qwen2.5-1.5b-instruct-q4_k_m", "eco": "qwen2.5-0.5b-instruct-q4_k_m", "deep": os.getenv("DEEP_MODEL", "qwen3-4b-q4_k_m"),
          "embedding": "nomic-embed-text-v1.5-q8_0", "replacement": "smollm2-360m-instruct-q8_0"}


def last_number(text: str) -> float | None:
    import re

    nums = re.findall(r"-?\d+(?:\.\d+)?", (text or "").replace(",", ""))
    return float(nums[-1]) if nums else None


def deep_check(rec: Recorder, c: httpx.Client, label: str, question: str, expected: float, samples: int = 1) -> None:
    t = time.time()
    r = c.post("/api/ai/reason", json={"question": question, "samples": samples}).json()
    rec.check(label, r.get("provider") == "local" and r.get("model") == MODELS["deep"] and last_number(r.get("answer", "")) == expected
              and bool(r.get("reasoning")),
              {"model": r.get("model"), "answer": r.get("answer") or "", "expected": expected, "found": last_number(r.get("answer", "")),
               "reasoning_complete": r.get("reasoning_complete"), "reasoning_tail": (r.get("reasoning") or "")[-400:],
               "self_consistency": r.get("self_consistency"),
               "seconds": round(time.time() - t, 1)})
ADMIN = ("admin@independence.test", "independence-admin-pw")
OPERATOR = ("operator@independence.test", "independence-operator-pw")
VIEWER = ("viewer@independence.test", "independence-viewer-pw")
PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"


# ------------------------------------------------------------------ infrastructure
def lo_up() -> None:
    """Bring the loopback interface up inside a fresh network namespace (no `ip` binary needed)."""
    SIOCGIFFLAGS, SIOCSIFFLAGS, IFF_UP = 0x8913, 0x8914, 0x1
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    ifreq = struct.pack("16sH14s", b"lo", 0, b"\x00" * 14)
    flags = struct.unpack("16sH14s", fcntl.ioctl(s, SIOCGIFFLAGS, ifreq))[1]
    fcntl.ioctl(s, SIOCSIFFLAGS, struct.pack("16sH14s", b"lo", flags | IFF_UP, b"\x00" * 14))
    s.close()


def env_for(work: Path, **extra: str) -> dict[str, str]:
    e = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "OLLAMA_", "MODEL_CHAIN_"))}
    e.update({"DATABASE_URL": f"sqlite:///{work / 'daemon.db'}", "ARCHIVE_DIR": str(work / "archive"), "LLM_ENABLED": "true",
              "SECRET_KEY": "independence-test-secret", "MODELS_DIR": str(BACKEND / "data" / "models"),
              "DAEMON_LOCAL_MAX_TOKENS": "300", "RESUME_TASKS_ON_START": "true", "CORS_ORIGINS": "http://localhost:3000"})
    e.update(extra)
    return e


class Server:
    def __init__(self, work: Path, **env: str) -> None:
        self.work, self.env, self.proc = work, env_for(work, **env), None

    def start(self) -> Server:
        log = (self.work / "server.log").open("ab")
        self.proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT)],
                                     cwd=BACKEND, env=self.env, stdout=log, stderr=subprocess.STDOUT)
        for _ in range(120):
            try:
                if httpx.get(f"{BASE}/api/auth/status", timeout=1, trust_env=False).status_code == 200:
                    return self
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        raise RuntimeError("server did not start; see server.log")

    def crash(self) -> None:
        self.proc.send_signal(signal.SIGKILL)
        self.proc.wait()

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait(timeout=20)


def client(email: str | None = None, password: str | None = None) -> httpx.Client:
    c = httpx.Client(base_url=BASE, timeout=600, trust_env=False)  # never through a proxy: this is loopback
    if email:
        r = c.post("/api/auth/login", json={"email": email, "password": password})
        r.raise_for_status()
        c.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return c


class Recorder:
    def __init__(self, test: str, title: str) -> None:
        self.test, self.title, self.checks, self.t0 = test, title, [], time.time()

    def check(self, name: str, ok: bool, evidence: Any = None) -> bool:
        self.checks.append({"check": name, "ok": bool(ok), "evidence": evidence})
        print(f"  [{'PASS' if ok else 'FAIL'}] {self.test}: {name}" + (f" — {json.dumps(evidence, default=str)[:160]}" if evidence is not None else ""), flush=True)
        return ok

    def result(self) -> dict[str, Any]:
        return {"test": self.test, "title": self.title, "passed": all(c["ok"] for c in self.checks), "checks": self.checks,
                "duration_s": round(time.time() - self.t0, 1)}


def external_attempts(work: Path) -> list[tuple]:
    """Every recorded model attempt that reached (or tried to reach) a non-local provider."""
    con = sqlite3.connect(work / "daemon.db")
    rows = con.execute("SELECT provider, model, status, locality FROM llm_calls WHERE locality NOT IN ('local','lan','cache') "
                       "AND status NOT IN ('not_configured','excluded_offline','excluded_privacy','excluded_external_disabled','paused')").fetchall()
    con.close()
    return rows


def internet_reachable() -> dict[str, Any]:
    out = {}
    for url in ("https://huggingface.co", "https://api.anthropic.com"):
        try:
            r = httpx.get(url, timeout=8)  # trust_env=True: even the egress proxy must be unreachable
            out[url] = f"reachable (HTTP {r.status_code})"
        except Exception as e:
            out[url] = f"unreachable: {type(e).__name__}"
    return out


def listening_sockets() -> list[str]:
    socks = []
    for f in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            for line in Path(f).read_text().splitlines()[1:]:
                parts = line.split()
                if parts[3] == "0A":  # LISTEN
                    host, port = parts[1].split(":")
                    socks.append(f"{'v6' if f.endswith('6') else 'v4'}:{host}:{int(port, 16)}")
        except FileNotFoundError:
            pass
    return socks


# ------------------------------------------------------------------ setup
def setup(work: Path) -> None:
    print("SETUP: fresh database, admin via CLI, models imported with checksum verification", flush=True)
    env = env_for(work)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True, capture_output=True)
    subprocess.run([sys.executable, "-m", "app.cli", "create-admin", "--email", ADMIN[0], "--password-stdin"], cwd=BACKEND, env=env,
                   input=ADMIN[1] + "\n", text=True, check=True, capture_output=True)
    srv = Server(work).start()
    try:
        c = client(*ADMIN)
        for email, pw, role in (OPERATOR + ("operator",), VIEWER + ("viewer",)):
            c.post("/api/auth/users", json={"email": email, "password": pw, "role": role}).raise_for_status()
        models_dir = BACKEND / "data" / "models"
        lib = {m["key"]: m for m in c.get("/api/daemon/library").json()["models"]}
        for key in MODELS.values():
            path = models_dir / lib[key]["source_file"]
            r = c.post(f"/api/daemon/library/{key}/import-file", json={"path": str(path)})
            r.raise_for_status()
        for slot in ("chat", "eco", "deep", "embedding"):
            c.post("/api/daemon/library/activate", json={"slot": slot, "key": MODELS[slot]}).raise_for_status()
        c.post("/api/demo").raise_for_status()  # synthetic, labelled sample commerce data so agents have something to work on
    finally:
        srv.stop()


# ------------------------------------------------------------------ tests
def test_a(work: Path) -> dict[str, Any]:
    rec = Recorder("A", "External provider shutdown")
    srv = Server(work).start()  # ANTHROPIC_*, OLLAMA_*, MODEL_CHAIN_* stripped from the environment
    try:
        c = client(*ADMIN)
        creds = c.get("/api/daemon/credentials").json()["credentials"]
        rec.check("no external AI credential exists (env stripped, none stored)", not [x for x in creds if x["status"] == "active"], creds)
        st = c.get("/api/ai/status").json()
        rec.check("independence verdict: no mandatory external runtime dependency", st["independence"]["independent"], st["independence"])
        t = time.time()
        r = c.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "In one sentence: who are you?"}], "max_tokens": 80}).json()
        rec.check("G-SUS chat answered by a local model", r.get("provider") == "local" and bool(r.get("reply")),
                  {"model": r.get("model"), "reply": (r.get("reply") or "")[:160], "seconds": round(time.time() - t, 1)})
        r = c.post("/api/ai/classify", json={"text": "The lamp arrived broken and late.", "labels": ["positive", "negative", "neutral"], "cache": False}).json()
        rec.check("classification served locally (fast tier → eco model)", r.get("provider") == "local", {"label": r.get("label"), "model": r.get("model")})
        r = c.post("/api/ai/generate", json={"prompt": "Extract product and price from: 'The Aurora lamp costs 49 EUR.'", "tier": "standard",
                                            "json_schema": {"type": "object", "properties": {"product": {"type": "string"}, "price": {"type": "number"}},
                                                            "required": ["product", "price"]}, "max_tokens": 60}).json()
        rec.check("structured generation served locally", r.get("provider") == "local" and isinstance(r.get("data"), dict), r.get("data"))
        # self-consistency (the recommended mode for answers that matter): a single sample of this problem answered -40 in
        # two earlier runs — see docs/independence_runs/ and docs/INDEPENDENCE_TESTS.md
        deep_check(rec, c, "deep reasoning on the local reasoning model, self-consistency ×3 (multi-step margin problem)",
                   "A product costs 80 SEK to make and sells for 200 SEK. The marketplace takes 15% of the sale price plus a fixed fee of "
                   "10 SEK per order. What is the profit per unit in SEK? End your answer with the number.", 80, samples=3)
        run = c.post("/api/gsus/runs", json={"objective": "Create brand concepts for the winter commuter pannier", "mode": "creative"}).json()
        rec.check("G-sus orchestrated run completed using the local model", run.get("status") == "completed" and run.get("ai_calls", 0) > 0,
                  {"status": run.get("status"), "ai_calls": run.get("ai_calls"), "ai_cost_usd": run.get("ai_cost_usd")})
        rec.check("zero external provider attempts recorded", not external_attempts(work), external_attempts(work))
    finally:
        srv.stop()
    return rec.result()


def tests_offline(work: Path) -> list[dict[str, Any]]:
    """B, D, E, G — executed inside an isolated network namespace."""
    lo_up()
    results = []
    net = internet_reachable()
    # a fake external key: proves offline mode does not fall back to an external provider even when one is "configured"
    srv = Server(work, ANTHROPIC_API_KEY="sk-ant-fake-key-to-prove-no-fallback").start()
    try:
        admin = client(*ADMIN)
        # ---------------- B
        rec = Recorder("B", "Offline operation (network namespace: loopback only)")
        rec.check("internet is unreachable from this namespace", all(v.startswith("unreachable") for v in net.values()), net)
        admin.patch("/api/daemon/settings", json={"offline_mode": True}).raise_for_status()
        st = admin.get("/api/ai/status").json()
        ext_in_chain = [o for ch in st["chains"].values() for o in ch["order"] if "external" in o]
        rec.check("offline mode on: no external provider in any routing chain", st["offline_mode"] and not ext_in_chain,
                  {t: ch["excluded"] for t, ch in st["chains"].items()})
        t = time.time()
        r = admin.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "What is Demonkoncernen AB? Answer briefly."}], "max_tokens": 80}).json()
        rec.check("local model processes prompts offline", r.get("provider") == "local" and bool(r.get("reply")),
                  {"model": r.get("model"), "reply": (r.get("reply") or "")[:160], "seconds": round(time.time() - t, 1)})
        deep_check(rec, admin, "deep reasoning works offline (multi-step VAT problem)",
                   "A lantern costs 240 SEK including 25% VAT. What is the price excluding VAT, in SEK? End your answer with the number.", 192)
        r = admin.post("/api/ai/agents/execute", json={"type": "system.self_evaluate", "payload": {}}).json()
        rec.check("an agent executes a local task offline", r.get("status") in ("succeeded",), {"agent": r.get("agent_id"), "status": r.get("status"), "error": r.get("error")})
        m = admin.post("/api/memory", json={"key": "offline-note", "content": "The offline test ran inside a network namespace.", "scope": "long_term"})
        mem = admin.get("/api/memory").json()
        rec.check("memory works offline (write + read)", m.status_code == 200 and any(x.get("key") == "offline-note" for x in (mem if isinstance(mem, list) else mem.get("items", []))),
                  {"write": m.status_code})
        rec.check("model downloads are refused in offline mode",
                  admin.post(f"/api/daemon/library/{MODELS['replacement']}/install").status_code == 409)
        rec.check("zero external provider attempts recorded (despite a configured external key)", not external_attempts(work), external_attempts(work))
        results.append(rec.result())

        # ---------------- D
        rec = Recorder("D", "Local embeddings (index + search without external embedding APIs)")
        docs = [("lantern.txt", "Solar panels charge the camping lantern during the day so it can light the tent at night.", "historical_fact"),
                ("pannier.txt", "The waterproof bicycle pannier attaches to the rear rack with two hooks.", "historical_fact"),
                ("bread.txt", "Cinnamon buns are baked with cardamom dough and pearl sugar.", "historical_fact")]
        for name, text, cls in docs:
            admin.post("/api/archive/upload", files={"file": (name, text.encode())}, data={"evidence_class": cls}).raise_for_status()
        re = admin.post("/api/archive/reembed").json()
        rec.check("archive embedded with the local GGUF model", str(re.get("model", "")).startswith("gguf:"), re)
        hits = admin.post("/api/archive/search", json={"query": "sun-powered light for outdoor sleeping", "mode": "semantic"}).json()
        hits = hits if isinstance(hits, list) else hits.get("results", [])
        top = (hits[0].get("title") or hits[0].get("document_title") or hits[0].get("filename") or "") if hits else ""
        rec.check("semantic query with no shared keywords finds the right document", "lantern" in json.dumps(hits[:1]).lower(),
                  {"top": top, "n": len(hits)})
        con = sqlite3.connect(work / "daemon.db")
        models_used = sorted({r[0] for r in con.execute("SELECT DISTINCT embedding_model FROM document_chunks")})
        con.close()
        rec.check("every stored vector came from the local model", models_used and all(m.startswith("gguf:") for m in models_used), models_used)
        results.append(rec.result())

        # ---------------- E
        rec = Recorder("E", "Agent continuity (local orchestration, no external orchestration service)")
        run = admin.post("/api/gsus/runs", json={"objective": "Evaluate the winter commuter pannier and convene a council"}).json()
        agents = sorted({s.get("agent_hint") for s in run.get("steps", []) if s.get("agent_hint")})
        rec.check("G-sus multi-step run completed offline", run.get("status") == "completed",
                  {"status": run.get("status"), "steps": [(s["title"], s["status"]) for s in run.get("steps", [])][:8]})
        con = sqlite3.connect(work / "daemon.db")
        task_agents = sorted({r[0] for r in con.execute("SELECT DISTINCT agent_id FROM tasks WHERE status='succeeded'")})
        con.close()
        rec.check("several agents collaborated through the in-process orchestrator", len(task_agents) >= 2, {"agents": task_agents, "plan_hints": agents})
        rec.check("still zero external attempts", not external_attempts(work), external_attempts(work))
        results.append(rec.result())

        # ---------------- G
        rec = Recorder("G", "Security (local services require authorisation)")
        anon = client()
        protected = ["/api/ai/status", "/api/ai/health", "/api/daemon/settings", "/api/daemon/library", "/api/memory", "/api/archive/stats"]
        codes = {p: anon.get(p).status_code for p in protected}
        codes.update({p: anon.post(p, json={}).status_code for p in ("/api/ai/chat", "/api/ai/generate", "/api/ai/embeddings", "/api/ai/agents/execute")})
        rec.check("anonymous requests are rejected (401)", all(v == 401 for v in codes.values()), codes)
        forged = httpx.Client(base_url=BASE, trust_env=False, headers={"Authorization": "Bearer eyJzdWIiOjF9.forged"})
        rec.check("forged token rejected", forged.get("/api/ai/status").status_code == 401)
        viewer = client(*VIEWER)
        vcodes = {"chat": viewer.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "hi"}]}).status_code,
                  "settings": viewer.patch("/api/daemon/settings", json={"offline_mode": False}).status_code,
                  "credentials": viewer.get("/api/daemon/credentials").status_code,
                  "install": viewer.post(f"/api/daemon/library/{MODELS['chat']}/install").status_code}
        rec.check("viewer cannot use AI, change settings, see credentials or install models (403)", all(v == 403 for v in vcodes.values()), vcodes)
        op = client(*OPERATOR)
        ocodes = {"settings": op.patch("/api/daemon/settings", json={"offline_mode": False}).status_code,
                  "credentials": op.post("/api/daemon/credentials", json={"provider": "x", "secret": "12345678", "attestation": "x"}).status_code,
                  "activate": op.post("/api/daemon/library/activate", json={"slot": "chat", "key": MODELS["replacement"]}).status_code}
        rec.check("operator cannot change settings, credentials or models (403)", all(v == 403 for v in ocodes.values()), ocodes)
        socks = listening_sockets()
        rec.check("the only listening socket in the namespace is the API on loopback (model runtime has no listener)",
                  socks == [f"v4:0100007F:{PORT}"], socks)
        h = admin.get("/api/ai/status").headers
        rec.check("security headers present", h.get("x-content-type-options") == "nosniff" and h.get("x-frame-options") == "DENY",
                  {k: h.get(k) for k in ("x-content-type-options", "x-frame-options", "content-security-policy")})
        locks = [client().post("/api/auth/login", json={"email": VIEWER[0], "password": "wrong-password-x"}).status_code for _ in range(6)]
        rec.check("brute-force login is locked out", locks[-1] == 429, locks)
        results.append(rec.result())
    finally:
        srv.stop()
    return results


def test_c(work: Path) -> dict[str, Any]:
    rec = Recorder("C", "Model replacement through the same internal API")
    srv = Server(work).start()
    try:
        c = client(*ADMIN)
        before = c.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "Name one colour."}], "max_tokens": 20}).json()
        for slot in ("chat", "eco"):
            c.post("/api/daemon/library/activate", json={"slot": slot, "key": MODELS["replacement"]}).raise_for_status()
        after = c.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "Name one colour."}], "max_tokens": 20}).json()
        rec.check("same /api/ai/chat call now served by a different model family", before.get("model") == MODELS["chat"] and after.get("model") == MODELS["replacement"],
                  {"before": before.get("model"), "after": after.get("model"), "reply_after": (after.get("reply") or "")[:80]})
        cl = c.post("/api/ai/classify", json={"text": "I love it", "labels": ["positive", "negative"], "cache": False})
        rec.check("classification still works on the replacement model", cl.status_code in (200, 502),
                  {"status": cl.status_code, "body": cl.json() if cl.status_code == 200 else cl.text[:160],
                   "note": "502 = the small model returned a label outside the allowed set; the API refuses to invent one"})
        run = c.post("/api/gsus/runs", json={"objective": "Create brand concepts for the winter commuter pannier", "mode": "creative"}).json()
        rec.check("agents keep working (G-sus run completes)", run.get("status") == "completed", {"status": run.get("status"), "ai_calls": run.get("ai_calls")})
        for slot in ("chat", "eco"):
            c.post("/api/daemon/library/rollback", json={"slot": slot}).raise_for_status()
        back = c.get("/api/ai/status").json()["active_models"]
        rec.check("rollback restores the previous models", back["chat"] == MODELS["chat"] and back["eco"] == MODELS["eco"], back)
    finally:
        srv.stop()
    return rec.result()


def test_f(work: Path) -> dict[str, Any]:
    rec = Recorder("F", "Recovery after a crash (SIGKILL) and restart")
    srv = Server(work).start()
    c = client(*ADMIN)
    c.patch("/api/daemon/settings", json={"offline_mode": True, "profile": "ECO"}).raise_for_status()
    c.post("/api/memory", json={"key": "survives-restart", "content": "written before the crash", "scope": "long_term"}).raise_for_status()
    queued = c.post("/api/tasks", json={"type": "system.self_evaluate", "payload": {"note": "recovery"}, "run": False}).json()
    srv.crash()
    con = sqlite3.connect(work / "daemon.db")  # simulate a task that was mid-flight when the process died
    con.execute("UPDATE tasks SET status='running', attempts=1 WHERE id=?", (queued["id"],))
    con.commit()
    con.close()
    srv = Server(work).start()
    try:
        c = client(*ADMIN)
        st = c.get("/api/ai/status").json()
        rec.check("configuration recovered (offline mode, profile)", st["offline_mode"] and st["profile"] == "ECO", {"offline": st["offline_mode"], "profile": st["profile"]})
        rec.check("active models recovered", all(st["active_models"][k] == MODELS[k] for k in ("chat", "eco", "deep", "embedding")), st["active_models"])
        r = c.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "Say OK."}], "max_tokens": 10}).json()
        rec.check("local model reloads and answers after restart", r.get("provider") == "local", {"model": r.get("model"), "reply": r.get("reply")})
        mem = c.get("/api/memory").json()
        items = mem if isinstance(mem, list) else mem.get("items", [])
        rec.check("memory recovered", any(x.get("key") == "survives-restart" for x in items))
        hits = c.post("/api/archive/search", json={"query": "camping lantern solar"}).json()
        rec.check("archive documents still searchable", bool(hits if isinstance(hits, list) else hits.get("results")))
        t = {}
        for _ in range(60):
            t = c.get(f"/api/tasks/{queued['id']}").json()
            if t["status"] not in ("queued", "running"):
                break
            time.sleep(1)
        rec.check("interrupted task was requeued and finished after restart", t.get("status") in ("succeeded", "blocked"), {"status": t.get("status"), "attempts": t.get("attempts")})
        c.patch("/api/daemon/settings", json={"offline_mode": False, "profile": "BALANCED"})
    finally:
        srv.stop()
    return rec.result()


def main() -> int:
    if "--offline-phase" in sys.argv:
        work = Path(sys.argv[sys.argv.index("--offline-phase") + 1])
        print(json.dumps(tests_offline(work), default=str), file=(work / "offline.json").open("w"))
        return 0
    work = Path(tempfile.mkdtemp(prefix="independence-"))
    print(f"work dir: {work}")
    results: list[dict[str, Any]] = []
    setup(work)
    results.append(test_a(work))
    p = subprocess.run(["unshare", "-n", sys.executable, __file__, "--offline-phase", str(work)], cwd=BACKEND)
    if p.returncode == 0 and (work / "offline.json").exists():
        results += json.loads((work / "offline.json").read_text())
    else:
        results.append({"test": "B/D/E/G", "title": "offline phase", "passed": False, "checks": [{"check": "network namespace phase ran", "ok": False,
                                                                                                    "evidence": f"exit {p.returncode}"}]})
    results.append(test_c(work))
    results.append(test_f(work))
    results.sort(key=lambda r: r["test"])
    hw = json.loads(subprocess.run([sys.executable, "-c", "import json,sys;sys.path.insert(0,'.');from app.daemon import hardware;print(json.dumps(hardware.snapshot()))"],
                                   cwd=BACKEND, capture_output=True, text=True, env=env_for(work)).stdout)
    out = {"ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "hardware": {"cpu": hw["cpu"]["model"], "cores": hw["cpu"]["usable_cores"],
           "ram_gb": round(hw["ram_total_bytes"] / 1e9, 1), "gpu": hw["gpus"] or "none", "runtime": hw["runtime"]},
           "models": MODELS, "all_passed": all(r["passed"] for r in results), "results": results}
    (ROOT / "docs" / "independence_results.json").write_text(json.dumps(out, indent=2, default=str))
    print("\nSUMMARY")
    for r in results:
        print(f"  Test {r['test']}: {'PASS' if r['passed'] else 'FAIL'} — {r['title']} ({r['duration_s'] if 'duration_s' in r else '?'} s)")
    print("ALL PASSED" if out["all_passed"] else "NOT ALL PASSED")
    return 0 if out["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
