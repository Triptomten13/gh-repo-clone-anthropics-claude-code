# DAEMON COST INTELLIGENCE

> Never spend premium intelligence on a task that inexpensive intelligence can solve. Never sacrifice essential
> quality merely to save tokens.

## What exists (and is tested)

| Requirement | Implementation | Where |
|---|---|---|
| Provider discovery & registry | `provider_records` table: website, docs, pricing/terms/privacy URLs, models, facts (free tier, rate/token limits, commercial use, privacy, geography, registration), adapter flag, status, **last verification date and who verified it**. Seeded with what was verifiable at build time; seven discovered API providers are listed as **unverified** with every fact "unknown" | `daemon/registry_seed.py`, DAEMON CORE → Providers & keys |
| Verification | An admin records what they checked on the provider's official documentation, with the URL (`POST /api/daemon/providers/{id}/verify`); the optimiser proposes re-verification of facts older than 90 days | `daemon_routes.py`, `daemon/optimizer.py` |
| Account & key management | Owner attestation required verbatim; Fernet-encrypted at rest (key `CREDENTIALS_KEY` or HKDF from `SECRET_KEY`); never returned by the API or given to agents; validate (Anthropic: a model-list call, no tokens generated), rotate, disconnect (secret destroyed, audit kept), expiry warning; **one active key per provider** — no pools to rotate around limits | `daemon/credentials.py` |
| Intelligent routing | Tier (= required intelligence) + profile + sensitivity + offline mode + external switch + quota + spend limit → ordered chain; local first for fast/standard work, strongest available for deep; private data stays local | `daemon/policy.py`, `ai/router.py` |
| Quota intelligence | Requests/tokens per provider, rate-limit events, exponential backoff (5 s → 15 min, or the server's retry-after), admin pause/resume; a limited provider is skipped, never worked around | `daemon/quota.py` |
| Spending limits | Daily (default `DAILY_COST_LIMIT_USD`), monthly (default $50) and per-provider caps checked **before** every paid call with a conservative estimate; if spend cannot be verified the call is not made; blocked attempts are recorded as `spend_blocked` | `quota.spend_check` |
| Token reduction | Response cache (exact request hash, TTL, actual saving recorded), provider-side prompt caching (`cache_control` on Anthropic calls; cache reads/writes priced at 0.1×/1.25× input), retrieval instead of whole documents, budgeted context assembly with dedupe, structured outputs, local preprocessing/classification, versioned reusable system prompts | `daemon/gateway.py`, `ai/providers.py`, `daemon/prompts.py` |
| Model quality evaluation | 12 graded tasks (classification, Swedish ×2, structured output, instruction adherence ×2, reasoning ×2, abstention, context retention, coding — static check only, tool-call format); accuracy by skill, latency, API cost, estimated energy, **cost per successful task** | `daemon/bench.py` |
| Fallback & resilience | Local → alternative local → LAN workers → authorised external; circuit breakers; refusals never re-routed; no permitted resource ⇒ the task is **blocked with the reason** (never silently charged) | router + orchestrator |
| Dashboard | Total external cost, local share, local energy (estimate), tokens, cached tokens, failed requests, actual vs estimated savings, monthly forecast, cost per agent / workflow / project / model, calls per day local vs external, quality from benchmarks | DAEMON CORE → Costs |
| Autonomous optimisation | Proposals: premium tier for short answers, repeated paid prompts (enable cache), work a benchmarked local model can do, rate-limit trouble, oversized contexts, missing local model, stale provider facts. Deduplicated. **Approval records the decision; nothing changes spending, credentials, accounts or terms automatically** | `daemon/optimizer.py` |

## Measured on this machine (2026-11-05)

| Model | Accuracy | Avg latency | API cost | Cost per success (energy estimate, 65 W, $0.20/kWh) | Failed |
|---|---|---|---|---|---|
| qwen2.5-0.5b-instruct-q4_k_m (local) | 10/12 (83 %) | 0.70 s | $0 | ≈ $0.000003 | both Swedish tasks |
| qwen2.5-1.5b-instruct-q4_k_m (local) | 9/12 (75 %) | 1.27 s | $0 | ≈ $0.000006 | both Swedish tasks, ceiling-division word problem |

No external model was benchmarked: that spends money and needs an explicit `allow_spend: true` from an operator, and no
key is configured in this environment. The energy figure is an estimate, not a measurement — set your own wattage and
tariff in DAEMON settings (`energy`).

## What is not done (honestly)

* The **Provider Discovery Agent** cannot browse in offline-first mode and no research connector is configured, so it
  does not fetch provider documentation itself. It maintains the registry, flags stale or unverified facts and drafts
  verification tasks; a human (or a future research connector) records the verified facts with their source URL.
* **Account creation, terms acceptance and key entry are the account owner's actions.** The system never registers
  accounts, never creates identities and never accepts terms.
* **Semantic (embedding-similarity) response caching** is not enabled: wrong cache hits silently degrade answers, and the
  measured similarity margins of the local embedder are not yet validated for that use. Exact-match caching is on.
* **Provider rate-limit headers** are not parsed into "remaining" counts yet; rate-limit errors drive backoff.
* Cost figures are list-price computations; the provider's invoice is authoritative.
