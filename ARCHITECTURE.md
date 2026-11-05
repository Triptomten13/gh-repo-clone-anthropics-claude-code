# Architecture

## Overview

```
                ┌──────────────────────────── Next.js command center ───────────────────────────┐
                │ Overview · Radar · Lab · Portfolio · Agents · Finance · Experiments ·          │
                │ Approvals · Archive · Settings          (REST + WebSocket /ws/events)          │
                └───────────────┬───────────────────────────────────────────────┬───────────────┘
                                │ REST (/api/*)                                  │ live events
┌───────────────────────────────▼────────────────────────────────────────────────▼──────────────┐
│ FastAPI                                                                                        │
│  api/routes.py ── auth (PBKDF2 + HMAC tokens, roles) ── approvals ── audit ── kill switch      │
│        │                                                                                       │
│        ▼                                                                                       │
│  agents/orchestrator.py   task registry · routing · depth/loop/dedupe guards · budgets ·       │
│        │                  timeout + retry · single-worker drain · writes AgentMessage + audit │
│        ▼                                                                                       │
│  agents/catalog.py        14 agents ──► engines/* (pure, tested)   ──► ai/llm.py (tiers)       │
│                                     └─► integrations/* (official APIs, rate limited)           │
│  services/scheduler.py    daily / weekly / monthly operating loop (DB-tracked last runs)       │
│  governance/core.py       audit(), EventBus (thread-safe), approvals, system state             │
└───────────────────────────────┬────────────────────────────────────────────────────────────────┘
                                ▼
                     PostgreSQL (prod) / SQLite (dev, tests) · Alembic migrations
```

## Design principles

1. **Engines are pure functions; agents are thin.** All business logic (scoring, economics, pricing, compliance, trends,
   business models, finance, experiments) lives in `backend/app/engines/` with no DB or network access, so it is
   unit-tested in isolation. Agents gather inputs, call engines or an LLM, and return a structured `AgentOutput`.
2. **Honesty is enforced in code, not just prompts.**
   - Unknown inputs never become optimistic defaults: they score neutral and reduce `confidence`.
   - Engagement-only demand is capped (viral ≠ buying).
   - Missing data, credentials, permissions or approvals end a task as `blocked` with the reason.
   - Every agent message carries an epistemic label: `verified | estimate | assumption | hypothesis`.
   - Promotional reference prices require 30-day price history (Omnibus Directive).
   - Demo data is flagged `is_demo` on every row and badged in the UI.
3. **Humans control money, law and the outside world.** Actions ≥ LEVEL 4 always create an `Approval`; compliance is
   only ever *approved* by a human admin; capital allocation is a recommendation.
4. **Modularity.** New platforms = one `Connector` subclass + registry entry. New agents = one `BaseAgent` subclass
   declaring its `task_types`; the orchestrator routes automatically.

## Orchestration

`Orchestrator.submit()` enforces, before a task exists:

| Guard | Mechanism |
|---|---|
| Kill switch | `SystemState["kill_switch"]` checked on submit and before each execution |
| Recursion depth | `depth = parent.depth + 1`, max `MAX_TASK_DEPTH` (default 3) |
| Circular delegation | walks the ancestor chain; identical type+payload ⇒ rejected |
| Duplicate work | SHA-256 of (type, agent, payload); an active or successful task within `DEDUPE_WINDOW_HOURS` is reused (incremental research — unchanged questions are not re-asked) |

`Orchestrator.run_task()` executes with a per-task timeout and up to `max_attempts` retries for *failures*;
`Blocked`, `NotConfigured` and `NotImplementedPlatform` are terminal (`blocked`) and not retried.
Token usage and cost are written to the task and the agent; `check_token_budget()` blocks an agent past its daily budget
and all agents past `DAILY_COST_LIMIT_USD`. Every outcome produces an `AgentMessage` (findings, evidence, confidence,
epistemic, recommendations, financial impact, risks, required approvals) and a bus event.

Execution model: a single in-process worker (`drain()` guarded by a lock) processes the queue by `priority ASC, id ASC`.
Dependent steps are ordered by priority — e.g. `ceo.evaluate_product` spawns `risk.assess (10) → cfo.economics (20) →
product.score (30) → opportunity.generate (40)`. To scale out, run `drain()` in Celery/RQ workers with
`SELECT … FOR UPDATE SKIP LOCKED` claiming and swap `EventBus` for Redis pub/sub (both noted in ROADMAP).

## Data model (backend/app/models.py)

`User`, `Agent`, `Task`, `AgentMessage`, `Product`, `Supplier`, `TrendObservation`, `Trend`, `Opportunity`, `Experiment`,
`Store`, `LedgerEntry`, `Approval`, `AuditLog`, `Lesson`, `SystemState`.

- `LedgerEntry` is the single financial source of truth; every dashboard number is aggregated from it.
- `TrendObservation` stores raw time series per keyword × platform × metric (history for future prediction).
- `Product.score_breakdown` stores each component's score, weight and data coverage for explainability.

## Key algorithms

- **Opportunity score** — weights from the spec (demand 20, momentum 15, profit 20, competition 10, differentiation 10,
  supplier 10, marketing 5, scalability 5, risk-adjusted viability 5). Confidence = weighted data coverage. Bounded (±30)
  audited adjustments by humans/CFO/Risk. Compliance `blocked` caps the score at 25.
- **Trend velocity** — per platform+metric series normalised to its mean; weekly log-growth by least squares;
  acceleration = late − early growth; boosted for independent growth on ≥2 platforms; stage classification incl.
  seasonal (same window last year) and evergreen (low variation over ≥ 6 months).
- **Unit economics** — VAT-exclusive net revenue, landed cost with duty, payment/marketplace fees, returns modelled as
  refunded orders with sunk fulfilment costs and partial stock write-off, break-even CAC and ROAS.
- **Pricing** — margin floor (25% contribution), market-anchored standard price, competitive, premium, bundle,
  subscription; promotional only with verified 30-day lowest price.
- **Business models** — 25 models × 9 attributes, product-trait fit adjustments with explicit reasons; top 3 returned.
- **Experiments** — pre-registered metrics; continue / scale / iterate / abandon; two-proportion z-test; prediction MAPE
  feeds the self-improvement agent.
- **Forecast** — OLS on daily totals with an ≈80% band; refuses with < 14 days of data.

## Frontend

Next.js App Router, all pages client-rendered against the API with a bearer token. `lib/hooks.ts` provides `useApi`
and `useLiveEvents` (auto-reconnecting WebSocket); pages refresh on relevant bus events. Charts use Recharts with a
validated colour-blind-safe palette (single axis, legends + direct labels, tooltips).
