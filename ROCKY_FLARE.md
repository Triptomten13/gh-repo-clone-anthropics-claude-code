# ROCKY FLARE — Creative Intelligence Layer & Field Operations

Rocky Flare is the creative and strategic DNA of the platform. It is **not** a personality prompt bolted onto
agents: it is a set of structured engines, editable persona data and orchestrated workflows whose outputs are
typed, scored, explained and testable. It runs inside the existing orchestrator, permission system, approval
centre, compliance engine and ledger. Nothing in it can spend money, publish, or approve compliance.

## 1. Migration plan (as executed)

| Step | Finding | Decision |
|---|---|---|
| Inspect repository | FastAPI + SQLAlchemy + orchestrator with governance; engines are pure and tested | Rocky Flare follows the same pattern: pure engines in `backend/app/flare/`, thin agents in `agents/flare_agents.py` |
| Inspect agents | 14 agents, routed by task type; no join mechanism for multi-agent work | Added **task dependencies** (`Task.depends_on`) so councils/panels/competitions synthesise only after members finish |
| Inspect database | No brand, persona, asset or graph tables | Migration **0002** adds 15 tables + new columns (`products.brand_id`, `ledger_entries.brand_id/customer_ref`, supplier certification fields, `tasks.depends_on`), with server defaults so existing rows upgrade cleanly. Verified upgrade → downgrade → upgrade on SQLite and PostgreSQL 16 |
| Inspect integrations | Connector framework with honest "planned" states | Image generation uses the same honesty: a real offline procedural SVG provider, external image models registered as planned |
| Reusable components | Compliance engine, economics/pricing, business models, approvals, audit, event bus | Compliance **extended** (mobility, survival, PPE, blades …) so the existing Risk agent covers Field Ops automatically; CFO economics feed campaign budgets; approvals gate brand/campaign launches |
| Gaps | No personalities, creative engines, collaboration records | Built as described below |
| Preserve functionality | 39 pre-existing tests | All still pass; the CEO pipeline now also sends every evaluated product through the Mutation Engine |

## 2. Modules

| Module | Code | What it does |
|---|---|---|
| Personality Registry | `flare/personas.py`, `models.Persona*` | 60 personas (executive, studio, commercial, 21 Field Ops). Structured fields: lens weights over 12 criteria, genre affinities, novelty appetite, risk tolerance, naming & communication style, biases, tools. Editable in the dashboard, versioned, audited. **No permission/budget fields.** |
| Genre taxonomy | `flare/taxonomy.py` | 45 genres in 4 families (structural, cultural, nature, narrative/pillar D) with palette, type, materials, surfaces, graphic language, photography, packaging, web, social, advertising, price-tier fit, functional affinities, video fit, cost, scalability, recognisability, naming vocabulary, sensitivity flags, clashes |
| Genre-to-Market matching | `flare/genres.py` | Scores every genre against product function tags, price tier (vs. competitor median), channel fit, recognisability, competitor aesthetics (blend-in penalty), sensitivity (e.g. occult codes on pet/kids products) and **learned** Style DNA adjustments |
| Hybrid fusion | `flare/genres.py` | Combines 2–4 genres into a full hybrid (name, concept, philosophy, audience, palette, typography, materials, surfaces, graphic language, applications, packaging, photography, marketing identity); compatibility + clash detection; novelty tracked in `custom_genres` |
| Creative directions | `flare/genres.py` | ≥5 diverse directions per product with the 11 brand-system fields and 7 evaluation scores |
| Originality score + Anti-Generic Filter | `flare/originality.py` | 7 components; flags generic names, template suffixes, AI phrases, overused slogans, buzzwords, empty descriptions, no target customer, predictable palettes (OKLab ΔE vs. stock palettes), unsubstantiated claims, conspiracy-as-fact, real agency names; trademark pre-screen (known marks only); sensitivity reviews. Blocking flags ⇒ `needs_revision`, approval refused until revised |
| Concept authoring & revision | `flare/creative.py` | A persona authors a concept from its own lens/affinities; deterministic revision loop until the gate passes; revisions are new versions (lineage) |
| Mutation Engine 2.0 | `flare/mutation.py` | 15 mutation types, each labelled `existing_product` / `supplier_customization` (only if the supplier record documents it) / `proposed_modification` / `original_concept`; scored on value, cost, complexity, differentiation, profit, regulatory risk (via the compliance engine); ranked; graph persisted. Subscriptions only when a recurring need exists |
| Survival Innovation Lab | `flare/mutation.py` | The 14 field questions with a concrete verification step for each (e.g. IEC 60529 before "waterproof", −20 °C test before "winter") |
| Think Sideways | `flare/sideways.py` | Scores 16 domains by distance + shared trait bridge; 5 items × 8 categories, high-potential combinations, cross-industry graph; 11 Field Ops challenge presets; free-form questions mapped to modes; optional LLM ideas |
| Campaigns & Creative Analyst | `flare/campaigns.py` | 8 campaign identities × platforms testing matrix with hook, message, visual, video format, CTA, test budget (= 20 orders × break-even CAC) and measurement criteria; analyst ranks by **contribution after ads**, reports when engagement leaders differ |
| Style DNA, genre evolution, reuse, calibration | `flare/learning.py` | Learned ±10-point adjustments per genre/identity/platform from real performance (Bayesian shrinkage); evolution from ROI over time + imported `aesthetic:<genre>` observations; reuse of templates/formats (never identity assets); persona calibration (score vs. realised profit) |
| Brand Portfolio Manager | `flare/portfolio.py` | Per-brand revenue, contribution, growth, conversion, marketing cost, retention (if consented customer refs exist), branded-search recognition, complexity; overlap detection blocks unnecessary brands; extension opportunities |
| Creative assets | `flare/assets.py` | Provider interface; procedural SVG palette boards, wordmarks, sigils, packaging fronts; text briefs (photography, packaging, landing page, ad concepts, brand guidelines); versioned with lineage, approve/reject, searchable |
| Commercial modules | `flare/commercial.py` | Audience monetisation, digital assets, B2B, licensing (owned IP only), Nordic local opportunity, subscription intelligence (never forced), waste-to-value (permit notes), acquisition screening (offers need LEVEL 5) |
| Personalisation guard | `flare/personalization.py` | Only customer-entered data with a purpose; rejects inferred/social-media data, sensitive-category profiling, profile-based pricing/urgency |
| Field Operations | `flare/field.py` | 4 pillars, 16 customer segments (hypotheses), 3 modular ecosystems, mounting standards, documentation requirements per compliance category, Nordic-first sourcing ranking, compatibility matrix |

## 3. Orchestrated workflows

All are tasks in the central orchestrator (budgets, kill switch, suspension, dedupe, depth limits, audit apply):

| Task | Agent | Flow |
|---|---|---|
| `flare.competition` | Council Chair | spawns `persona.concept` for N creatives (independent) → `flare.judge` (depends on all) → `persona.evaluate` per judge → `flare.synthesize`. **All concepts are saved**; winner is only *shortlisted* |
| `flare.panel` | Council Chair | Creative Director, Marketing Strategist, Target Audience Analyst, Commercial Analyst, Devil's Advocate evaluate each concept → synthesis with mean, spread, stances, dissent |
| `flare.council` | Council Chair | 8 seats (Creative Director, Tactical Design Director, Survival Researcher, E-Mobility Engineer, Ancient Symbolism AD, Commercial Analyst, The Accountant, Devil's Advocate) → best functional design, best creative direction, best brand opportunity, best monetisation, technical risks, regulatory risks, recommended next experiment |
| `flare.discussion` | Council Chair | Scout → Visionary → Architect → Accountant → Devil's Advocate → Creative Director → CEO, each turn depending on the previous; CEO decision rule creates a **draft, zero-budget** experiment or asks to iterate; dissent recorded |
| `flare.directions`, `flare.mutate`, `flare.sideways`, `flare.field_analysis`, `flare.ecosystem`, `flare.campaign_matrix`, `flare.assets`, `flare.revise` | Flare Engine | engine runs, results stored as typed outputs |
| `flare.campaign_analysis` | Creative Analyst | ranks campaigns, refreshes Style DNA, writes persona calibration memory |
| `flare.commercial.<module>` | 8 commercial agents | module analysis |

Any agent that carries a persona (CEO, CFO, Risk, Chief Intelligence, Transformation Lab, Brand Studio, Advertising …) can sit
on panels and councils: `persona.*` tasks are dispatched by the orchestrator, and permissions are still checked per action.

**No forced consensus:** synthesis reports a split verdict when scores spread (> 12 points) or stances conflict, lists every
dissent with its reason, and never deletes losing concepts. The support threshold depends on each persona's risk tolerance,
so sceptics need more evidence than visionaries before they say yes.

## 4. Honesty and control rules enforced in code

* Engines never invent market data; missing evidence lowers confidence or produces "insufficient evidence".
* Every output carries reasoning and an epistemic label; concepts, mutations and sideways ideas are `hypothesis`.
* Compatibility defaults to `unverified`; `verified` requires written evidence and records who verified it.
* "Universal fit", "100% waterproof", "military-grade" etc. block a product until evidence exists.
* Speed-unlock / derestriction products are prohibited.
* Conspiracy and archive aesthetics must read as fiction; real agency names and seals are blocked; sacred names trigger a respectful-use review.
* Known trademark conflicts (e.g. "Black Mirror", "G-Sus") block a concept; every name still needs an official EUIPO/PRV search, recorded by an admin before a brand can request launch.
* Concept approval: admin only, and only after the anti-generic gate passes. Brand launch: LEVEL 4 approval. Campaign launch: LEVEL 5 approval.

## 5. Acceptance criteria → evidence

| # | Criterion | Tests |
|---|---|---|
| 1 | Editable individual personalities | `test_1_2_personas_editable_versioned_and_distinct` |
| 2 | Distinct roles & creative preferences | same + `test_personas_measurably_differ_and_lens_edit_changes_score`, `test_support_bar_depends_on_risk_tolerance` |
| 3 | Generate & compare genres for a product | `test_3_4_genres_compared_and_hybrids_fused`, `test_genre_matching_is_product_driven`, `test_directions_at_least_five_distinct_with_all_fields` |
| 4 | Hybrid directions | `test_fusion_hybrid_fields_and_novelty_and_clash` |
| 5 | Mutation Engine | `test_5_mutation_engine_and_graph`, `test_mutation_engine_statuses_graph_and_ranking` |
| 6 | Think Sideways | `test_6_think_sideways_and_challenges`, `test_think_sideways_five_per_category_with_bridges` |
| 7 | Independent creative concepts | `test_7_8_9_…`, `test_persona_concepts_differ_and_pass_gate` |
| 8 | Review panel | `test_7_8_9_…`, `test_council_outputs` |
| 9 | Concepts saved & compared | `test_7_8_9_…` |
| 10 | Asset version history | `test_10_assets_versioned_and_approval` |
| 11 | Campaigns ↔ performance | `test_11_12_campaigns_performance_learning` |
| 12 | Learns from results | `test_style_dna_learns_from_results_and_feeds_matrix`, `test_learned_adjustment_changes_ranking` |
| 13 | Brand Portfolio Manager | `test_13_brand_portfolio_overlap_and_launch_gate` |
| 14 | Financial & compliance controls | `test_14_financial_and_compliance_controls_still_hold` + all original tests |
| 15 | Command-centre integration | 8 Rocky Flare pages + Field Operations (14 subsections), verified in a browser |
| 16 | Tests & docs | 73 backend tests; this document |

## 6. Known limitations

* Deterministic persona judgement is a transparent heuristic (lens-weighted criteria), labelled `heuristic`. With an
  Anthropic key, personas can additionally voice concepts and generate sideways ideas (`use_llm`), still gated by the filter.
* External image-generation providers are planned adapters; only the procedural SVG provider is implemented.
* Segment profiles, domain bridges and mounting standards are curated knowledge to validate, not measured market data.
* Style DNA needs recorded campaign performance; until then it reports "insufficient evidence".
* Trademark screening is a known-marks pre-screen only.
