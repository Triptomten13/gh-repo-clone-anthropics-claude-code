# Decision records

Short records of decisions that shape the system. Newest first.

### D-012 · 2026-11-05 · llama.cpp in-process as the default local runtime
**Context:** the host has 4 vCPU, 16.9 GB RAM, no GPU; independence requires local generation. **Decision:**
llama-cpp-python (MIT, prebuilt CPU wheel) inside the API process; GGUF Q4/Q8 models ≤ 1.5B; Ollama and
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
