# G-SUS & Demonkoncernen AB

**G-SUS** is the intelligence (head orchestrator **G-sus**), **Demonkoncernen AB** the infrastructure, the **Archive** the
memory, the agents the workforce — and the human owner stays in control. The company name is one setting
(`COMPANY_NAME`); *Rocky* is the commerce platform and *Rocky Flare* its creative intelligence layer.

**DAEMON CORE** runs the intelligence on Demonkoncernen's own hardware: local models through llama.cpp, a verified model
library, offline mode with no external fallback, an internal AI API with a model-independent G-SUS identity, and cost
intelligence for any external provider used as a guest. Independence Tests A–G pass on CPU-only hardware —
see [docs/INDEPENDENCE_TESTS.md](docs/INDEPENDENCE_TESTS.md) for what that does and does not mean.

A governed multi-agent system that **discovers → analyses → validates → transforms → brands → prices → (with approval) launches**
commercial opportunities, initially for the Swedish / EU market.

**Rocky Flare** is its creative intelligence layer: editable agent personalities, genre intelligence and hybrid fusion,
the Product Mutation Engine, Think Sideways, creative competitions, review panels, councils and discussions, a brand
portfolio, a versioned asset library, campaign testing and learning from real results — plus the **Field Operations**
division for survival, tactical, outdoor and e-mobility products. See [ROCKY_FLARE.md](docs/ROCKY_FLARE.md).

> Status: **Phase 1 (foundation) complete, Phase 3 (opportunity engine) largely complete, Phases 2/4/5 partially
> implemented.** See [ROADMAP.md](docs/ROADMAP.md) for the exact list of completed, partial, blocked and planned features.
> Nothing in this repository claims an integration works unless it is implemented and tested.

## What works today

| Area | State |
|---|---|
| FastAPI backend, PostgreSQL/SQLite, Alembic migrations, auth (admin/operator/viewer) | ✅ tested |
| Orchestrator: task registry, routing, depth limit, loop & duplicate detection, retries, timeouts, token budgets, daily cost cap, kill switch, agent suspension | ✅ tested |
| 14 agents (CEO, Chief Intelligence, CFO, Chief Risk, research division, product analyst, transformation lab, supplier, brand, content, advertising, store builder, experiments, self-improvement) | ✅ deterministic agents tested; LLM agents tested with a fake provider |
| Engines: opportunity scoring, trend velocity/stage detection, unit economics (VAT, duty, fees, returns), pricing scenarios with Omnibus-compliant promotions, 25-model business-model generator, transformation lab, SE/EU compliance checklist, finance & forecasts, capital allocation, experiment decisions & A/B stats | ✅ unit tested |
| Approval center (LEVEL 4–5 actions), audit trail, live WebSocket event bus | ✅ tested |
| Connectors on official APIs: YouTube Data v3, Reddit, eBay Browse, Etsy v3, Shopify Admin (draft products) | ✅ implemented, tested with mocked HTTP; **not exercised against live APIs** (no credentials in this environment) |
| 23 further platforms (TikTok, Instagram, Amazon, Google Trends, AliExpress, Stripe, …) | ⏳ registered as *planned* with access requirements documented |
| Rocky Flare: 60 editable personas, 45-genre taxonomy, fusion, originality gate, mutation engine, think-sideways, competitions/panels/councils/discussions, brand portfolio, assets, campaigns & Style DNA learning | ✅ tested (engine + end-to-end API tests) |
| Field Operations: pillars, segments, ecosystems, Nordic-first sourcing, compatibility matrix, mobility/survival compliance | ✅ tested |
| Next.js command center (10 core sections + 8 Rocky Flare sections + Field Operations with 14 subsections) | ✅ builds, type-checks, verified in a real browser against the live API |
| G-sus Chamber, The Archive (provenance, evidence classes, hybrid search, citations), memory, Archivum canon tools, HQ, AI Core | ✅ tested; evals 1.0 |
| DAEMON CORE: local models (llama.cpp), model library, offline mode, internal AI API, prompts, tools, workers, recovery | ✅ tested; Independence Tests A–G passed with real local models |
| Cost intelligence: provider registry, encrypted credentials, spend limits, caching, benchmarks, cost dashboard, proposals | ✅ tested; real benchmarks of two local models |
| Admin access: first-run setup, `python -m app.cli`, Users & access UI | ✅ tested |

## Quick start (local, no Docker)

```bash
# backend
cd backend
pip install -r requirements-dev.txt
cp ../.env.example ../.env            # optional; defaults work for local use
alembic upgrade head                   # or let the app create tables on first start
uvicorn app.main:app --reload --port 8000
python -m pytest -q                    # 118 tests

# frontend (separate shell)
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Open http://localhost:3000. The first visit asks you to create the admin account (or run
`python -m app.cli create-admin --email you@example.com` in `backend/`). Full guide incl. local models and Docker:
[docs/INSTALL.md](docs/INSTALL.md).
To explore before any connector is configured: **Systems & Integrations → Load demo data**
(synthetic, badged `DEMO` everywhere, removable with one click), then **Product Laboratory → Evaluate pipeline**,
then try **Rocky Flare → Brand Laboratory → Creative competition** or **Field Operations → Creative Council**.

## Docker

```bash
cp .env.example .env   # set SECRET_KEY, ANTHROPIC_API_KEY, connector keys
docker compose up --build
```

Services: `db` (PostgreSQL 16), `api` (runs migrations, then uvicorn), `web` (Next.js standalone), `backup` (daily `pg_dump`, 14-day retention).
The compose file is validated with `docker compose config`; images were not built in the development environment (no Docker daemon available).

## Enabling AI agents

Agents ask for a model *tier* (fast / standard / deep); DAEMON CORE routes it. **Local first:**
`pip install -r backend/requirements-local-ai.txt`, then DAEMON CORE → Models → install and activate a chat, eco and
embedding model. **External (optional guest):** `ANTHROPIC_API_KEY` or a stored, owner-attested credential; tier models
`MODEL_DEEP=claude-opus-5-5`, `MODEL_STANDARD=claude-sonnet-5-5`, `MODEL_FAST=claude-haiku-5-5`, bounded by spend limits.
With no permitted model, LLM-backed tasks end as **blocked** with the reason — they never return invented output.
Deterministic agents (scoring, economics, compliance, trends, business models, experiments) need no AI at all.

## Documentation

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — system design, data model, request/agent flow
- [AGENTS.md](docs/AGENTS.md) — every agent, its task types, permission level and outputs
- [SECURITY.md](docs/SECURITY.md) — permission levels, approvals, kill switch, secrets, data protection
- [INTEGRATIONS.md](docs/INTEGRATIONS.md) — every connector, its state and the credentials it needs
- [ROCKY_FLARE.md](docs/ROCKY_FLARE.md) — creative intelligence layer & Field Operations: modules, workflows, acceptance map
- [ROADMAP.md](docs/ROADMAP.md) — completed / partial / blocked / planned
- [DAEMON_CORE.md](docs/DAEMON_CORE.md) — sovereign AI infrastructure: audit, architecture, plan, limits
- [COST_INTELLIGENCE.md](docs/COST_INTELLIGENCE.md) — provider registry, credentials, routing, limits, benchmarks
- [INDEPENDENCE_TESTS.md](docs/INDEPENDENCE_TESTS.md) — Tests A–G with actual results
- [INSTALL.md](docs/INSTALL.md) — installation, deployment, **admin access** · [BACKUP_RECOVERY.md](docs/BACKUP_RECOVERY.md)
- [AI_SYSTEM.md](docs/AI_SYSTEM.md) · [KNOWLEDGE_SYSTEM.md](docs/KNOWLEDGE_SYSTEM.md) · [DESIGN_SYSTEM.md](docs/DESIGN_SYSTEM.md) ·
  [DECISIONS.md](docs/DECISIONS.md) · [TESTING.md](docs/TESTING.md) · [progress.md](progress.md)

## Repository layout

```
backend/   FastAPI app (app/), Alembic migrations, pytest suite
frontend/  Next.js 16 + React 19 + Tailwind 4 + Recharts command center
docker-compose.yml, .env.example, .github/workflows/ci.yml
```
