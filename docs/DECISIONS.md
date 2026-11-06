# Decision records

Short records of decisions that shape the system. Newest first.

### D-021 · 2026-11-06 · One web app for every device: same-origin API, PWA, no wrapper
Phones could not use the app at all (no navigation; API at a build-time `localhost`). Fix in the web app itself: the
browser talks only to its own origin and the web server proxies to the backend; live events moved from WebSocket
(502 through the proxy) to an HTTP event stream; installable as a PWA. No Electron/Tauri (nothing needs native APIs;
a wrapper adds an update channel and attack surface) and no separate native app (one codebase, one API contract).
Revisit for iOS background push or OS-level integration.

### D-020 · 2026-11-05 · In-process Archive index, not a vector database (yet)
Measured: the per-query scan cost 0.45 s at 2 000 chunks and 5.9 s at 20 000. An in-memory index (BM25 postings + a
float32 matrix, numpy) brings that to 3.8 / 22 ms with identical rankings and no new service to run, secure or back up.
Freshness comes from a change token written in the same transaction as every chunk change, so it is correct across
processes. Revisit (pgvector / ANN) when the Archive outgrows memory — roughly beyond a few hundred thousand chunks.

### D-019 · 2026-11-05 · Conservative semantic answer reuse
Two similar questions are not the same question. L3 reuse requires a semantic embedder, cosine ≥ 0.95, the same scope and
task category, identical numbers and the same negation, and only verified (cited) answers are stored. Time-sensitive
questions never use it.

### D-018 · 2026-11-05 · Internet research through official APIs; the user is not identified to third parties
Research uses documented APIs (Wikipedia, arXiv, Crossref, GitHub, HN Algolia, PyPI, OSV, NVD, Hugging Face, RSS) within
their rate limits; general web search only through a keyed API. Search-result pages are not scraped. The User-Agent names
the software, not the owner. Long Retry-After ⇒ the host is paused, not hammered.

### D-017 · 2026-11-05 · Memory-aware model residency instead of "max 2 loaded"
Measured: cold weight reads 14 MB/s vs 6.5 GB/s from page cache; the fixed limit caused 5 reloads in a 7-call sequence.
Models now stay resident while RAM allows (reserve per mode), LRU-idle eviction only when room is needed, idle unload,
automatic LOW_MEMORY/EMERGENCY under pressure. Result: 3 loads, repeat calls 3–9× faster; RSS higher by design.

### D-016 · 2026-11-05 · Rules-first task routing
The orchestrator classifies requests with rules (no model call) and prefers deterministic solvers, caches and the Archive
before any model; research for current facts; deep model for multi-step reasoning; G-sus only for multi-agent work.
Evaluated: 30/30 on the tuned set, 12/12 on a held-out set.

### D-015 · 2026-11-05 · Self-consistency for deep answers that matter
**Context:** in the Independence Test environment a single sample of Qwen3 4B answered a margin problem with −40
instead of 80 (it counted the marketplace's cut as income) — reproducibly, because each fresh process starts from the
same sampling seed. **Decision:** `POST /api/ai/reason` takes `samples` (1–5): independent samples, majority vote on the
final answer, early stop once a majority is certain, agreement reported, "no majority" flagged as unreliable. Default 1
(it multiplies the time); recommended for anything consequential, alongside human review.

### D-014 · 2026-11-05 · Swedish is not a requirement; deep reasoning is
The owner decided Swedish-language quality is not needed and deep reasoning is. Swedish tasks were removed from the
benchmark; seven multi-step reasoning problems were added; a local reasoning model serves the deep tier.

### D-013 · 2026-11-05 · Local deep reasoning: Qwen3 4B in a `deep` slot, two-phase thinking with a hard budget
**Context:** 0.5B/1.5B models fail most multi-step problems; the host has no GPU (4B ≈ 4–5 tokens/s, 8B about half).
**Decision:** a separate `deep` slot (deep tier: local deep → local chat; external Opus first only in BALANCED/DEEP when
authorised) served by Qwen3 4B in thinking mode. Thinking runs as phase 1 up to `local.thinking_tokens` (default 1,536);
if the budget is hit the model is told to conclude and phase 2 produces the answer — the thinking-budget technique
described in the Qwen3 technical report. The answer is flagged `reasoning_complete: false` in that case. Working notes are returned separately and
labelled unverified; they are never mixed into the answer. Outside the deep slot Qwen3's `/no_think` switch keeps it
fast; JSON-schema calls never think. Deep-tier agent tasks get `DEEP_TASK_TIMEOUT_S` (900 s).
**Consequences:** real multi-step reasoning offline, at minutes per answer on this CPU; Qwen3 8B is catalogued for
better hardware.

### D-012 · 2026-11-05 · llama.cpp in-process as the default local runtime
**Context:** the host has 4 vCPU, 16.9 GB RAM, no GPU; independence requires local generation. **Decision:**
llama-cpp-python (MIT, prebuilt CPU wheel) inside the API process; GGUF Q4/Q8 models ≤ 4B; Ollama and
OpenAI-compatible servers supported as workers. **Consequences:** no extra daemon or port, simple deployment; one
process does inference (serialised per model, max two models loaded); scale-out by registering workers. vLLM/Kubernetes
rejected — no GPU, single host.

### D-011 · 2026-11-05 · Offline mode excludes, it does not merely deprioritise
External candidates are removed from every chain (recorded as `excluded_offline`) so no failure path can reach them.
Verified with a fake external key present (Independence Test B).

### D-010 · 2026-11-05 · Licence from the source's own metadata; commercial use only for permissive licences
Open weights ≠ unrestricted. `commercial_use = permitted` only for Apache-2.0/MIT/BSD; anything else is
`review_required`. Licence and sha256 are re-checked against the Hub right before download.

### D-009 · 2026-11-05 · One active credential per provider, owner attestation, encrypted at rest
Prevents key pools that could be used to evade rate limits; makes the human owner's authorisation explicit.

### D-008 · 2026-11-05 · Spend checks before the call, fail closed
A paid call that would exceed a limit — or whose spend cannot be verified — is not made. No silent charges.

### D-007 · 2026-11-05 · Token versioning for sessions
Stateless HMAC tokens carry the user's `token_version`; password reset, role change and disable bump it, revoking every
existing session without a session table.

### D-006 · 2026-11-05 · Admin CLI over a hidden web reset
Owner recovery uses shell access to the server (`python -m app.cli`), which already implies control of the machine,
instead of an unauthenticated reset endpoint.

### D-005 · Master evolution · Tiers, not models, in agent code
Agents request `fast/standard/deep`; routing decides. Enables local-first routing and model replacement without touching
agents.

### D-004 · Master evolution · Refusals are terminal
A provider refusal is reported, never re-routed to a less careful provider.

### D-003 · Master evolution · Untrusted-content envelope
All retrieved/external text reaches models XML-escaped inside `<untrusted_source>` with guard text; instructions inside
it carry no authority.

### D-002 · Master evolution · Evidentiary classes are separate fields, never merged
Facts, sources, interpretations, theories, hypotheses, speculation and fiction are labelled at ingestion and in answers.

### D-001 · Phase 1 · Human approval for LEVEL 4–5 actions
Spending, publishing, external messages, purchases, permission changes and irreversible actions require a human
`Approval`; agents cannot grant themselves permissions.
