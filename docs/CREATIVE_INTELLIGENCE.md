# DAEMON CREATIVE INTELLIGENCE — Creative Tournament Mode and provider autonomy

Agents choose **how** they create — which models, how many, which routing mode. The orchestration engine decides **how
they coordinate**, the policy engine decides **what they may do**, the evaluation system decides **whether the result
is good enough**, and people keep control of sensitive data, spending, permissions and external actions.
Status words: IMPLEMENTED AND VERIFIED · PARTIALLY IMPLEMENTED · DESIGNED BUT NOT IMPLEMENTED · NOT SUPPORTED · CONFIGURATION REQUIRED.

## 1. Creative Tournament Mode (the owner's recommendation)

> *Ask Demonkoncernen for a song: it sends the brief to several models, each writes its own version, two critics judge
> them, and a synthesis agent combines the best rhymes, phrasings, structures and ideas. Every competition has a stop
> condition and a budget — otherwise 27 models debate one line while the token counter retires before them.*

That is what `app/creative/tournament.py` does:

1. **Plan** — the brief is analysed (category, language, complexity, required capabilities). AUTOMATIC uses one model
   for simple work and a tournament only when the task is creative or complex *and* the budget can pay for candidates,
   critics and a synthesis. Contestants are chosen by DAEMON PROVIDER INTELLIGENCE (different model families first).
2. **Candidates** — each contestant writes its own version. Remote models run in parallel; local models run one after
   another (they share this machine's CPU). A failing provider is replaced by the next permitted model and recorded.
3. **Critics** — up to 3 other models score every candidate in one call each, quote the best lines (quotes that do not
   occur in the text are dropped) and name weaknesses. **A critic never grades its own output.** Rule-based checks
   (structure, rhyme, language, topic, repetition, clichés, AI boilerplate, completeness, code syntax) count for 60 %.
4. **Synthesis** — the author of the best round-1 candidate (evidence from this brief outranks a benchmark score) writes
   ONE new version from the top candidates and the critics' notes. It is **rejected** if it is a candidate returned
   unchanged or a paste-up of candidates (both without spending critic calls), or if it scores below the best candidate
   — the result is never worse than something already in hand.
5. **Targeted revision** — only the named weaknesses are fixed; everything else is kept. A revision is attempted only
   when the budget leaves room to judge it; a revision that returns the text unchanged ends refinement without being
   judged again. Scores are compared like for like: when one side has no critic scores, rule score vs rule score.
6. **Learning from earlier tournaments** — a critic whose answers could not be parsed in ≥ 2 earlier tournaments of
   the category is not chosen again (`plan.critics_excluded` says why), and in AUTOMATIC mode a synthesizer whose last
   ≥ 3 syntheses for the category were all rejected is skipped: the tournament becomes a comparison.
7. **Stop** — quality target reached · call / token / USD budget would be exceeded · time limit · diminishing returns
   (a round gains < `min_gain`, default 0.02) · rounds exhausted · no permitted model. The reason is stored and shown.

**Hard caps** whatever is requested: 6 contestants, 3 critics, 4 revision rounds, 40 calls, 3 600 s, 200 000 tokens.
**Budget fields**: `max_calls`, `max_tokens`, `max_usd` (0 = local / verified-free only), `max_seconds`, `max_rounds`,
`max_models`, `critics`. Every call is checked against the remaining budget *before* it is made (synthesis and judging
keep a reserve), and the platform's own budgets (governance budgets) apply on top.
**Value metric**: Creative Value per Resource Unit = final score ÷ (1 + tokens/10 000 + USD/0.01 + minutes), and the
gain per extra call after round 1 — so a tournament that adds calls without adding quality is visible as such.

Strategies: AUTOMATIC · SINGLE · COMPARISON (candidates + critics, best wins) · TOURNAMENT (+ synthesis + revision) ·
ITERATIVE (one model, critic, revisions). The same engine serves songs, poems, names, business ideas, designs (as text
briefs), research summaries and code (Python syntax is checked by parsing; generated code is never executed).

## 2. DAEMON PROVIDER INTELLIGENCE (`app/creative/providers.py`)

Built on the existing router — no competing provider layer:

* `daemon.policy.check_candidate()` is the per-model policy (offline mode, privacy/classification, external master
  switch, quota pause). Tier routing and agents that pick a specific model use the same function.
* `LLMRouter.complete_on(provider, model)` runs one chosen model through the same breakers, rate-limit backoff and
  spend checks; no silent fallback (the tournament decides what to try next).
* `call_model()` reserves the platform budget before the call, settles it after, and traces every attempt.

**Candidates**: installed local models (model library), LAN workers, Ollama, and registry APIs. **Cost classes** and the
FREE-FIRST preference: `local` → `free_tier` (only when verified in the provider registry — none is assumed; today none
is verified) → `open_endpoint` → `low_cost` (≤ $1 per M output tokens) → `premium`. Unverified (discovered) providers
are never routable.

**Routing modes** — FREE_FIRST, BEST_QUALITY, BEST_VALUE, FASTEST, LOCAL_FIRST, PRIVACY_FIRST, CREATIVE_ENSEMBLE,
DEEP_RESEARCH, SPECIALIST, BALANCED. Each candidate gets a score from its **measured quality for the task category**
(else a clearly labelled prior), estimated cost, measured (or size-estimated) latency and locality; every choice and
every exclusion carries a reason ("songwriting 0.62 measured on 2 task(s); local; no API cost; ~9.8 s measured").
A more capable free model beats a weaker local one; a premium model wins only when its measured quality gap outweighs
its cost and the budget allows it (tested both ways).

## 3. Quality and model performance intelligence

* `app/creative/quality.py` — rubrics per category (songwriting, poetry, storytelling, brainstorming, business,
  programming, general). Deterministic share ≥ 0.5 (currently 0.6) so model opinions are never the only evidence.
* Every output is also checked for **echoing the brief**: if ≥ 50 % of its 4-word phrases come from the brief, the
  score is capped (×0.3) with the note "repeats the brief instead of answering it" (found in the first real run, §7).
* `app/creative/perf.py` — a versioned dataset (`creative-bench-2026-11-06.2`; `.2` = scoring with the echo check, so
  profiles measured with the old scoring are listed as due) of Demonkoncernen tasks: Swedish and
  English lyrics, poems, product names (pannier, hand-crank radio), a short story, business ideas (e-scooter
  batteries), a product summary, a Python function. Profiles are stored per model **version** and category with their
  conditions. A changed model file or API model id makes the profile **stale**: the selector discounts it (×0.85, marked)
  and `GET /api/creative/models` lists the model as due for re-benchmarking. Tournament observations are shown apart —
  they are not reproducible and do not overwrite benchmark profiles.

## 4. Governance

| Action | Category | Who |
|---|---|---|
| `creative.tournament` (local / verified-free within budget) | SUPERVISED — runs, recorded | users with `creative.run`, agents (Creative Director) |
| `creative.tournament.paid` (`max_usd` above `CREATIVE_AUTONOMOUS_USD`, default 0.50) | APPROVAL_REQUIRED — a second person approves this exact request | humans approve; agents never |
| `creative.benchmark` | AUTONOMOUS/SUPERVISED by level | `creative.run` |
| `providers.discover` | research | `creative.run` (listing only) |
| `providers.approve` (make a provider routable) | RESTRICTED (four eyes); **prohibited for agents** | security admin + approver |

Restricted data never reaches an unapproved provider: the tournament's classification sets the routing sensitivity
(CONFIDENTIAL → local/LAN, RESTRICTED → this machine, HIGHLY_SENSITIVE → in-process), checked per model. Provider keys
stay in encrypted backend storage; they never appear in prompts, results, traces or API responses (tested).
Saved results go to the Archive as evidence class **model_generated** (collection `creative-library`) with provenance:
models, roles, round, sources, critics, scores, requester, tournament id.

## 5. API and interface

`/api/creative/overview` · `POST /api/creative/select` (routing decision, dry run) · `POST /api/creative/tournaments`
(`wait: false` runs in the background; poll) · `GET /api/creative/tournaments[/{id}]` · `POST …/{id}/save` ·
`GET /api/creative/models` · `POST /api/creative/benchmarks` · `GET /api/creative/providers` (registry, runtimes,
24 h health per model) · `GET /api/creative/discovery` · `GET /api/creative/costs`. Agents use the **Creative
Director** (task type `creative.tournament`). The **Creative Intelligence Center** (`/creative`) has tabs for
tournaments (start, watch, compare candidates, critiques, synthesis, stop reason, usage, save), routing, model quality,
providers & health, and costs.

## 6. Acceptance criteria → tests (`backend/tests/test_creative.py`)

| # | Criterion | Test |
|---|---|---|
| 1 | agent selects a provider without a human | `test_01_an_agent_selects_providers_and_runs_a_tournament_without_a_human` |
| 2 | free/local preferred when good enough | `test_02_free_and_local_models_are_preferred_when_they_are_good_enough` |
| 3 | premium when justified and affordable | `test_03_a_premium_model_wins_when_its_quality_justifies_the_cost_and_the_budget_allows` |
| 4 | several models generate candidates | `test_04_several_models_independently_generate_candidates` |
| 5 | specialists contribute components | `test_05_specialist_roles_contribute_separate_components` |
| 6 | synthesis without concatenation | `test_06_synthesis_combines_instead_of_concatenating` |
| 7 | independent evaluation finds weak output | `test_07_independent_evaluation_identifies_the_weak_output` |
| 8 | provider failure → authorised fallback | `test_08_a_failing_provider_is_replaced_by_an_authorised_alternative` |
| 9 | sensitive data never to unapproved provider | `test_09_restricted_briefs_never_reach_an_external_model` |
| 10 | quotas and rate limits respected | `test_10_a_rate_limited_provider_is_paused_and_not_hammered` |
| 11 | hard budgets cannot be bypassed | `test_11_hard_budgets_cannot_be_bypassed` (tournament budget, platform budget, paid → approval, 27-model cap) |
| 12 | credentials protected | `test_12_provider_credentials_never_appear_in_prompts_results_or_api_responses` |
| 13 | model version change → evaluation | `test_13_a_model_version_change_marks_its_profile_stale_and_due` |
| 14 | stop on diminishing returns | `test_14_refinement_stops_on_diminishing_returns` |
| 15 | provenance retained | `test_15_every_output_keeps_its_provenance` |
| 16 | authorised cache reuse | `test_16_a_repeated_brief_reuses_the_accepted_result_without_model_calls` |
| 17 | repeatable cross-provider comparison | `test_17_benchmarks_compare_models_reproducibly` |
| 18 | works when a provider is unavailable | `test_18_the_workflow_keeps_working_when_a_provider_is_unavailable` |

The tests use fake models with known behaviour (deterministic). Further tests cover what the real runs (§7) exposed:
brief echo, synthesizer chosen from round-1 evidence, like-for-like comparisons, no revision without budget to judge it,
unreliable critics skipped, AUTOMATIC skipping a synthesis that has not paid off, unchanged synthesis/revision rejected
without critic calls, template-echo critiques discarded, plus API governance and G-sus delegation (28 tests in total).

## 7. Real runs on local models (2026-11-06)

Evidence: `docs/benchmarks/creative-2026-11-06.json` (every entry's text, rule checks, critiques, tokens and latency).
Hardware: 4 vCPU Xeon @ 2.1 GHz, 15 GB RAM, no GPU; llama.cpp with GGUF models. No API model was used (no key here).

### Benchmark (dataset `.2`, 10 tasks per model, rule-based scoring, 434 s for 4 models)

| Model | Songs | Poetry | Names | Story | Business | Summary | Code | Song latency |
|---|---|---|---|---|---|---|---|---|
| Qwen3 4B | **0.75** | **0.79** | **0.94** | 0.89 | 0.80 | 0.87 | 0.97 | 21.7 s |
| Qwen2.5 1.5B | 0.66 | 0.73 | 0.90 | **0.92** | **0.83** | **0.90** | **0.98** | 10.1 s |
| Qwen2.5 0.5B | 0.43 | 0.71 | 0.82 | **0.92** | 0.82 | 0.87 | **0.98** | 7.4 s |
| SmolLM2 360M | 0.49 | 0.47 | 0.60 | 0.83 | 0.76 | 0.87 | 0.88 | 7.2 s |

With the first scoring (dataset `.1`) SmolLM2 scored 0.78 on songs, *above* Qwen3 4B, because it answered by repeating
the brief and the rule checks found the brief's topic words and section labels in it. The echo check fixed that.

### Tournament: a Swedish song (TOURNAMENT, target 0.90, budget 9 calls · 3 contestants · 2 critics · 1 revision)

Brief: *"Skriv en låt på svenska om vinterns första snö i en liten norrländsk by. Två verser och en refräng … Gärna rim,
inga klichéer."* Critics: Qwen3 8B and Qwen2.5 0.5B. Same brief and budget each time; the code improved between runs.

| Run | Round-1 candidates (score) | Synthesis | Revision | Calls | Tokens | Time | Result | Stop |
|---|---|---|---|---|---|---|---|---|
| 1 | Qwen3 4B 0.81 · SmolLM2 0.51 · Qwen2.5 1.5B 0.45 | SmolLM2, rejected (0.55) | SmolLM2, rejected (−0.054) | 9 | 6 479 | 319 s | Qwen3 4B draft, 0.81 | diminishing returns |
| 2 | Qwen3 4B 0.81 · Qwen2.5 1.5B 0.55 · SmolLM2 0.20 (echo) | Qwen3 4B, its own draft unchanged, rejected (0.73) | unchanged, rejected | 9 | 5 642 | 496 s | Qwen3 4B draft, 0.81 | diminishing returns |
| 3 | Qwen3 4B 0.83 · Qwen2.5 1.5B 0.53 · SmolLM2 0.22 (echo) | Qwen3 4B, 4 lines changed, rejected (0.77) | not attempted: no budget left to judge it | **8** | 5 458 | 371 s | Qwen3 4B draft, 0.83 | no budget to judge a revision |

Creative value per resource unit: 0.116 · 0.082 · 0.107. Gain per extra call after round 1: **0.0 in all three runs**.
Every run ended below target with "human review suggested".

### What the runs exposed, and what changed

1. **Brief echo** (run 1): SmolLM2 copied the brief and the rule checks gave it full marks for topic and structure →
   echo check, scoring version `.2`.
2. **A weak synthesizer** (run 1): the inflated benchmark score made SmolLM2 synthesizer and reviser → the author of the
   best round-1 candidate synthesizes and revises.
3. **An unfair comparison** (run 2): the revision had no critic scores (budget spent) and its rule score was compared
   with the draft's critic-boosted score → like-for-like comparison.
4. **A revision that could not be judged** (run 2) → a revision is attempted only when the budget leaves room to judge
   it. Run 3 stopped there and used 8 calls instead of 9 for the same result.
5. **A critic that cannot critique**: the 0.5B critic returned nothing parseable in runs 1–2, and in run 3 its one
   "usable" answer listed the prompt's example values ("exact quote", "specific problem") as weaknesses → critic
   reliability is recorded per tournament (`usage.critics`), critics failing in ≥ 2 tournaments are skipped, and
   template-echo critiques are discarded.
6. **Unchanged "new" versions** (run 2): synthesis and revision returned the draft word for word and were judged again
   → rejected without critic calls.
7. **Critic noise**: the same critic (Qwen3 8B) gave the *identical* Qwen2.5 1.5B text 0.11 in run 1 and 0.38 in run 2
   (the candidates were in a different order), and the identical Qwen3 4B text 0.89 as a candidate but 0.69 when it came
   back as a "synthesis". That is why rule checks keep ≥ 60 % of the weight and why a model's score is never the only
   evidence.

### Honest conclusion

* **On this machine, the tournament did not beat the best single model.** In all three runs every synthesis and
  revision was rejected and the result was Qwen3 4B's first draft (0.81–0.83, below the 0.90 target). The lyrics follow
  the structure but have no rhymes, and some phrases are not idiomatic Swedish ("i skumra vänner", "källarvända").
  Small local models do not write good Swedish lyrics, and critics of the same size cannot reliably say why.
* What the tournament did deliver: it chose the best of three drafts, caught the brief echo, stayed inside its budget,
  and stopped honestly instead of claiming quality it did not reach.
* **Cost**: 5–8 minutes and 5 500–6 500 tokens per tournament, against 26–29 s for Qwen3 4B's draft alone — 12–17× the
  time for the same text. On this hardware, a single strong model (SINGLE) or COMPARISON is better value for songs. The engine learns this:
  after 3 rejected syntheses by the same synthesizer in a category, AUTOMATIC stops synthesizing. Qwen3 4B has 2 rejected
  songwriting syntheses so far.
* **Not measured**: whether tournaments pay off with stronger contestants (Qwen3 8B as a writer, or API models). No API key
  is configured here, and an 8B contestant would take several minutes per draft on this CPU.

## 8. Implementation status

| Capability | Status | Notes |
|---|---|---|
| Creative Tournament (candidates, critics, synthesis, revision, budgets, stop conditions) | **IMPLEMENTED AND VERIFIED** | tests 4–7, 11, 14; three real local runs §7 |
| Better results from tournaments than from one model | **NOT DEMONSTRATED** | on local models (≤ 8B, CPU) no synthesis or revision beat the best draft in 3 real runs (§7); stronger models not measured |
| Learning from earlier tournaments (critic reliability, synthesis track record) | **IMPLEMENTED AND VERIFIED** (tests); real effect not yet observed | needs more runs per category |
| Provider selection with 10 routing modes + explanations | **IMPLEMENTED AND VERIFIED** | tests 1–3, 9, 18 |
| Free-first with verified free tiers | **PARTIALLY IMPLEMENTED** | the logic is there; **no free tier is verified** in the registry, so "free" means local today |
| External providers | **CONFIGURATION REQUIRED** | only the Anthropic adapter exists; never called live here (no key); others are discovered candidates without adapters |
| Hugging Face / cloud-hosted open models, image, audio, video generation | **NOT SUPPORTED** | no adapters; tasks needing those capabilities are refused with the reason |
| Specialist collaboration | **PARTIALLY IMPLEMENTED** | role specialisation (generate / critique / synthesize / revise); splitting one task into parts written by different models is not implemented |
| Research-assisted creation | **DESIGNED BUT NOT IMPLEMENTED** | research exists (Research & Monitoring) but is not wired into tournaments |
| Quality intelligence | **IMPLEMENTED AND VERIFIED** for rule checks + model critics; human evaluation: a "human review suggested" stop, no rating UI |
| Model performance profiles, staleness, due list | **IMPLEMENTED AND VERIFIED** | tests 13, 17; real benchmark §7 |
| Provider health | **IMPLEMENTED AND VERIFIED** | breakers, rate-limit pauses, 24 h per-model stats |
| Provider discovery | **PARTIALLY IMPLEMENTED** | lists unverified providers, catalogued models and due benchmarks; no online search for new models |
| Knowledge sharing | **PARTIALLY IMPLEMENTED** | accepted results saved with provenance (model_generated); prompt library / workflow patterns not stored |
| Cost & resource optimisation | **IMPLEMENTED AND VERIFIED** for calls/tokens/USD/time, cache reuse, value per resource unit; per-run RAM/energy not attributed |
