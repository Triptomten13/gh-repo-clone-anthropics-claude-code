"""DAEMON HYPERINTELLIGENCE: orchestrator, deterministic tools, caches, research (mocked network), monitors, residency,
telemetry, Control Center, retention. No real network or model files are used."""
import threading
import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.daemon import cache, deterministic, intel, residency, semantic_cache, state, telemetry


# ------------------------------------------------------------------ deterministic + routing
@pytest.mark.parametrize("q,answer", [("What is 17*23+4?", "395"), ("25% of 480", "120"), ("2^10", "1024"),
                                      ("A lantern costs 240 SEK including 25% VAT. Price excluding VAT?", "192"),
                                      ("100 SEK excluding 25% VAT", "125"), ("How many days between 2026-01-01 and 2026-03-01?", "59"),
                                      ("30 C to F", "86 f")])
def test_deterministic_solvers(q, answer):
    assert deterministic.solve(q)["answer"] == answer


def test_deterministic_solvers_do_not_guess():
    for q in ("What is the capital of France?", "Is 15% of revenue a lot?", "Write a poem about 3 cats", "__import__('os')"):
        assert deterministic.solve(q) is None


def test_routing_eval_suites_score_fully():
    from app.evals.runner import intel_routing_suite

    assert intel_routing_suite()["score"] == 1.0


def test_plan_respects_offline_and_missing_capabilities():
    c = intel.classify("What is the latest version of llama.cpp?")
    assert c.needs_current_info
    assert intel.plan(c, offline=True, has_local={"deep": True}).strategy == "archive"  # never pretends to search offline
    assert intel.plan(intel.classify("Describe this photo.png"), offline=False, has_local={}).strategy == "unavailable"
    p = intel.plan(intel.classify("A costs 80, sells for 200, fee 15% plus 10. Profit per unit?"), offline=False, has_local={"deep": False})
    assert p.strategy == "model_standard" and "no reasoning model" in p.reason


def test_ask_solves_arithmetic_without_any_model(client):
    r = client.post("/api/ai/ask", json={"question": "What is 17*23+4?"}).json()
    assert r["answer"] == "395" and r["model_calls"] == 0 and r["plan"]["strategy"] == "deterministic"
    assert client.post("/api/ai/ask", json={"question": "Transcribe interview.mp3"}).json()["status"] == "unavailable"
    plan = client.post("/api/ai/plan", json={"question": "Research the literature on LLM quantization"}).json()
    assert plan["plan"]["strategy"] == "research"


def test_ask_archive_answer_is_cached_and_reused(client):
    client.post("/api/archive/text", json={"title": "Exile", "text": "Jerusalem fell to Babylon in 587 BCE and many were deported.",
                                           "evidence_class": "historical_fact"})
    q = "What does our archive say about Jerusalem and Babylon?"
    first = client.post("/api/ai/ask", json={"question": q}).json()
    assert first["plan"]["strategy"] == "archive" and first["sources"] and not first.get("cached")
    second = client.post("/api/ai/ask", json={"question": q}).json()
    assert second["cached"] and second["cache_layer"] == "L2-exact" and second["model_calls"] == 0


def test_semantic_cache_guards():
    assert semantic_cache._numbers("VAT on 240 SEK") != semantic_cache._numbers("VAT on 250 SEK")
    assert bool(semantic_cache.NEG.search("which lanterns are not waterproof")) != bool(semantic_cache.NEG.search("which lanterns are waterproof"))


# ------------------------------------------------------------------ L1 cache + single flight
def test_ttl_cache_and_single_flight():
    c = cache.TTLCache("t", ttl_s=0.2, maxsize=2)
    calls = []
    assert c.get_or_set("a", lambda: calls.append(1) or 1) == 1 and c.get_or_set("a", lambda: calls.append(1) or 2) == 1 and len(calls) == 1
    time.sleep(0.25)
    assert c.get("a")[0] is False
    c.set("x", 1), c.set("y", 2), c.set("z", 3)
    assert c.evictions == 1 and c.stats()["size"] == 2
    sf, n, out = cache.SingleFlight(), [], []

    def slow():
        n.append(1)
        time.sleep(0.2)
        return 42

    ts = [threading.Thread(target=lambda: out.append(sf.do("k", slow))) for _ in range(5)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert out == [42] * 5 and len(n) == 1 and sf.suppressed == 4  # duplicate requests suppressed


# ------------------------------------------------------------------ research (mocked sources)
def _fake_sources(monkeypatch):
    from app.internet import sources as S

    def wiki(q, k=3):
        return [{"source": "wikipedia", "id": "w1", "url": "https://en.wikipedia.org/wiki/Llama.cpp", "title": "Llama.cpp",
                 "text": "llama.cpp is an open-source library for local inference of large language models. The llama.cpp library for local inference was first released in 2023.",
                 "published_at": "2026-10-01T00:00:00Z", "reliability": "tertiary", "license_note": "CC BY-SA"}]

    def gh(q, k=3):
        return [{"source": "github", "id": "g1", "url": "https://github.com/ggml-org/llama.cpp", "title": "ggml-org/llama.cpp",
                 "text": "llama.cpp local inference of large language models library, first released in 2022 according to this record.",
                 "published_at": "2026-11-01T00:00:00Z", "reliability": "primary", "license_note": "MIT"}]
    monkeypatch.setitem(S.REGISTRY, "wikipedia", wiki)
    monkeypatch.setitem(S.REGISTRY, "github", gh)
    monkeypatch.setitem(S.REGISTRY, "pypi", lambda *a, **k: [])
    monkeypatch.setitem(S.REGISTRY, "hn", lambda *a, **k: [])


def test_research_quick_extractive_cached_and_offline(client, fresh_db, monkeypatch):
    _fake_sources(monkeypatch)
    r = client.post("/api/research", json={"query": "What is llama.cpp?", "depth": "quick"}).json()
    assert r["status"] == "completed" and r["answer_kind"] == "extractive" and "[1]" in r["answer"] and r["sources"][0]["url"].startswith("https://")
    assert r["findings"][0]["kind"].startswith("extracted_fact")
    again = client.post("/api/research", json={"query": "What is llama.cpp?", "depth": "quick"}).json()
    assert again["cached"] and again["run_id"] == r["run_id"]
    client.patch("/api/daemon/settings", json={"offline_mode": True})
    off = client.post("/api/research", json={"query": "Something entirely new about llama.cpp releases", "depth": "quick"}).json()
    assert off["status"] == "offline" and off["answer"] is None


def test_research_standard_flags_contradictions_without_resolving_them(fresh_db, monkeypatch):
    from app.internet import research

    from app.internet import sources as S

    _fake_sources(monkeypatch)
    monkeypatch.setitem(S.REGISTRY, "hn", S.REGISTRY["wikipedia"])  # a library question selects github/pypi/hn — feed the second account via hn
    s = fresh_db.SessionLocal()
    r = research.run(s, "llama.cpp open-source library local inference large language models released", depth="standard")
    assert {x["source"] for x in r["sources"]} == {"wikipedia", "github"}
    assert r["contradictions"] and "different numbers" in r["contradictions"][0]["why"]  # 2023 vs 2022 is reported, not decided
    s.close()


def test_http_respects_offline_and_long_retry_after(fresh_db, monkeypatch):
    from app.internet import http

    calls = []

    def handler(req):
        calls.append(req.url.host)
        return httpx.Response(429, headers={"retry-after": "120"})

    monkeypatch.setattr(http, "_client", httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(http, "_paused_until", {})
    r = http.request("GET", "https://api.example.org/x")
    assert r.status_code == 429 and len(calls) == 1
    with pytest.raises(http.FetchError, match="retry after"):
        http.request("GET", "https://api.example.org/y")  # paused: nothing is sent before the server allows it
    assert len(calls) == 1
    s = fresh_db.SessionLocal()
    state.update(s, offline_mode=True)
    s.commit()
    s.close()
    with pytest.raises(http.OfflineError):
        http.request("GET", "https://other.example.org/")


# ------------------------------------------------------------------ monitors
def test_monitor_reports_only_new_items(client, fresh_db, monkeypatch):
    from app.internet import sources as S

    batches = [[{"id": "a", "title": "A", "url": "u1", "source": "hn"}], [{"id": "a", "title": "A", "url": "u1", "source": "hn"},
               {"id": "b", "title": "B", "url": "u2", "source": "hn"}], [{"id": "b", "title": "B", "url": "u2", "source": "hn"}]]
    monkeypatch.setitem(S.REGISTRY, "hn", lambda q, k=10: batches.pop(0))
    m = client.post("/api/monitors", json={"name": "test monitor", "purpose": "test", "query": "llama", "sources": ["hn"], "every_minutes": 60}).json()
    first = client.post(f"/api/monitors/{m['id']}/run").json()
    second = client.post(f"/api/monitors/{m['id']}/run").json()
    third = client.post(f"/api/monitors/{m['id']}/run").json()
    assert (first["new"], second["new"], third["new"]) == (1, 1, 0)
    events = client.get("/api/monitors/events").json()
    assert len(events) == 1 and events[0]["items"][0]["title"] == "B"  # baseline run and quiet run produce no alerts


# ------------------------------------------------------------------ residency + telemetry
class FakeProvider:
    def __init__(self, resident, freed_per_unload=0):
        self.res = dict(resident)  # key → last_used
        self.unloaded = []
        self.avail, self.freed = 0, freed_per_unload

    def resident(self):
        return list(self.res)

    def lru_idle(self):
        return min(self.res, key=self.res.get) if self.res else None

    def unload(self, k, reason=""):
        self.res.pop(k, None)
        self.unloaded.append(k)
        self.avail += self.freed  # unloading really frees memory
        return True


def test_residency_evicts_lru_only_when_needed(fresh_db, monkeypatch):
    p = FakeProvider({"old|gen": 1, "new|gen": 2})
    monkeypatch.setattr(residency, "available_bytes", lambda: int(8e9))
    residency.make_room(p, int(1e9))
    assert p.unloaded == []  # enough RAM: nothing is evicted (no fixed model count in BALANCED)
    p = FakeProvider({"old|gen": 1, "new|gen": 2}, freed_per_unload=int(1e9))
    p.avail = int(2.0e9)
    monkeypatch.setattr(residency, "available_bytes", lambda: p.avail)
    residency.make_room(p, int(1e9))  # needs 1 GB + 1.5 GB reserve: evicting the least-recently-used model is enough
    assert p.unloaded == ["old|gen"]
    p2 = FakeProvider({})
    monkeypatch.setattr(residency, "available_bytes", lambda: int(0.5e9))
    with pytest.raises(MemoryError):
        residency.make_room(p2, int(1e9))


def test_memory_pressure_switches_mode_with_hysteresis(fresh_db):
    residency._auto_mode = None
    total = int(16e9)
    residency.on_sample({"ram_total_bytes": total, "ram_available_bytes": int(total * 0.08)})
    assert residency.effective_mode() == "LOW_MEMORY"
    residency.on_sample({"ram_total_bytes": total, "ram_available_bytes": int(total * 0.15)})
    assert residency.effective_mode() == "LOW_MEMORY"  # not flapping: needs >20 % to clear
    residency.on_sample({"ram_total_bytes": total, "ram_available_bytes": int(total * 0.03)})
    assert residency.effective_mode() == "EMERGENCY"
    residency.on_sample({"ram_total_bytes": total, "ram_available_bytes": int(total * 0.5)})
    assert residency.effective_mode() == residency.configured_mode()
    assert any(e["kind"] == "resource_mode" for e in telemetry.events())


def test_telemetry_records_routes_with_sql_counts(client):
    telemetry.reset()
    client.get("/api/agents")
    row = next(r for r in telemetry.routes() if r["route"] == "GET /api/agents")
    assert row["count"] == 1 and 1 <= row["sql_per_request"] <= 5  # was 124 statements before the grouped query
    s = telemetry.sample()
    assert s["ram_total_bytes"] and "cpu_pct" in s and "process" in s


def test_control_overview_reports_real_or_null(client):
    o = client.get("/api/control/overview").json()
    assert {"intelligence", "hardware", "network", "economics", "efficiency"} <= set(o)
    assert o["hardware"]["ram_total_bytes"] and o["hardware"]["vram"] is None  # no GPU here: null, not invented
    agents = client.get("/api/agents").json()
    assert all("policy" in a for a in agents if a["task_types"]) and agents[0]["policy"]["context_budget_tokens"] > 0


def test_retention_removes_only_expired(client, fresh_db):
    from app.models import ResponseCache, WebResource

    s = fresh_db.SessionLocal()
    now = datetime.now(UTC)
    s.add_all([ResponseCache(key="old", expires_at=now - timedelta(days=1)), ResponseCache(key="fresh", expires_at=now + timedelta(days=1)),
               WebResource(url="https://a.example/1", host="a.example", source="web", expires_at=now - timedelta(days=3)),
               WebResource(url="https://a.example/2", host="a.example", source="web", expires_at=now - timedelta(days=3), promoted_document_id=1)])
    s.commit()
    s.close()
    out = client.post("/api/control/retention").json()
    assert out["deleted"]["response_cache"] == 1 and out["deleted"]["web_resources"] == 1  # promoted sources are kept


# ------------------------------------------------------------------ context, perf agent, delegation report
def test_long_chat_history_is_summarised_not_resent(client):
    from app.ai import llm
    from app.ai.llm import LLMResult

    seen = []

    class Stub:
        name = "stub"

        def complete(self, *, system, prompt, tier="standard", schema=None, max_tokens=1000):
            seen.append((tier, len(prompt)))
            return LLMResult("summary: they discussed lanterns and prices", None, "m", 10, 5, 0.0, "local", 1, [])

    llm.set_provider(Stub())
    history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"Turn {i}: " + "details about lantern pricing and shipping " * 30}
               for i in range(14)]
    r = client.post("/api/ai/chat", json={"messages": [*history, {"role": "user", "content": "So what did we decide?"}]}).json()
    ctx = r["context"]
    assert ctx["summarized"] and ctx["sent_tokens_est"] < ctx["history_tokens_est"] / 2
    assert seen[0][0] == "fast"  # the summary is made by the small model
    short = client.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "hi"}]}).json()
    assert short["context"]["summarized"] is False


def test_perf_agent_files_measured_proposals(client):
    from app.daemon import telemetry

    telemetry.reset()
    for _ in range(25):
        telemetry.record_request("GET /api/slow-thing", 900.0, 200, 40, 100)
    r = client.post("/api/ai/agents/execute", json={"type": "perf.analyze", "payload": {}}).json()
    assert r["status"] == "succeeded"
    props = client.get("/api/daemon/proposals").json()
    kinds = {p["kind"] for p in props}
    assert {"perf_slow_route", "perf_n_plus_one"} <= kinds
    slow = next(p for p in props if p["kind"] == "perf_slow_route")
    assert slow["evidence"]["p95_ms"] == 900.0 and "perf_bench" in slow["detail"] and slow["status"] == "proposed"


def test_agent_efficiency_report(client):
    client.post("/api/ai/agents/execute", json={"type": "system.self_evaluate", "payload": {}})
    rep = client.get("/api/agents/efficiency").json()
    row = next(a for a in rep["agents"] if a["agent"] == "self_improvement")
    assert row["tasks"] >= 1 and row["success_rate"] == 1.0 and "delegation" in row


def test_large_document_is_searchable_at_once_and_upgraded_in_background(client, fresh_db, monkeypatch):
    from sqlalchemy import select

    from app.knowledge import process
    from app.models import DocumentChunk

    monkeypatch.setattr(process, "LARGE_DOC_CHUNKS", 3)
    monkeypatch.setattr(process, "embedder", lambda: ("gguf:fake", lambda texts, kind="document": [[1.0, 0.0] for _ in texts]))
    text = " ".join(f"Section {i}: pallets of lanterns inspected at the Gothenburg warehouse." for i in range(400))
    t0 = time.time()
    doc = client.post("/api/archive/text", json={"title": "big", "text": text, "evidence_class": "unclassified"}).json()
    assert doc["status"] == "ready" and time.time() - t0 < 10
    hits = client.post("/api/archive/search", json={"query": "Gothenburg warehouse", "mode": "keyword", "k": 1}).json()["results"]
    assert hits  # keyword search works immediately
    for _ in range(50):
        s = fresh_db.SessionLocal()
        models = set(s.scalars(select(DocumentChunk.embedding_model).where(DocumentChunk.document_id == doc["id"])).all())
        s.close()
        if models == {"gguf:fake"}:
            break
        time.sleep(0.1)
    assert models == {"gguf:fake"}  # semantic vectors arrived in the background


# ------------------------------------------------------------------ security regressions (audit 2026-11-05)
@pytest.mark.parametrize("url,why", [("http://127.0.0.1:8000/api/auth/users", "non-public"), ("http://169.254.169.254/latest/meta-data/", "non-public"),
                                     ("http://[::1]/", "non-public"), ("http://10.0.0.5/feed.xml", "non-public"),
                                     ("http://localhost:5432/", "local host"), ("http://db.internal/", "local host"),
                                     ("file:///etc/passwd", "scheme"), ("gopher://example.org/", "scheme"),
                                     ("https://evil.example/", "non-public")])
def test_research_http_refuses_internal_targets(url, why, monkeypatch):
    from app.internet import http

    cache.invalidate("ssrf-guard")
    # evil.example resolves to a private address (DNS pointing inwards) — the guard checks what the name RESOLVES to
    monkeypatch.setattr(http, "_resolve", lambda host, port: [(2, 1, 6, "", ("192.168.1.10", 0))])
    with pytest.raises(http.FetchError, match=why):
        http.guard_url(url)


def test_research_http_guard_checks_every_redirect_hop(monkeypatch):
    from app.internet import http

    cache.invalidate("ssrf-guard")
    monkeypatch.setattr(http, "_resolve", lambda host, port: [(2, 1, 6, "", ("93.184.215.14", 0))])  # a public address
    sent = []

    def handler(req):
        sent.append(str(req.url))
        if req.url.host == "feeds.example.org":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/iam"})
        return httpx.Response(200, text="SECRET")

    c = http._make_client(httpx.MockTransport(handler))
    assert c.get("https://ok.example.org/").status_code == 200  # public targets still work
    with pytest.raises(http.FetchError, match="non-public"):
        c.get("https://feeds.example.org/rss.xml")
    assert not any("169.254" in u for u in sent)  # the metadata endpoint was never contacted


def test_connector_links_are_http_only():
    from app.internet import sources as S

    items = S.sanitize([{"url": "javascript:alert(document.cookie)"}, {"url": "data:text/html,<script>x</script>"}, {"url": " https://arxiv.org/abs/1 "},
                        {"url": "https://x.org/\"onmouseover=1"}, {"url": None}])
    assert [i["url"] for i in items] == ["", "", "https://arxiv.org/abs/1", "", ""]


def test_monitor_patch_is_validated_and_audited(client):
    m = client.post("/api/monitors", json={"name": "bounded monitor", "purpose": "test", "query": "llama", "sources": ["hn", "hn"]}).json()
    assert m["sources"] == ["hn"]  # duplicates cannot multiply a monitor's requests
    for bad in ({"max_requests": 10_000}, {"every_minutes": 0}, {"enabled": "maybe"}, {"purpose": "x" * 600}):
        assert client.patch(f"/api/monitors/{m['id']}", json=bad).status_code == 422, bad
    ok = client.patch(f"/api/monitors/{m['id']}", json={"enabled": False, "max_requests": 2})
    assert ok.status_code == 200 and ok.json()["enabled"] is False and ok.json()["max_requests"] == 2
    assert client.post("/api/monitors", json={"name": "too many", "purpose": "test", "query": "q", "sources": ["hn"] * 11}).status_code == 422
    log = client.get("/api/audit").json()
    rows = log if isinstance(log, list) else log.get("entries", log.get("items", []))
    assert any(r.get("action") == "monitor.update" for r in rows)


def test_deleting_a_document_purges_cached_answers_quoting_it(client):
    d = client.post("/api/archive/text", json={"title": "Private note", "text": "The vault code for the Uppsala office is kept by Ingrid Berg.",
                                               "evidence_class": "primary_source"}).json()
    q = "What does our archive say about the Uppsala office vault?"
    first = client.post("/api/ai/ask", json={"question": q}).json()
    assert first["sources"] and not first.get("cached")
    assert client.post("/api/ai/ask", json={"question": q}).json().get("cached")
    assert client.delete(f"/api/archive/documents/{d['id']}?confirm=true").status_code == 200
    after = client.post("/api/ai/ask", json={"question": q}).json()
    assert not after.get("cached") and "Ingrid" not in str(after.get("answer"))  # the deleted text does not live on in the cache


def test_no_pickle_backed_disk_cache_is_used():
    """Accepted risk PYSEC-2026-2447 (diskcache ≤5.6.3 unpickles its cache directory; no fix released): it is only safe
    while nothing in the app opens a diskcache (llama-cpp-python's LlamaDiskCache). Revisit the audit if this fails."""
    from pathlib import Path

    app = Path(__file__).resolve().parents[1] / "app"
    hits = [str(p) for p in app.rglob("*.py") if any(s in p.read_text(encoding="utf-8") for s in ("LlamaDiskCache", "import diskcache"))]
    assert hits == []


# ------------------------------------------------------------------ Archive index (measured: docs/perf/archive-*.json)
TEXTS = ["Jerusalem fell to Babylon in 587 BCE and many were deported to Babylon.", "The temple was rebuilt after the exile under Persian rule.",
         "Lantern pallets were inspected at the Gothenburg warehouse in March.", "Babylon's hanging gardens are attested only in later Greek sources.",
         "The covenant texts were copied by scribes during the exile in Babylon.", "Warehouse inventory: 400 lanterns, 12 pallets, 3 inspections."]


def _seed_archive(client):
    ids = []
    for i, t in enumerate(TEXTS * 3):
        ids.append(client.post("/api/archive/text", json={"title": f"doc {i}", "text": t, "tags": ["even"] if i % 2 == 0 else [],
                                                          "evidence_class": "historical_fact" if i % 3 else "primary_source"}).json()["id"])
    return ids


def test_index_ranks_exactly_like_the_scan(client, fresh_db):
    from app.knowledge import search

    _seed_archive(client)
    db = fresh_db.SessionLocal()
    cases = [("Babylon exile", "hybrid", None), ("warehouse lanterns", "keyword", None), ("temple rebuilt Persian", "semantic", None),
             ("Babylon", "hybrid", {"evidence_class": "primary_source"}), ("exile", "hybrid", {"tag": "even"}), ("nothing-matches-this", "hybrid", None)]
    for q, mode, f in cases:
        indexed = search.search(db, q, k=10, mode=mode, filters=f)
        scan = search._search_scan(db, q, k=10, mode=mode, filters=f)
        assert [(h["chunk_id"], h["score"]) for h in indexed] == [(h["chunk_id"], h["score"]) for h in scan], (q, mode, f)
    db.close()


def test_index_never_serves_deleted_or_stale_chunks(client, fresh_db):
    from app.knowledge import index, search
    from app.models import DocumentChunk

    ids = _seed_archive(client)
    q = {"query": "Gothenburg warehouse", "mode": "keyword", "k": 50}
    before = client.post("/api/archive/search", json=q).json()["results"]
    victim = before[0]["document_id"]
    builds = index.stats["builds"]
    assert client.delete(f"/api/archive/documents/{victim}?confirm=true").status_code == 200
    after = client.post("/api/archive/search", json=q).json()["results"]
    assert victim not in {h["document_id"] for h in after} and len(after) == len(before) - 1
    assert index.stats["builds"] == builds  # the delete was applied incrementally, not by a full rebuild
    # a write from ANOTHER session (another process would look the same: it only sees the database) is picked up
    other = fresh_db.SessionLocal()
    c = other.query(DocumentChunk).filter(DocumentChunk.document_id == ids[1]).first()
    c.text = "Zanzibar spice ledger, rewritten in another session."
    other.commit()
    other.close()
    db = fresh_db.SessionLocal()
    assert [h["document_id"] for h in search.search(db, "zanzibar ledger", mode="keyword")] == [ids[1]]
    db.close()


def test_index_picks_up_background_semantic_upgrade(client, fresh_db, monkeypatch):
    from app.knowledge import process, search

    monkeypatch.setattr(process, "LARGE_DOC_CHUNKS", 3)
    vec = {"doc": [1.0, 0.0], "query": [1.0, 0.0]}
    fake = ("gguf:fake", lambda texts, kind="document": [vec["doc"] for _ in texts])
    monkeypatch.setattr(process, "embedder", lambda: fake)
    monkeypatch.setattr(search, "embedder", lambda: fake)
    text = " ".join(f"Section {i}: lantern audit notes from the northern depot." for i in range(300))
    did = client.post("/api/archive/text", json={"title": "big", "text": text, "evidence_class": "unclassified"}).json()["id"]
    db = fresh_db.SessionLocal()
    for _ in range(100):  # semantic hits appear once the background upgrade has committed — no restart, no manual refresh
        db.rollback()
        hits = search.search(db, "anything", k=3, mode="semantic")
        if hits and all(h["document_id"] == did for h in hits):
            break
        time.sleep(0.1)
    db.close()
    assert hits and hits[0]["document_id"] == did


def test_index_is_safe_under_concurrent_search_and_writes(client, fresh_db):
    """Updates are copy-on-write: searches running while documents change never see a half-updated index."""
    from app.knowledge import search
    from app.models import Document, DocumentChunk

    _seed_archive(client)
    errors: list[str] = []
    stop = threading.Event()

    def reader():
        db = fresh_db.SessionLocal()
        try:
            while not stop.is_set():
                db.rollback()
                search.search(db, "Babylon warehouse exile", k=5)
        except Exception as e:  # noqa: BLE001 - any failure is the finding
            errors.append(repr(e))
        finally:
            db.close()

    readers = [threading.Thread(target=reader) for _ in range(3)]
    for t in readers:
        t.start()
    db = fresh_db.SessionLocal()
    for i in range(25):
        d = Document(uid=f"cc-{i}", title=f"concurrent {i}", doc_type="txt", content_hash=f"cc{i}", status="ready")
        db.add(d)
        db.flush()
        db.add(DocumentChunk(document_id=d.id, ordinal=0, text=f"Babylon warehouse ledger {i}", embedding=[], embedding_model=""))
        db.commit()
    db.close()
    stop.set()
    for t in readers:
        t.join()
    assert errors == []
    s = fresh_db.SessionLocal()
    assert len(search.search(s, "ledger", k=50, mode="keyword")) == 25
    s.close()
