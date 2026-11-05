# Roadmap

Legend: ✅ complete & tested · 🟡 partial · ⛔ blocked (external dependency) · ⏳ planned

## Phase 1 — Foundation ✅
- ✅ Application structure (FastAPI backend, Next.js frontend), env-based config
- ✅ Database schema (16 tables), Alembic migration `0001`, verified on SQLite and PostgreSQL 16
- ✅ Authentication (first-run admin, login, roles admin/operator/viewer)
- ✅ Orchestrator with governance guards (depth, loops, dedupe, retries, timeouts, budgets, cost cap, kill switch, suspension)
- ✅ Structured message bus, audit trail, live WebSocket feed
- ✅ Command center: 10 sections, verified in a real browser against the API
- ✅ CI workflow (pytest + migrations on Postgres, typecheck + build)
- 🟡 Docker: Dockerfiles + compose (with backups) written and `docker compose config` validated; images not built in dev env (no Docker daemon)

## Phase 2 — Market intelligence 🟡
- ✅ Connector framework (rate limiting, NotConfigured, status reporting), research agent, market scan fan-out
- ✅ Trend engine (velocity, acceleration, 7 stages, cross-platform confirmation), historical observation storage
- ✅ Connectors: YouTube, Reddit, eBay, Etsy (mock-tested)
- ⛔ Live verification of connectors — needs credentials
- ⏳ TikTok, Instagram, Amazon, Google Trends, Pinterest, AliExpress, Alibaba, CJ, Walmart, Mercado Libre, Product Hunt, Faire adapters (access programmes required)
- ⏳ Predictive trend model trained on stored history (needs months of observations)

## Phase 3 — Opportunity engine ✅
- ✅ Weighted opportunity scoring with confidence, engagement cap, audited bounded adjustments
- ✅ Business model generator (25 models, top 3 with reasons)
- ✅ Product Transformation Lab (≥ 10 concepts, 7 families, optional LLM enrichment) + revenue multiplication questions
- ✅ Supplier reliability score + inquiry drafts (sending approval-gated)
- ✅ Unit economics (VAT, duty, fees, returns, CAC) and pricing scenarios with Omnibus rule
- ⏳ Relationship graph (products ↔ audiences ↔ suppliers ↔ trends ↔ models) — tables exist, graph queries not built

## Phase 4 — Brand & commerce 🟡
- ✅ Brand Studio agent (LLM, structured output; trademark/domain checks flagged pending)
- ✅ Shopify draft listing + publish approval request
- ✅ Pricing intelligence (scenarios); live price changes are LEVEL 4 actions
- ⏳ Trademark (EUIPO/PRV) and domain availability checks
- ⏳ Publishing an approved listing (execute step after approval), WooCommerce, Printful/Printify fulfilment
- ⏳ Stripe/PayPal/Klarna ledger sync (ledger import works today)

## Phase 5 — Marketing factory 🟡
- ✅ Content agent (multi-angle drafts + claim screening), Advertising planning agent (funnel economics)
- ⏳ SEO research agent, influencer discovery (needs platform APIs), campaign analytics ingestion

## Phase 6 — Autonomous operations 🟡
- ✅ Scheduler (daily scan + pipeline, weekly CEO review, monthly self-evaluation), DB-tracked runs, manual tick
- ✅ Approval center, financial monitoring & forecasts, capital allocation recommendations, experiments with decisions
- ⏳ Multi-worker execution (Celery/RQ + `SKIP LOCKED` claiming) and Redis pub/sub bus for multiple API replicas
- ⏳ Event triggers from external webhooks (orders, refunds, price changes)
- ⏳ Customer intelligence (requires consented order/support data source)

## Phase 7 — Self-improvement 🟡
- ✅ Prediction error tracking (experiments), agent performance metrics, improvement proposals (never auto-applied)
- ⏳ Recalibrating scoring weights from outcomes (needs a history of launched products)
- ⏳ Vector memory / retrieval over the intelligence archive

## Known limitations
- Single in-process task worker; long LLM tasks run sequentially.
- The compliance engine is keyword-based decision support; it is conservative and must be reviewed by a human.
- Advertising benchmarks are planning assumptions until real campaign data is ingested.
