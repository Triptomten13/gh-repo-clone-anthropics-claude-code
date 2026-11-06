# DAEMON CONTROL PLANE — governed multi-agent operation

How Demonkoncernen decides who may do what, with which data, on which model, through which tool — and how every
consequential operation can be reconstructed. Status words follow the honest scale: IMPLEMENTED AND VERIFIED ·
PARTIALLY IMPLEMENTED · DESIGNED BUT NOT IMPLEMENTED · NOT SUPPORTED · BLOCKED BY INFRASTRUCTURE.

## 0. Audit of the existing system (2026-11-06, before changes)

Git: clean working tree at `683e602` on `claude/ai-commerce-empire-txb0qj`.

| Capability | What already existed (file) | Gap found |
|---|---|---|
| 1 Orchestration | `agents/orchestrator.py`: task registry + routing by task type, delegation depth limit, circular-delegation and duplicate detection, per-task timeout + retries (non-retryable `Blocked`), crash recovery (requeue), kill switch; `gsus/engine.py`: plan → steps with dependencies → delegate → verify | no central policy decision; workflows are code (G-sus plans), not versioned definitions; no per-workflow execution policy |
| Approvals | `governance/core.py`: `request_approval` / `decide_approval`; `security/permissions.py`: 6 action levels, LEVEL ≥ 4 needs an approved `Approval` | no expiry, no revocation, no delegation, no self-approval guard, no approval categories, decided by any operator |
| 2 Knowledge | Archive: extraction (magic + size checks), chunking, local embeddings (nomic GGUF), hybrid BM25 + vector with RRF, in-memory index with transactional change tokens, citations, versions, evidence classes, deletion purging answer caches | documents are visible to **every** signed-in user; no classification, collections or ACL; no deletion verification |
| 3 Model routing | `daemon/policy.py` + `gateway.py`: profiles, offline mode (no external ever), `sensitivity` private/sensitive ⇒ local/LAN only, spend limits, circuit breakers, registry with verified pricing | 3 ad-hoc sensitivity words instead of classifications; routing explanation exists only in traces |
| 4 Tools | `daemon/tools.py`: 4 declared tools with input schemas, `ROLE_LEVEL` check, unknown-argument rejection, audit on invoke | gated by **user role only** — no agent identity, no per-agent/workflow grants, no per-operation permissions, no budgets, no invocation log |
| 5 Observability | `llm_calls` (every attempt, cost, latency), task rows, G-sus run steps, telemetry (routes, hosts, events) | no unified run/trace record linking policy decisions, retrievals, tools and approvals; no replay |
| 6 Evaluation | `evals/runner.py`: 6 suites (planner, routing, injection, originality, retrieval, grounding), held-out set; benchmarks | no release gates; nothing blocks activating a prompt/model that fails |
| 7 Identity | own auth (PBKDF2, HMAC tokens with revocation via `token_version`), roles admin/operator/viewer, lockout | no fine-grained permissions, no separation of duties, no SSO |
| 8 Deployment | offline mode, DAEMON profiles, Docker Compose, HTTPS profile, independence tests (network-namespace offline run) | no explicit outbound allow-list, no deployment profiles as configuration, no egress verification report |
| 9 Cost/resources | cost dashboard, daily/monthly USD limits, per-agent daily token budget, telemetry (CPU/RAM/disk/net), energy estimates | budgets only per agent-tokens and global USD; no per-workflow/user/tool limits; no efficiency score |
| 10 Audit | `audit_log` table written on state changes; `/api/audit` list | a normal mutable table: rows can be edited or deleted without trace; no export, no integrity check |
| UI | Control Center, Agents, Approvals, Audit & Lessons, DAEMON, Research pages | no policy, tool-grant, trace/replay, gate or integrity views |

Conventions kept: FastAPI + SQLAlchemy + Alembic (new migration, never edit applied ones), `gov.audit` on every
state change, `require_role`, the Demonkoncernen design tokens, honest empty states.

## Implementation plan (phases, each tested and committed)

1. **Audit chain + RBAC foundation** — hash-chained audit, verify, signed export; permission-based roles.
2. **Policy engine + approvals** — PDP/PEP with 5 approval categories, versioned rules, approval lifecycle.
3. **Tool Security Gateway** — deny-by-default grants, per-operation permissions, budgets, invocation log.
4. **Knowledge Vault ACL + classification routing** — permission-aware retrieval, classification-gated routing.
5. **Runs + replay, budgets, release gates, air-gap egress, unified UI, documentation and the final matrix.**
