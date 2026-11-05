# Agents

All agents live in `backend/app/agents/catalog.py`. Permission levels: 0 research · 1 analysis · 2 drafting ·
3 reversible internal ops · 4 external publishing · 5 financial/contractual. Levels 4–5 additionally require a
human-approved `Approval` for each action. Admins can change levels in the Agent Control Room; agents cannot.

| Agent (id) | Division | Level | Task types | Uses LLM | What it does |
|---|---|---|---|---|---|
| CEO (`ceo`) | executive | 3 | `ceo.evaluate_product`, `ceo.evaluate_pipeline`, `ceo.weekly_review` | no | Runs the opportunity pipeline; weekly ranking; requests `product.launch` approval only for products with score ≥ 65, confidence ≥ 0.6 **and** human-approved compliance |
| Chief Intelligence (`chief_intel`) | executive | 1 | `intel.scan_market`, `trend.analyze` | no | Fans out research to every *configured* connector; computes trends; links trends to products; highlights multi-platform growth |
| CFO (`cfo`) | executive | 1 | `cfo.economics`, `finance.capital_allocation` | no | Unit economics, pricing scenarios, net margin after assumed CAC; capital allocation recommendation (25% reserve) |
| Chief Risk (`risk`) | executive | 3 | `risk.assess` | no | SE/EU compliance checklist; `blocked` / `restricted` / `needs_review`; never overrides a human approval |
| Market Research Division (`research`) | research | 0 | `research.collect` | no | One agent class for every platform connector; stores signals as `TrendObservation`, product candidates as `Product` |
| Product Intelligence (`product_analyst`) | opportunity | 1 | `product.score` | no | Weighted opportunity score with confidence and per-component breakdown; supplier reliability |
| Transformation Lab (`transformation_lab`) | opportunity | 2 | `opportunity.generate` | optional (`enrich: true`) | ≥ 10 transformations across 7 families, top-3 business models, revenue-multiplication questions → `Opportunity` |
| Supplier Intelligence (`supplier_intel`) | opportunity | 2 | `supplier.evaluate`, `supplier.inquiry_draft` | no | Reliability score; professional inquiry draft + `supplier.send_inquiry` approval request (never sends itself) |
| Brand Studio (`brand_studio`) | brand | 2 | `brand.generate` | yes | 3 brand concepts (structured JSON); trademark/domain checks marked `pending` |
| Content & Creative (`content`) | marketing | 2 | `content.generate` | yes | Drafts per creative angle; re-screens copy for health claims / prohibited terms |
| Advertising (`advertising`) | marketing | 2 | `ads.plan` | no | CPM/CPC/CTR/CAC/ROAS per channel from planning assumptions (labelled `assumption`); cannot spend |
| Store Generator (`store_builder`) | commerce | 3 | `store.draft_listing` | no | Creates a Shopify **draft** product (requires approved compliance) and requests `store.publish_listing` approval |
| Experimentation (`experiments`) | operations | 3 | `experiment.evaluate` | no | Scale / iterate / abandon against pre-registered metrics; A/B significance; writes `Lesson` |
| Self-Improvement (`self_improvement`) | operations | 1 | `system.self_evaluate` | no | Forecast MAPE, agent success/failure rates, improvement *proposals* only |

## Rocky Flare agents (`backend/app/agents/flare_agents.py`)

| Agent (id) | Level | Task types | What it does |
|---|---|---|---|
| Rocky Flare Creative Engine (`flare_engine`) | 2 | `flare.directions`, `flare.mutate`, `flare.sideways`, `flare.field_analysis`, `flare.ecosystem`, `flare.campaign_matrix`, `flare.assets`, `flare.revise` | Runs the creative engines; persists graphs, concepts, campaigns and assets |
| Council Chair (`flare_council`) | 2 | `flare.panel`, `flare.council`, `flare.competition`, `flare.discussion`, `flare.judge`, `flare.synthesize` | Spawns persona tasks with dependencies, then synthesises without forcing consensus |
| Persona agents (`p_<persona>`) | 2 | `persona.evaluate`, `persona.concept`, `persona.turn` (addressed by agent id) | One per persona (studio, review panel, Field Ops). Personality is read from the DB on every task |
| Creative Analyst (`p_creative_analyst`) | 1 | `flare.campaign_analysis` | Ranks campaigns by contribution; refreshes Style DNA; writes persona calibration memory |
| Commercial agents (`p_audience_monetization`, `p_digital_assets`, `p_b2b_opportunity`, `p_licensing`, `p_local_opportunity`, `p_subscription_intel`, `p_waste_to_value`, `p_acquisition`) | 1 | `flare.commercial.<module>` | Commercial intelligence modules; recommend only |

Every agent — including the original 14 — carries a persona from the **Personality Registry** (60 personas). Existing agents
use theirs when they sit on panels, councils and discussions (`persona.*` tasks are dispatched by the orchestrator).
Field Operations personas (21): Survival Researcher, Nordic Preparedness Analyst, Bushcraft Product Scout, E-Scooter Intelligence,
E-Bike Intelligence, E-Mobility Engineer, Tactical Design Director, EDC Product Designer, Outdoor Innovation Engineer,
Ancient Symbolism Art Director, Biblical Reference Researcher, Esoteric Visual Researcher, Conspiracy Culture Researcher,
Modular Systems Architect, Product Compatibility Analyst, Safety & Compliance Officer, Outdoor Content Strategist,
Tactical Brand Strategist, Supplier Intelligence Specialist, Product Mutation Specialist, Commercial Portfolio Analyst.

Persona fields are behaviour, not decoration: `evaluation_lens` (weights over 12 criteria), `genre_affinities`,
`novelty_appetite`, `risk_tolerance` (also sets the bar for "support"), `naming_style`, `communication_style`.
Edit them in **Rocky Flare → Personalities**; every change is versioned and audited. Personas have no permission or
budget fields — authority stays in the Agent Control Room.

## Message contract

Every task produces an `AgentMessage` with: agent id, task id, timestamp, summary, findings, evidence, confidence,
epistemic status (`verified | estimate | assumption | hypothesis`), recommendations, estimated financial impact (SEK),
risks, required approvals. Blocked and failed tasks produce `blocked` / `error` messages with the reason.

## Shared system rules for LLM agents

See `BaseAgent.SYSTEM_RULES`: no fabricated figures, statistics, credentials, reviews or testimonials; label every
claim; no impersonation or invented endorsements; no deceptive scarcity or fake discounts; follow EU consumer,
marketing and product-safety law. LLM outputs are constrained to JSON schemas (structured outputs).

## Adding an agent

```python
class MyAgent(BaseAgent):
    id, name, division = "my_agent", "My Agent", "research"
    level, tier = 1, "fast"
    task_types = ("my.task",)

    def handle(self, ctx, task):
        ctx.check("market.research")                # permission gate
        ...                                          # call engines / connectors / ctx.llm(...)
        return AgentOutput(summary="...", result={...}, epistemic="estimate", confidence=0.6)
```

Append it to `ALL_AGENTS`; it is registered, persisted and routable on next start.
