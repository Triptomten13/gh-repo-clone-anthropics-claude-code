# DAEMON HYPERINTELLIGENCE — maximum useful intelligence per unit of resources

Principle: think before using a model, search before guessing when current facts matter, reuse verified knowledge,
and never claim an optimisation without a measurement. Every number on this page was measured on the development host
(4 vCPU x86-64, 16.9 GB RAM, no GPU) with the scripts named next to it.

## 1. Audit — the system as it was (Phase 1)

**Map.** Next.js command center (28 routes; each page view triggered 3 status calls) → FastAPI (≈200 endpoints) →
SQLAlchemy on SQLite/PostgreSQL → in-process orchestrator (single worker, 61 agents) → AI router (local llama.cpp,
Ollama, workers, Anthropic) → Archive (BM25 + local embeddings, all chunks scanned per query) → no internet research
subsystem (only commerce connectors and the model downloader) → scheduler loop (optional) → telemetry: none beyond
`llm_calls` → caches: response cache only → storage: SQLite file, Archive directory, model directory.

**Baseline** (`scripts/perf_bench.py --label baseline`, copy of the dev DB + 20,000 synthetic `llm_calls` rows in the
copy only; `docs/perf/baseline.json`). Prioritised findings:

| # | Finding | Measured | Priority |
|---|---|---|---|
| 1 | Cost dashboard loaded every row of the window into Python | 563 ms p50 at 20k rows | high |
| 2 | `/api/agents` ran 2 COUNT queries per agent (N+1) | 124 SQL statements, 33 ms | high |
| 3 | Every page view re-fetched three status endpoints; `/api/ai/status` re-probed hardware and model slots | 28 SQL, 24 ms per page view | medium |
| 4 | Local models: fixed "max 2 loaded", no idle unload; disk reads cold at **14 MB/s** (cached 6.5 GB/s) | 5 reloads in a 7-call chat/deep/eco sequence; first deep call 221 s (cold read of 2.5 GB) | high |
| 5 | Optimiser loaded all rows of 14 days | 172 ms | medium |
| 6 | No request, network or resource telemetry; nothing to base optimisation on | — | high |
| 7 | No internet research: current questions could only be guessed by a small model | — | high |
| 8 | Archive search scans and tokenises every chunk per query (BM25 without an index) | 4 ms with today's small Archive; grows linearly | watch |
| 9 | `REDIS_URL` setting exists but nothing uses Redis | dead configuration | low |
| 10 | WebSocket reconnect retries every 3 s forever when the API is down | minor polling | low |

## 2. What was built, phase by phase

| Phase | Built | Acceptance criterion | Result |
|---|---|---|---|
| 1 Audit | map, `scripts/perf_bench.py`, baseline | baseline recorded, repeatable | ✅ `docs/perf/baseline.json` |
| 2 Telemetry | `daemon/telemetry.py`: system sampler (CPU, RAM, page cache, swap, disk + I/O, network, temperature, GPU via nvidia-smi, process RSS/CPU), per-route latency + SQL count (middleware), per-host HTTP metrics, event log — all bounded | real values or null, never invented | ✅ tested; temperature and VRAM report null here (not exposed / no GPU) |
| 3 Orchestration | `daemon/intel.py` classifier (14 categories, time-sensitivity, complexity) + planner + `POST /api/ai/ask`, `/api/ai/plan`; `daemon/deterministic.py` | cheapest reliable strategy chosen; no model for deterministic work | ✅ routing eval 30/30 (after 2 general fixes from 28/30), held-out 12/12 first run |
| 4 Model optimisation | `daemon/residency.py`: memory-aware residency (no fixed count), LRU idle eviction, idle unload, LOW_MEMORY/EMERGENCY auto-entered under pressure with hysteresis, PERFORMANCE mode, prewarm (load small models, page-cache the deep one) | fewer reloads, never unloads a busy model | ✅ reloads 5 → 3, repeat deep call 10.5 s → 1.2 s |
| 5 Context | per-agent context budgets (measured, surfaced, never silently truncated), chat history budget with small-model summarisation, existing context assembly | long chats do not resend everything | ✅ 14-turn chat sends < ½ of the history tokens |
| 6 Caching | L1 TTL/LRU caches with stats + single-flight duplicate suppression; L2 exact + L3 semantic answer cache (scoped, category-checked, numbers/negation guards, verified-only, capped); response cache; L4 research cache with freshness classes; L5 model residency | caches bounded, expiring, scoped | ✅ |
| 7 Internet intelligence | `internet/`: one instrumented client (pooling, per-host rates, backoff, Retry-After pause, ETag/Last-Modified, robots.txt, size caps, offline stop); 10 official-API sources + keyed web search; QUICK/STANDARD/DEEP research; contradiction flags; missing-evidence; citations; knowledge kinds separated; monitors with change detection | grounded, cited, no repeated searches | ✅ live: Wikipedia, arXiv, Crossref, GitHub, HN, PyPI, OSV, NVD, Hugging Face, RSS |
| 8 Agent scheduling | per-agent model tier, context budget, tools, timeout and success criterion exposed; delegation cost/benefit report; single-worker orchestrator kept (no new concurrency without measured need) | delegation measurable | ✅ `/api/agents/efficiency` |
| 9 Storage & DB | SQL aggregation for costs/optimiser, grouped agent counts, retention rules (hourly), migration 0005 | measured speed-ups; nothing grows unbounded | ✅ see §3 |
| 10 Self-optimisation | Performance Engineering Agent (`perf.analyze`, daily) files proposals with the triggering measurement and a verification step; approval required; never applied automatically | measurable proposals only | ✅ tested |
| 11 Control Center | `/control`: intelligence, hardware, network, economics, efficiency, routes, events, Ask DAEMON; `/research`: research + monitors | real measurements only | ✅ |
| 12 Verification | `scripts/system_benchmark.py` (13 scenarios), unit/API tests, perf comparisons, Independence Tests | see §5 | see §5 |

## 3. Measured before / after (same harness, same data)

`scripts/perf_bench.py --label after-p9-sql-l1 --compare baseline`:

| Endpoint | Before | After |
|---|---|---|
| `GET /api/ai/status` (every page view) | 14.3 ms · 20 SQL | **2.5 ms · 1.2 SQL** |
| `GET /api/agents` | 32.9 ms · 124 SQL | **8.6 ms · 3 SQL** |
| `GET /api/daemon/costs` (20k rows) | 563 ms | **186 ms** |
| `POST /api/daemon/proposals/generate` | 172 ms | **54 ms** |
| `GET /api/ai/health` | 6.5 ms · 6 SQL | 4.1 ms · 1.1 SQL |
| Shell page view (3 calls) | 24 ms · 28 SQL | **10.6 ms · 7.2 SQL** |
| Process RSS after the run | 170 MB | 129 MB |

`--models` (real models, same 7-call chat/deep/eco sequence): reloads **5 → 3**; repeat deep call 10.5 s → 1.2 s; repeat
eco 1.3 s → 0.4 s; resident RSS 6.2 → 8.0 GB (three models kept while RAM allows — the intended trade-off, bounded by
the reserve and the LOW_MEMORY mode). The total sequence time (248 s → 44 s) is **not** claimed as an improvement: most
of the baseline was a cold disk read that depends on the OS page cache, not on this change.

## 4. How a request is solved now

```
question ─► classify (rules, no model) ─► plan: deterministic │ cache │ Archive │ research(depth) │ fast │ standard │ deep │ G-sus │ unavailable
                                              │ answer + execution trace (strategy, why, rejected options, cost, cache layer, sources)
```

* Deterministic: arithmetic, percentages, VAT add/remove, date differences, unit conversion, current date — no model.
* Facts: Archive first (grounded, cited); QUICK external lookup only if the Archive has nothing; offline ⇒ Archive only,
  and the answer says so.
* Current information (latest/price/release/CVE/news …): research, never model memory.
* Routine NLP (classify, transform, summarise): small local model. Programming/creative: standard model.
  Multi-step reasoning/planning: local reasoning model (optional self-consistency). Several agents: G-sus.
* Vision/speech: reported as unavailable — no local model for them is installed; they are not imitated.

## 5. System benchmark (Phase 12)

`python scripts/system_benchmark.py` — live server, real local models, fresh database. Full run 2026-11-05 20:16 UTC
(`docs/benchmarks/system-2026-11-05T201659Z.json`); scenario 7 re-run after the lock fix (see below).

| # | Scenario | Quality | Latency | Server RSS peak · CPU-s | Network · tokens · $ |
|---|---|---|---|---|---|
| 1 | Deterministic tasks (6) | 6/6 correct, **0 model calls** | p50 5 ms | 109 MB · 0.3 | 0 · 0 · 0 |
| 2 | Simple tasks, small local model (3 classifications) | 3/3 | 0.86 s | 823 MB · 10.3 | 0 · 284 · 0 |
| 3 | Complex reasoning, Qwen3 4B (2 problems) | 2/2 | 42.5 s and 91.1 s | 6.4 GB · 482 | 0 · 1,367 · 0 |
| 4 | Internet research | QUICK completed (via fallback), STANDARD completed (7 sources, generated conclusion), repeat served from research cache | 0.7 s · 32 s · **6 ms** | — | ext. requests only on cache miss · 0 $ |
| 5 | Multi-agent workflow (G-sus, council) | completed, 3 steps | 21 s | 8.4 GB · 81 | 0 · 627 · 0 |
| 6 | Semantic retrieval (no shared keywords) | top-1 3/3 | 41 ms | — | 0 |
| 7 | Large document (1.6 MB, 2,250 chunks) ingest + search | completed | ingest **6.5 s** (was > 600 s and locked the database) · search see below | 8.7 GB · 80 | 0 |
| 8 | High concurrency (50 mixed requests, 16 parallel) | 0 errors | p50 109 ms · p95 150 ms | — · 1.1 | 0 |
| 9 | Low-memory operation (LOW_MEMORY) | 2/2 answered; **1 model resident** afterwards | 70 s total | — · 226 | 0 · 577 · 0 |
| 10 | Offline operation | deterministic answer kept; "latest version" question routed to the Archive (not guessed); research reports `offline` | 37 s | 775 MB · 120 | 0 |
| 11 | Provider failure (invalid external key, DEEP profile) | served by `local` after `anthropic:unavailable` | 8.2 s | 2.2 GB · 18 | 0 · 286 · 0 |
| 12 | Network failure (dead proxy) | research `insufficient_evidence` with the connection errors listed; local answering unaffected | 30 s (bounded retries) | — | 0 |
| 13 | Recovery after SIGKILL | ready again in **1.6 s**; the first answer (249 ms) came from the persisted response cache — the same question had been asked before the crash | — | 110 MB | 0 |

Findings from the benchmark, fixed and re-measured:

* **Large-document ingest blocked the database.** The 1.6 MB ingest embedded 2,250 chunks inside the write transaction
  (local embeddings measure ~4 chunks/s on this CPU), timed out after 600 s and made every other write fail with
  "database is locked". Fixes: chunk/embed before writing; documents over 200 chunks are indexed lexically at once and
  upgraded to semantic vectors in the background (commits every 64 chunks); SQLite WAL + 30 s busy timeout. Result: 6.5 s.
  A batched-embedding idea was **measured and rejected** (1.9 vs 4.0 chunks/s sequential).
* **Search during a background upgrade took 22.5 s** — measured without the upgrade: 0.30 s keyword, 0.18 s semantic,
  0.42 s hybrid over 2,253 chunks; the difference was the query waiting on the embedding model's lock held for 64-chunk
  batches. Fix: lock per text. Re-measured: see the scenario 7 re-run below.
* **QUICK research returned nothing when Wikipedia rate-limited this host** → one bounded fallback source.
* **Benchmark harness**: a server whose worker was busy did not stop within 20 s and was left running (it contaminated
  one micro-benchmark); the harness now escalates to SIGKILL. The percentile helper mis-reported p95 for two samples; fixed.

**Scenario 7 re-run after the per-text lock** (`docs/benchmarks/system-2026-11-05T201808Z.json`): ingest 6.4 s, search
during the background semantic upgrade **433 ms** (was 22,544 ms), server RSS peak 289 MB.

## 6. Internet use — rules that are enforced in code

* Official APIs first; general web search only through a keyed API (Brave Search adapter, off until an owner-authorised
  key is stored — **not exercised live**). Search-engine result pages are not scraped.
* robots.txt is checked for page fetches; API endpoints are used within their documented rate limits (per-host token
  rates in `internet/http.py`); 429/503 with a long Retry-After pauses that host instead of retrying.
* The User-Agent identifies the software but **not the user** (no personal contact data is sent).
* Retrieved text is untrusted: wrapped before any model sees it, scanned for injection patterns, never followed.
* Only bounded excerpts are stored, with retrieval time, URL, licence note and an expiry; a human can "Save to Archive",
  which creates a curated document with provenance. Generated research answers are labelled "generated conclusion";
  quoted findings are "extracted fact (quoted from source)". A summary is never stored as a source.
* Measured here: Wikipedia rate-limits this host's shared egress IP intermittently (429 with ~20 s Retry-After);
  OpenAlex answered 429 at audit time and is not used.

## 7. Limits and what is not done

* Vision, speech, OCR: no local models installed; reported as unavailable.
* No GPU here: VRAM/GPU panels show "no GPU detected".
* General web search needs an API key; without it, research covers the official sources above only.
* Archive search still scans every chunk (fine at the current size; an inverted index / vector index is the next step
  when the Archive grows — the Performance Engineering Agent will flag it from the route latency).
* The task orchestrator stays single-worker: local inference is serialised per model anyway, and no measurement yet
  shows queueing delay worth the added complexity.
* Semantic (L3) answer reuse only activates with a semantic embedder and a ≥ 0.95 match plus identical numbers/negation;
  it is deliberately conservative.
