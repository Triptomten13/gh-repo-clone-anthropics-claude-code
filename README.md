# Rocky — Autonomous Commerce Intelligence Platform

A governed multi-agent system that **discovers → analyses → validates → transforms → prices → (with approval) launches**
commercial opportunities, initially for the Swedish / EU market.

> Status: **Phase 1 (foundation) complete, Phase 3 (opportunity engine) largely complete, Phases 2/4/5 partially
> implemented.** See [ROADMAP.md](ROADMAP.md) for the exact list of completed, partial, blocked and planned features.
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
| Next.js command center (10 sections) | ✅ builds, type-checks, verified in a real browser against the live API |

## Quick start (local, no Docker)

```bash
# backend
cd backend
pip install -r requirements-dev.txt
cp ../.env.example ../.env            # optional; defaults work for local use
alembic upgrade head                   # or let the app create tables on first start
uvicorn app.main:app --reload --port 8000
python -m pytest -q                    # 38 tests

# frontend (separate shell)
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Open http://localhost:3000. The first visit asks you to create the admin account.
To explore before any connector is configured: **Systems & Integrations → Load demo data**
(synthetic, badged `DEMO` everywhere, removable with one click), then **Product Laboratory → Evaluate pipeline**.

## Docker

```bash
cp .env.example .env   # set SECRET_KEY, ANTHROPIC_API_KEY, connector keys
docker compose up --build
```

Services: `db` (PostgreSQL 16), `api` (runs migrations, then uvicorn), `web` (Next.js standalone), `backup` (daily `pg_dump`, 14-day retention).
The compose file is validated with `docker compose config`; images were not built in the development environment (no Docker daemon available).

## Enabling AI agents

Set `ANTHROPIC_API_KEY`. Agents ask for a model *tier*, mapped in `.env`:
`MODEL_DEEP=claude-opus-5-5`, `MODEL_STANDARD=claude-sonnet-5-5`, `MODEL_FAST=claude-haiku-5-5`.
Without a key, LLM-backed tasks (brand concepts, content drafts, AI-enriched transformations) end as **blocked** with the reason — they never return invented output.
Deterministic agents (scoring, economics, compliance, trends, business models, experiments) need no AI at all.

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — system design, data model, request/agent flow
- [AGENTS.md](AGENTS.md) — every agent, its task types, permission level and outputs
- [SECURITY.md](SECURITY.md) — permission levels, approvals, kill switch, secrets, data protection
- [INTEGRATIONS.md](INTEGRATIONS.md) — every connector, its state and the credentials it needs
- [ROADMAP.md](ROADMAP.md) — completed / partial / blocked / planned

## Repository layout

```
backend/   FastAPI app (app/), Alembic migrations, pytest suite
frontend/  Next.js 16 + React 19 + Tailwind 4 + Recharts command center
docker-compose.yml, .env.example, .github/workflows/ci.yml
```
