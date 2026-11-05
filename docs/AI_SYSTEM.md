# AI system

How models are chosen, called, traced and evaluated. Sovereign/local operation is detailed in
[DAEMON_CORE.md](DAEMON_CORE.md); costs in [COST_INTELLIGENCE.md](COST_INTELLIGENCE.md).

## Principles

* Agents ask for a **tier** (`fast`, `standard`, `deep`), never a vendor model.
* No model output is ever invented: when no permitted provider can serve a request, `LLMUnavailable` is raised and the
  task is **blocked** with the reason.
* A **refusal** is never silently re-routed to another provider.
* Every attempt — success, failure, fallback, exclusion by policy, cache hit — is recorded in `llm_calls`
  (provider, model, tier, status, tokens, list-price cost, latency, locality, workflow/project, energy estimate).

## Components (`backend/app/ai`, `backend/app/daemon`)

| Module | Responsibility |
|---|---|
| `ai/registry.py` | Model metadata: capabilities, context, output cap, list prices (Anthropic table cached 2026-10), intended use. Local models have no API price. |
| `ai/providers.py` | Adapters: Anthropic SDK (adaptive thinking, effort per tier, structured output, server-side refusal fallback for Opus/Sonnet 5.5, automatic prompt caching), Ollama, local hash embedder. Errors are classified as *unavailable* (may fall back) or *refused* (never). |
| `daemon/runtime.py` | In-process llama.cpp provider over the model library; OpenAI-compatible worker provider; local GGUF embedder. |
| `daemon/policy.py` | Builds the ordered candidate chain from tier, execution profile, sensitivity, offline mode, external switch and quota. |
| `ai/router.py` | Walks the chain: circuit breakers, spend checks before paid calls, rate-limit backoff, attempt records. |
| `ai/llm.py` | `get_provider()` — the router when any provider (local model, worker, authorised API) is configured, otherwise an honest "none". Re-evaluated per call, so activating a model needs no restart. |
| `daemon/gateway.py` | Internal AI API path: response cache, tracing with workflow/project, energy estimate. |
| `daemon/prompts.py` | Versioned prompts incl. the model-independent **G-SUS identity**, token estimates, context assembly. |
| `ai/tracing.py` | Persists attempts; usage summaries. |
| `evals/` | Regression evaluations (below). `daemon/bench.py` — model benchmark with cost per successful task. |

## Default routing (BALANCED profile)

| Tier | Order |
|---|---|
| fast | local eco → local chat → (Ollama/workers) → Claude Haiku 5.5 |
| standard | local chat → local eco → (Ollama/workers) → Claude Sonnet 5.5 |
| deep | Claude Opus 5.5 → workers → local chat |

External entries are dropped in offline mode, for `private`/`sensitive` requests, when external providers are switched
off, when a provider is paused/backing off, or when a spend limit would be exceeded. `MODEL_CHAIN_<TIER>` overrides the
order (still subject to the same filters). Live chains: `GET /api/ai/status`.

## Evaluations

`POST /api/ai/evals/run` runs suites with fixed datasets (`backend/app/evals/datasets`):
planner intents, prompt-injection detection (F1), anti-generic originality gate, retrieval grounding (recall@3 +
abstention on unanswerable questions, isolated in-memory database) and, only when explicitly requested and a provider is
configured, LLM grounding. Last full run: all deterministic suites 1.0 (SQLite and PostgreSQL smoke).
The model benchmark (DAEMON CORE → Benchmarks) measures models, not code; results are in COST_INTELLIGENCE.md.

## Prompt injection

Retrieved or user-supplied content is wrapped by `security/untrusted.wrap` (XML-escaped envelope + guard text) and
scanned by `untrusted.detect`; flagged chunks are marked in the Archive. Content never changes instructions or
permissions. Small local models are more likely to *echo* envelope text than larger ones — another reason G-sus
verification steps and human review remain in place for consequential output.
