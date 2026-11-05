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
| DAEMON COST INTELLIGENCE: registry, credentials, routing, quota backoff, spend limits, caches, benchmarks, dashboard, proposals | `test_daemon.py`, real benchmark runs on two local models |
| Backup / restore | round-trip + tamper refusal tested (docs/BACKUP_RECOVERY.md) |
| Docs restructure | docs/ holds architecture, AI system, knowledge, agents, security, design system, decisions, testing, roadmap, DAEMON, cost, install, backup |

Totals: 128 backend tests pass; ruff clean; frontend type-checks and builds (28 routes); migrations 0001–0004 verified
upgrade/downgrade/upgrade on SQLite and PostgreSQL.

## Measured facts worth remembering

* CPU-only host (4 vCPU, 16.9 GB): Qwen2.5 1.5B ~0.8 s per classification, 6–10 s per short chat answer; Qwen2.5 0.5B
  ~0.4 s; Qwen3 4B reasoning ~4–5 tokens/s, ~1 min average per multi-step problem, up to ~5 min.
* 17-task benchmark: 0.5B 11/17 (deep reasoning 1/7), 1.5B 11/17 (2/7), Qwen3 4B 17/17 (7/7).
* A single reasoning sample can be wrong: Qwen3 4B answered −40 instead of 80 on a margin problem (reproducibly in a
  fresh process); self-consistency (3 samples) outvoted it 2/3. Use `samples` + human review for consequential answers.
* The 1.5B model once invented a fact about the company when asked offline; the identity prompt now limits what G-SUS
  may claim about itself.

## Not done / blocked (honest list)

* Live external connectors (YouTube, Reddit, eBay, Etsy, Shopify) — implemented against official APIs, never exercised
  live (no credentials here).
* Anthropic models — adapter tested with fakes only; no key in this environment.
* Docker images were never built here (no Docker daemon); compose file validated only.
* Multimodal (speech, vision, OCR), semantic response cache, rate-limit header parsing, research connector for provider
  verification, LoRA/fine-tuning (needs GPU + training stack), multi-worker task queue.
* Archivum canon content — none exists in the repository; nothing is invented.

## Next sensible steps

1. Run `python scripts/independence_test.py` and `scripts/verify.sh` on the production host.
2. On stronger hardware, benchmark Qwen3 8B (already catalogued and installed here) for the deep slot; with an authorised
   Anthropic key, BALANCED sends deep work to Claude Opus 5.5 first — compare cost per success before choosing.
3. Configure connectors with real credentials one at a time and verify each against its live API.
