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

## Rocky Flare & Field Operations ✅ (see ROCKY_FLARE.md)
- ✅ Personality registry (60 personas, editable, versioned, audited), persona agents in the orchestrator, task dependencies
- ✅ Genre taxonomy (45), matching, fusion, ≥5 directions, originality score + anti-generic gate, revisions as versions
- ✅ Mutation Engine 2.0 + Survival Innovation Lab, Think Sideways + challenges, cross-industry graphs
- ✅ Creative competition, review panel, creative council, structured discussions (dissent recorded, no forced consensus)
- ✅ Campaign testing matrix, performance ingestion, creative analyst, Style DNA learning, persona calibration, genre evolution, creative reuse
- ✅ Brand Portfolio Manager (overlap detection, trademark + launch gates), creative asset library (procedural SVG, versions)
- ✅ Eight commercial modules, personalisation privacy guard
- ✅ Field Ops: pillars, 16 segments, ecosystems, mounting standards, Nordic-first sourcing, compatibility matrix, extended compliance
- 🟡 LLM persona voice / sideways ideas implemented and tested with a fake provider; ⛔ not exercised live (no API key here)
- ⏳ External image-generation adapters (OpenAI Images, Stability AI, Replicate) — registered as planned
- ⏳ Official trademark search integration (EUIPO / PRV) — manual recording by an admin today
- ⏳ Ad-platform performance sync (Meta/TikTok/Google) — manual or imported rows today

## Master evolution — G-SUS & Demonkoncernen ✅
- ✅ Provider-independent AI core (tiers, fallback, breakers, tracing), Archive (provenance, evidence classes, hybrid
  retrieval, citations, memory), Archivum canon tools (empty until real canon is imported), G-sus head orchestrator,
  security hardening, Claude Code dev tooling, new interface (Chamber, Archive, Archivum, HQ, AI Core)
- ✅ docs/ restructure: AI_SYSTEM, KNOWLEDGE_SYSTEM, DESIGN_SYSTEM, DECISIONS, TESTING, progress.md

## DAEMON CORE & Cost Intelligence ✅ (see DAEMON_CORE.md, COST_INTELLIGENCE.md)
- ✅ Hardware manager, verified local model library (install / offline import / activate / rollback / remove)
- ✅ In-process llama.cpp runtime, OpenAI-compatible workers, local GGUF embeddings
- ✅ Execution profiles, offline mode without external fallback, privacy routing
- ✅ Internal AI API (chat, generate, embeddings, classify, reason, agents/execute, health, status) with G-SUS identity layer
- ✅ Versioned prompts, context assembly, tool registry (code execution blocked by design)
- ✅ Provider registry, encrypted owner-attested credentials, quota backoff, spend limits, response + prompt caching,
  benchmarks with cost per success, cost dashboard, optimisation proposals
- ✅ Crash recovery, backup/restore scripts, admin CLI and user management
- ✅ Independence Tests A–G passed on CPU-only hardware (INDEPENDENCE_TESTS.md)
- ✅ Local deep reasoning: Qwen3 4B reasoning model in a `deep` slot, thinking budget, flagged incomplete reasoning,
  Chamber → Deep reasoning; benchmark 17/17 (deep reasoning 7/7). Swedish dropped as a requirement (D-014)
- ⏳ Stronger local models (needs more RAM/GPU), multimodal (local STT/TTS/vision), semantic response cache,
  rate-limit header parsing, research connector for provider verification, LoRA (needs GPU + training stack)

## DAEMON HYPERINTELLIGENCE ✅ (see HYPERINTELLIGENCE.md)
- ✅ Audit + measured baseline; telemetry (system, routes, SQL, network, events); memory-aware model residency and
  resource modes; rules-first orchestrator with deterministic solvers; multi-layer caches; internet research over 10
  official sources with depth levels, citations and contradiction flags; monitors with change detection; retention;
  Performance Engineering Agent; delegation report; Control Center and Research pages; 13-scenario system benchmark
- ⏳ Vision/speech models, keyed web search (needs a key), Archive inverted/vector index (when the Archive grows),
  multi-worker orchestration (when measurements show queueing)

## Known limitations
- Local models are much weaker than frontier models; deep reasoning on CPU takes ~1–5 minutes per problem (Qwen3 4B).
- Single in-process task worker; long LLM tasks run sequentially.
- The compliance engine is keyword-based decision support; it is conservative and must be reviewed by a human.
- Advertising benchmarks are planning assumptions until real campaign data is ingested.
- Persona judgement without an LLM is a transparent lens-weighted heuristic (labelled `heuristic`).
- Segment profiles, think-sideways bridges and mounting standards are curated knowledge to validate, not market data.
