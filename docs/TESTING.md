# Testing

| Layer | Command | What it covers |
|---|---|---|
| Lint | `cd backend && ruff check .` | style, bugs, security rules (bandit subset) |
| Backend unit + API | `cd backend && python -m pytest -q` | engines, orchestrator governance, AI router/fallback/refusal, Archive, memory screening, canon, G-sus, security primitives, admin access, DAEMON policy/offline/privacy/spend/quota, cache, credentials, model library, prompts, tools, internal AI API, benchmarks, optimiser, crash recovery — with stub providers, no model files needed |
| PostgreSQL | `DATABASE_URL=postgresql+psycopg://… python scripts/pg_smoke.py` (empty DB) | migrations to head + main and DAEMON endpoints + evals on PostgreSQL (JSON/SQL portability) |
| Migrations | `alembic upgrade head && alembic downgrade 0003 && alembic upgrade head` | reversible migration 0004 (run on SQLite and PostgreSQL) |
| Frontend | `cd frontend && npx tsc --noEmit && npx next build` | types, build of every route |
| Browser | Playwright scripts (see `.claude/skills/test-and-verify`) | pages render against the live API, no console errors, no horizontal overflow at phone width |
| Evaluations | `POST /api/ai/evals/run` | planner, injection detection, anti-generic gate, retrieval grounding |
| Model benchmark | DAEMON CORE → Benchmarks | 12 graded tasks per model, cost per success (real models) |
| Independence | `python scripts/independence_test.py` | Tests A–G against a live server, real local models, network namespace for offline — see [INDEPENDENCE_TESTS.md](INDEPENDENCE_TESTS.md) |
| Backup | `scripts/backup.sh` → `scripts/restore.sh` | round-trip, `--force` guard, tamper refusal (see BACKUP_RECOVERY.md) |
| Performance | `python scripts/perf_bench.py --label <x> [--models] [--compare <baseline>]` | endpoint p50/p95, SQL per request, RSS, model load churn on a DB copy (+ synthetic rows in the copy only) — results in `docs/perf/` |
| System benchmark | `python scripts/system_benchmark.py` | 13 scenarios (deterministic, small model, deep reasoning, research, multi-agent, semantic retrieval, large document, concurrency, low memory, offline, provider failure, network failure, crash recovery) with accuracy, latency, RSS peak, CPU, network bytes, tokens — `docs/benchmarks/` |
| Routing | `POST /api/ai/evals/run` (suite `intel_routing`) + held-out set `evals/datasets/intel_routing_holdout.json` | strategy choice per request category |

`scripts/verify.sh` runs lint, pytest, type check and build in one go. CI (`.github/workflows/ci.yml`) runs pytest,
ruff, the PostgreSQL smoke and dependency audits for Python and npm. The independence test is not in CI: it needs the
~2.1 GB of model weights and root for `unshare -n`.

Rules: never weaken or delete a test to get green; never report something as working that was not run; record failed
runs honestly (see the first independence run noted in INDEPENDENCE_TESTS.md).
