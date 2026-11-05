# Progress — current state (2026-11-05)

## Done and verified

| Area | Evidence |
|---|---|
| Commerce platform (agents, engines, approvals, connectors, dashboard) | pytest, browser checks (Phase 1) |
| Rocky Flare + Field Operations | pytest, browser checks (Phase 2) |
| Master evolution: AI core, Archive, Archivum tools, G-sus head orchestrator, security hardening, dev tooling, new UI | pytest, evals 1.0, PostgreSQL smoke, browser checks |
| Admin access: first-run setup, `python -m app.cli`, Users & access UI, token revocation | `test_daemon.py`, manual CLI run |
| DAEMON CORE: hardware manager, verified model library, llama.cpp runtime, profiles, offline mode, internal AI API, prompts, tools, workers, recovery, fine-tuning feasibility | `test_daemon.py`, Independence Tests A–G **all passed** with real models (docs/INDEPENDENCE_TESTS.md, incl. two failed runs and why) |
| **Local deep reasoning** (owner decision: deep reasoning required, Swedish not): Qwen3 4B in a `deep` slot, two-phase thinking with a budget, incomplete reasoning flagged, working notes kept apart, self-consistency voting, Chamber → Deep reasoning | benchmark 17/17 (deep reasoning 7/7 vs 1–2/7 for the small models); Independence Tests A (self-consistency) and B (offline) solve multi-step problems |
| **DAEMON HYPERINTELLIGENCE**: audit + baseline, telemetry, memory-aware residency + resource modes, rules-first orchestrator (`/api/ai/ask`), deterministic solvers, L1/L2/L3/L4 caches, internet research (10 official sources, QUICK/STANDARD/DEEP, citations, contradictions), monitors, retention, Performance Engineering Agent, delegation report, Control Center + Research pages | `test_hyper.py`, measured before/after (docs/HYPERINTELLIGENCE.md §3), routing eval 30/30 + held-out 12/12, 13-scenario system benchmark |
| DAEMON COST INTELLIGENCE: registry, credentials, routing, quota backoff, spend limits, caches, benchmarks, dashboard, proposals | `test_daemon.py`, real benchmark runs on two local models |
| Backup / restore | round-trip + tamper refusal tested (docs/BACKUP_RECOVERY.md) |
| Docs restructure | docs/ holds architecture, AI system, knowledge, agents, security, design system, decisions, testing, roadmap, DAEMON, cost, install, backup |

Totals: 155 backend tests pass; ruff clean; frontend type-checks and builds (30 routes); migrations 0001–0005 verified
upgrade/downgrade/upgrade on SQLite and PostgreSQL; PostgreSQL smoke passes; Independence Tests A–G pass
(2026-11-05T20:27Z, after the HYPERINTELLIGENCE changes).

## Measured facts worth remembering

* CPU-only host (4 vCPU, 16.9 GB): Qwen2.5 1.5B ~0.8 s per classification, 6–10 s per short chat answer; Qwen2.5 0.5B
  ~0.4 s; Qwen3 4B reasoning ~4–5 tokens/s, ~1 min average per multi-step problem, up to ~5 min.
* 17-task benchmark: 0.5B 11/17 (deep reasoning 1/7), 1.5B 11/17 (2/7), Qwen3 4B 17/17 (7/7).
* A single reasoning sample can be wrong: Qwen3 4B answered −40 instead of 80 on a margin problem (reproducibly in a
  fresh process); self-consistency (3 samples) outvoted it 2/3. Use `samples` + human review for consequential answers.
* The 1.5B model once invented a fact about the company when asked offline; the identity prompt now limits what G-SUS
  may claim about itself.

* Hot paths after optimisation: page view 24 → 10.6 ms (28 → 7 SQL), agents list 124 → 3 SQL, cost dashboard 563 → 186 ms
  at 20k rows; model reloads 5 → 3 in a mixed sequence. Cold model reads run at 14 MB/s on this disk.

## Not done / blocked (honest list)

* Live external connectors (YouTube, Reddit, eBay, Etsy, Shopify) — implemented against official APIs, never exercised
  live (no credentials here).
* Anthropic models — adapter tested with fakes only; no key in this environment.
* Docker images were never built here (no Docker daemon); compose file validated only.
* Multimodal (speech, vision, OCR) — the orchestrator classifies image/audio requests and answers "unavailable" honestly.
* General web search — Brave adapter exists but is off (no key); research uses the 10 official keyless APIs only.
* Provider-verification research connector, LoRA/fine-tuning (needs GPU + training stack), multi-worker task queue
  (one process; background work runs in threads), vector index for the Archive (linear scan, measured 433 ms on the
  1.6 MB benchmark document).
* Wikipedia rate-limits this host's shared egress IP intermittently (429/403 measured); research falls back to other
  sources and reports the failure instead of hiding it.
* Archivum canon content — none exists in the repository; nothing is invented.

## Next sensible steps

1. Run `python scripts/independence_test.py` and `scripts/verify.sh` on the production host.
2. On stronger hardware, benchmark Qwen3 8B (already catalogued and installed here) for the deep slot; with an authorised
   Anthropic key, BALANCED sends deep work to Claude Opus 5.5 first — compare cost per success before choosing.
3. Configure connectors with real credentials one at a time and verify each against its live API.
