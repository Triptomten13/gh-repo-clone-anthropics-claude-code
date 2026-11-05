# DAEMON CORE — sovereign AI infrastructure

> G-SUS provides the identity. Demonkoncernen AB provides the infrastructure. External AI providers may be guests;
> they are not the foundation.

This document is the architecture, the audit, the plan and the honest state of Demonkoncernen AB's self-hosted AI
layer. Measured results are in [INDEPENDENCE_TESTS.md](INDEPENDENCE_TESTS.md); cost controls in
[COST_INTELLIGENCE.md](COST_INTELLIGENCE.md); installation in [INSTALL.md](INSTALL.md).

## 1. Audit — external AI dependencies before this work (Stage 1)

| Area | Before | Mandatory? |
|---|---|---|
| Text generation (agents, G-sus answers, creative work) | Anthropic API only; Ollama adapter existed but nothing ran locally | **Yes** — without a key every LLM task was *blocked* |
| Embeddings (Archive search) | Local feature-hashed vectors (lexical) or Ollama if configured | No, but only lexical quality |
| Orchestration, agents, approvals, memory, Archive storage | In-process / own database | No |
| Model metadata & pricing | Static registry in code | No |
| Fonts / UI assets | Bundled (no CDN at runtime) | No |
| Install time | PyPI, npm, (now) Hugging Face for weights | Install-time only |

Conclusion: the platform was **not independent** — the only path to generated text was an external API.

## 2. Hardware decision (actual machine)

`GET /api/daemon/hardware` reads the OS; nothing is assumed. The development host has 4 vCPU (x86-64, AVX2/AVX-512),
16.9 GB RAM, no GPU. That rules out large models, vLLM and any training. Chosen architecture:

* **Runtime:** llama.cpp in-process through `llama-cpp-python` (MIT), prebuilt CPU wheel — no daemon to operate, no
  network listener, GGUF quantised models memory-mapped from disk. Ollama and any OpenAI-compatible server (llama.cpp
  server, vLLM, LM Studio) are supported as *workers* for machines that have them.
* **Models** (all Apache-2.0 or MIT, licence read from each repository's own model-card metadata, sha256 from the Hub's
  LFS record, re-verified live before download):

| Slot | Model | Size | Measured here |
|---|---|---|---|
| chat | Qwen2.5 1.5B Instruct Q4_K_M | 1.1 GB | ~0.8 s for a one-word classification, ~6–10 s for a short chat answer; benchmark 11/17, deep reasoning 2/7 |
| eco | Qwen2.5 0.5B Instruct Q4_K_M | 0.5 GB | ~0.4 s per short task; benchmark 11/17, deep reasoning 1/7 |
| **deep** | **Qwen3 4B Q4_K_M (reasoning, thinks first)** | 2.5 GB | ~4–5 tokens/s; 90 s–4 min per multi-step problem; benchmark **17/17, deep reasoning 7/7** |
| embedding | nomic-embed-text v1.5 Q8_0 | 0.15 GB | 768-d; related text cos ≈ 0.68–0.90, unrelated ≈ 0.28–0.32 |
| replacement (Test C) | SmolLM2 360M Instruct Q8_0 | 0.4 GB | different model family, English only |

Kubernetes, GPU schedulers and a model gateway service were deliberately **not** introduced: one process on one host
is what the hardware and workload justify. Workers scale out when another machine exists.

## 3. Architecture

```
            ┌────────────── internal AI API (authenticated) ───────────────┐
 apps/UI →  │ /api/ai/chat · generate · embeddings · classify · reason ·   │  ← agents & G-sus use the same router
            │ agents/execute · health · status                             │
            └──────────────┬───────────────────────────────────────────────┘
                           │ gateway (response cache, tracing, energy estimate)
                           ▼
          policy.plan(tier, sensitivity, profile)  ── offline mode / privacy / external switch / quota / spend limits
                           ▼
       LLMRouter: ordered candidates, circuit breakers, refusals never re-routed, rate-limit backoff
          │                 │                         │                          │
   local (llama.cpp)   ollama (local/LAN)   worker:<name> (OpenAI-compatible)   anthropic (external guest)
          │
   model library (DB rows + GGUF files in MODELS_DIR) · hardware fit · activation history (rollback)
```

* **G-SUS identity layer** (`daemon/prompts.py`, prompt `gsus.identity`, versioned): the same identity, facts about
  itself and non-negotiable rules whichever model serves the request. Verified in Test C: the replacement model answers
  through the same `/api/ai/chat` as G-SUS.
* **Deep reasoning** — the `deep` slot holds a reasoning model (Qwen3 4B; 8B catalogued for stronger hardware). The
  deep tier tries it before the chat model. It thinks in a first phase up to `local.thinking_tokens` (default 1,536,
  set on the status tab); if the budget runs out it is made to conclude and the answer is flagged
  `reasoning_complete: false`. Working notes are returned separately (labelled unverified), never mixed into the answer.
  Outside the deep slot and for JSON-schema calls the model does not think. Deep-tier agent tasks get a 900 s timeout.
  UI: G-sus Chamber → Deep reasoning; API: `POST /api/ai/reason` (`samples: 3` = self-consistency with majority vote;
  `verify: true` adds a second model's answer). A single sample can be confidently wrong — measured, see §7.
* **Execution profiles** — ECO, BALANCED, DEEP, SPECIALIST, OFFLINE, EMERGENCY (`daemon/policy.py`). BALANCED: local
  for fast/standard tiers, strongest available for deep. OFFLINE: local/LAN only. EMERGENCY: smallest local model,
  256-token outputs, nothing external.
* **Offline mode** (`PATCH /api/daemon/settings {"offline_mode": true}`): every external candidate is excluded from
  every chain (recorded as `excluded_offline`), model downloads and credential tests are refused, the header shows
  `OFFLINE`. Test B ran with a fake external key present and recorded zero external attempts.
* **Privacy routing:** `sensitivity: "private" | "sensitive"` on any internal API call excludes external providers
  (and LAN workers for `sensitive`).
* **Model library** (`daemon/library.py`, `daemon/catalog.py`): install (download from huggingface.co only, licence +
  checksum re-checked, redirects outside the Hub refused), offline import (file must match the verified sha256),
  activate per slot (chat / eco / embedding), rollback, remove (refused while active). A model that does not fit the
  hardware is never marked runnable.
* **Embeddings:** the Archive prefers the active local GGUF embedding model, then Ollama, then the lexical hash
  embedder. Relevance floor for GGUF vectors: cosine 0.5 (measured: unrelated text scores 0.28–0.32).
* **Prompt & context engine:** versioned prompts with activation = rollback, variables validated, token estimates
  (labelled as estimates), budgeted context assembly that drops duplicates and low-relevance background but never
  required instructions or evidence — if those alone exceed the budget the caller is told, not given a truncated context.
* **Tools:** declared with input schema, permission level and side-effect class (`GET /api/daemon/tools`). There is no
  shell or code-execution tool; `code.execute` is declared **blocked** until an isolated sandbox exists.
* **Workers:** `POST /api/daemon/workers` registers an OpenAI-compatible endpoint; its locality (loopback / LAN /
  external) is derived from the URL and enforced by the same policy (an internet-hosted "worker" counts as external).
* **Recovery:** on start, tasks left `running` by a crash are requeued (or failed if out of attempts) and queued work
  resumes; settings, active models, memory and documents live in the database/disk.
* **Fine-tuning lab:** `GET /api/daemon/finetune/feasibility` — on this host foundation training, full fine-tuning and
  LoRA are all reported **not feasible** (no GPU, no training libraries). Datasets can be registered; anything with
  private data and no explicit consent is `blocked_no_consent`.

## 4. Internal AI API

| Endpoint | Role | Notes |
|---|---|---|
| `POST /api/ai/chat` | operator | messages → G-SUS reply; `tier`, `profile`, `sensitivity`, `workflow`, `project` |
| `POST /api/ai/generate` | operator | raw prompt or a versioned `prompt_name` + variables; optional `json_schema`; `cache: true` |
| `POST /api/ai/embeddings` | operator | `kind: document|query`; always local |
| `POST /api/ai/classify` | operator | fast tier; rejects labels outside the given set (502) instead of inventing one |
| `POST /api/ai/reason` | operator | deep tier (local reasoning model); returns answer, working notes, `reasoning_complete`; `samples` 1–5 = self-consistency (majority vote, agreement reported); `verify: true` asks a different model independently |
| `POST /api/ai/agents/execute` | operator | runs an agent task through the orchestrator (budgets, approvals, kill switch apply) |
| `GET /api/ai/health`, `/api/ai/status` | any user | providers, breakers, quota; profile, chains, active models, independence verdict |

Administration lives under `/api/daemon/*` (settings, library, self-test, prompts, tools, providers, credentials,
costs, benchmarks, proposals, workers, fine-tuning). Settings, models, credentials and provider records are admin-only;
every change is audited.

## 5. Staged plan and acceptance criteria

| Stage | Scope | Acceptance criterion | State |
|---|---|---|---|
| 1 Audit | inventory external AI dependencies | table above | ✅ |
| 2 Local runtime | hardware manager, llama.cpp, verified model library | a local model answers through the internal API | ✅ measured |
| 3 Sovereign routing | profiles, offline mode, privacy routing, workers | OFFLINE chain contains no external provider; no silent fallback | ✅ Test B |
| 4 Internal AI API + identity | chat/generate/embeddings/classify/reason/agents/health/status | same calls work after model swap | ✅ Test C |
| 5 Local memory & embeddings | GGUF embeddings, reindex | semantic search without external API | ✅ Test D |
| 5b Deep reasoning | reasoning model in a `deep` slot, thinking budget, flags | multi-step problems solved locally, offline | ✅ 7/7 on the benchmark; Tests A & B |
| 6 Cost intelligence | registry, credentials, limits, cache, benchmarks, proposals | no paid call beyond limits; cost per success measured | ✅ (see COST_INTELLIGENCE.md) |
| 7 Recovery & backup | requeue on restart, backup/restore scripts | crash + restart recovers config, models, memory, tasks | ✅ Test F; backup/restore round-trip verified |
| 8 Security | auth on every local service, no extra listeners | anonymous 401, role 403, only the API listens | ✅ Test G |
| 9 Fine-tuning | dataset registry, consent, feasibility | honest feasibility report | ✅ report; training **not feasible** here |
| 10 Multimodal | speech, vision | — | ⏳ not started (no local STT/TTS/vision model installed) |
| 11 Scale-out | more workers, GPU host | a registered GPU worker serves the deep tier | ⏳ needs hardware |

## 6. Deliverables map

1 architecture → §3 · 2 dependency audit → §1 · 3 hardware manager → `daemon/hardware.py` · 4 model registry/library →
`daemon/catalog.py`, `daemon/library.py`, DAEMON CORE → Models · 5 local runtime → `daemon/runtime.py` · 6 profiles →
`daemon/policy.py` · 7 internal API → §4 · 8 orchestration → existing orchestrator, `/api/ai/agents/execute` ·
9 memory/embeddings → Archive + `runtime.LocalGGUFEmbedder` · 10 prompt & context engine → `daemon/prompts.py` ·
11 tools → `daemon/tools.py` · 12 offline mode + self-test → settings, `POST /api/daemon/selftest` · 13 workers →
`daemon/workers.py` · 14 fine-tuning lab → `daemon/finetune.py` · 15 monitoring → DAEMON CORE page (status, costs,
benchmarks) · 16 installation → [INSTALL.md](INSTALL.md) · 17 backup → [BACKUP_RECOVERY.md](BACKUP_RECOVERY.md) ·
18 tests → `backend/tests/test_daemon.py` (24 tests), `scripts/independence_test.py` · 19 roadmap → §5 and
[ROADMAP.md](ROADMAP.md).

## 7. Limits, stated plainly

* **Quality.** Local models are far weaker than frontier models. The small chat/eco models solve only 1–2 of 7
  multi-step problems, which is why the deep tier goes to the reasoning model (7/7 in its benchmark run). It samples,
  so single runs can be wrong: it once answered the mislabelled-boxes puzzle wrongly after its thinking budget ran out
  (flagged), and in the Independence Test environment it answered a margin problem with −40 instead of 80 — twice, since
  a fresh process starts from the same seed. With self-consistency (3 samples) the same problem came out 80 (2/2 agreeing
  samples, early stop). Use `samples` and human review for anything that matters. When asked "what is Demonkoncernen AB?" offline, the 1.5B model once invented that the company
  "develops games"; the identity prompt now states the only facts it may claim. Critical decisions should use
  `/api/ai/reason` with `verify: true` plus human review. Swedish-language quality is not a requirement (owner decision,
  D-014) and is no longer benchmarked.
* **Deep reasoning is slow on this CPU:** ~1 minute on average per problem, up to ~4–5 minutes when the model uses its
  whole thinking budget. Qwen3 8B is stronger but about half as fast here; it is catalogued for machines with more cores
  or a GPU.
* **Speed.** CPU inference: seconds per short answer, about a minute for a long G-sus synthesis.
  `DAEMON_LOCAL_MAX_TOKENS` (default 1024) caps local outputs.
* **Energy cost** is an estimate (configured watts × inference time × tariff), not a meter reading.
* **Install-time dependencies** remain: PyPI/npm packages and model weights must be obtained once (or imported from
  a verified offline copy). Runtime does not need them.
* **Independence verdict** (`/api/ai/status`) is computed, not declared: it turns false as soon as no local chat model
  is active.
