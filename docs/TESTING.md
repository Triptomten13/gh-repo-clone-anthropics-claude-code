# Testing

| Layer | Command | What it covers |
|---|---|---|
| Lint | `cd backend && ruff check .` | style, bugs, security rules (bandit subset) |
| Backend unit + API | `cd backend && python -m pytest -q` | engines, orchestrator governance, AI router/fallback/refusal, Archive, memory screening, canon, G-sus, security primitives, admin access, DAEMON policy/offline/privacy/spend/quota, cache, credentials, model library, prompts, tools, internal AI API, benchmarks, optimiser, crash recovery — with stub providers, no model files needed |
| Control plane | `cd backend && python -m pytest tests/test_control_plane.py` | the 20 acceptance criteria (grants, approvals, self-approval, expiry, Vault access, deletion, classification routing, credentials, audit of tool calls, traces, retry/escalation, budgets under concurrency, fallback, air-gap egress, tamper detection, release gates, user-bounded agents, role permissions, concurrent approval use, rollback) — mapping in CONTROL_PLANE.md §5 |
| Public demo | `make test-demo` (own DEMO_MODE stack) · `DEMO_BASE_URL=https://… make test-demo` (a deployed demo) | 10 visitor scenarios: anonymous landing/status, demo session, sample agent execution, sample workflow, approval-required rejection, permission denial, restricted retrieval, audit record, backend failure, mobile navigation → `frontend/test-results/demo-report.md` (PASS/FAIL); CI runs it against the built container (`demo-image`) |
| Container | CI job `demo-image` | compose file valid (private + demo profile), all-in-one image builds, container starts with DEMO_MODE, `/ready` 200, demo suite passes against it |
| PostgreSQL | `DATABASE_URL=postgresql+psycopg://… python scripts/pg_smoke.py` (empty DB) | migrations to head + main and DAEMON endpoints + evals on PostgreSQL (JSON/SQL portability) |
| Migrations | `alembic upgrade head && alembic downgrade 0003 && alembic upgrade head` | reversible migration 0004 (run on SQLite and PostgreSQL) |
| Frontend | `cd frontend && npx tsc --noEmit && npx next build` | types, build of every route |
| Browser | Playwright scripts (see `.claude/skills/test-and-verify`) | pages render against the live API, no console errors, no horizontal overflow at phone width |
| Evaluations | `POST /api/ai/evals/run` | planner, injection detection, anti-generic gate, retrieval grounding |
| Model benchmark | DAEMON CORE → Benchmarks | 12 graded tasks per model, cost per success (real models) |
| Independence | `python scripts/independence_test.py` | Tests A–G against a live server, real local models, network namespace for offline — see [INDEPENDENCE_TESTS.md](INDEPENDENCE_TESTS.md) |
| Backup | `scripts/backup.sh` → `scripts/restore.sh` | round-trip, `--force` guard, tamper refusal (see BACKUP_RECOVERY.md) |
| Performance | `python scripts/perf_bench.py --label <x> [--models] [--compare <baseline>]` | endpoint p50/p95, SQL per request, RSS, model load churn on a DB copy (+ synthetic rows in the copy only) — results in `docs/perf/` |
| Frontend unit | `make test-unit` (Playwright runner, no browser) | live-stream frame parser, API client errors/timeouts/same-origin, formatters |
| Device workflows | `make test-e2e` | sign-in/out, navigation (tab bar, drawer, back button, sidebar, Ctrl+K, skip link), Archive upload→search→delete, emergency stop, deterministic ask, G-sus chat, download, live feed, keyboard vs tab bar — desktop, iPad, iPhone 13, Pixel 7 (Chromium emulation) |
| Responsive | `make test-responsive` | 27 pages × 11 sizes (320–1920 px, portrait + landscape): no sideways scroll, navigation reachable, no console errors; open-document/dialog/drawer states at 320 px |
| Accessibility | `make test-a11y` | axe-core WCAG 2.0–2.2 A/AA on 10 pages, desktop + phone: no serious/critical violations |
| PWA / offline | `make test-pwa` | Chrome installability, nothing from the API cached, server-down / device-offline / recovery behaviour |
| Web performance | `make test-perf` | TTFB, FCP, LCP, CLS, INP estimate, JS size, DOM size, heap — desktop and throttled phone; budgets CLS ≤ 0.1, LCP ≤ 2.5 s / 4 s |
| Archive retrieval | `python scripts/archive_bench.py --label <x> [--compare archive-baseline]` | search p50/p95 at 2k/10k/20k synthetic chunks (temp DB, fixed seed), cold build, first search after add/delete, RSS, and whether top-k is identical to the baseline — `docs/perf/archive-*.json` |
| System benchmark | `python scripts/system_benchmark.py` | 13 scenarios (deterministic, small model, deep reasoning, research, multi-agent, semantic retrieval, large document, concurrency, low memory, offline, provider failure, network failure, crash recovery) with accuracy, latency, RSS peak, CPU, network bytes, tokens — `docs/benchmarks/` |
| Routing | `POST /api/ai/evals/run` (suite `intel_routing`) + held-out set `evals/datasets/intel_routing_holdout.json` | strategy choice per request category |

`scripts/verify.sh` runs lint, pytest, type check and build in one go. CI (`.github/workflows/ci.yml`) runs pytest,
ruff, the PostgreSQL smoke, dependency audits for Python and npm, the browser suites (Chromium; WebKit + Firefox), and
builds and tests the public demo container. Note: from the cost-intelligence phase until 2026-11-06 every CI run
failed at import (`cryptography` was not declared in requirements.txt); fixed in 3312e78 — check CI after dependency
changes, a green local run proves nothing about a clean install. The independence test is not in CI: it needs the
~2.1 GB of model weights and root for `unshare -n`.

Rules: never weaken or delete a test to get green; never report something as working that was not run; record failed
runs honestly (see the first independence run noted in INDEPENDENCE_TESTS.md).
