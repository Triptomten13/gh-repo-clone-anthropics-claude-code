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

## 1. Architecture — one control plane inside the existing application

No new services: the control plane is a set of backend modules every path goes through (FastAPI + SQLAlchemy +
Alembic, SQLite or PostgreSQL), with one administrative page (`/governance`) beside the existing Control Center.

```
 request / agent task ─▶ Identity & roles (security/rbac.py: permissions, separation of duties)
                      ─▶ Orchestration core (agents/orchestrator.py) ── runs + events (governance/observability.py)
                           │  every consequential step:
                           ├─▶ Policy decision + enforcement (governance/policy.py) ── approvals (governance/core.py)
                           ├─▶ Tool Security Gateway (governance/tool_gateway.py) ── grants, budgets (usage.py), credentials
                           ├─▶ Knowledge Vault (knowledge/vault.py + search.py) ── access filter BEFORE scoring, provenance
                           ├─▶ Model Router (ai/router.py + daemon/policy.py) ── classification / offline / privacy / spend
                           └─▶ Budgets (governance/budgets.py) ── reserved before the call, settled after
   everything ─▶ Audit chain (governance/audit_chain.py: sealed at commit, verifiable, exportable)
   releases   ─▶ Evaluation gates (governance/gates.py)        outbound ─▶ Egress guard (governance/egress.py)
```

| Component | Module | Tables (migration) | API |
|---|---|---|---|
| Audit & provenance | `governance/audit_chain.py` | `audit_log` + `seq`, `prev_hash`, `hash`; triggers (0006) | `GET /api/audit/records`, `/audit/verify`, `/audit/export?fmt=json\|csv\|zip`, `POST /audit/prune` (governed, four eyes); CLI `audit-verify`, `audit-export`, `audit-verify-export` |
| Identity & access | `security/rbac.py` | `users.role` | `GET /api/rbac/roles`, `/auth/me` (permissions), user management (super admin) |
| Policy (PDP/PEP) | `governance/policy.py` | `policy_rules` (0007) | `GET /api/policies`, `/policies/history`, `POST /policies`, `/policies/{key}/rollback`, `/policies/{key}/disable` |
| Approvals | `governance/core.py` | `approvals` + category, on_behalf_of, payload_hash, expires/revoked/consumed, delegated_to (0007) | `GET /api/approvals`, `POST /approvals/{id}/decide`, `/revoke`, `/delegate` |
| Tool gateway | `governance/tool_gateway.py`, `usage.py` | `tool_grants`, `tool_invocations`, `usage_counters` (0007) | `GET /api/tools`, `/tools/grants`, `/tools/invocations`, `POST /tools/grants`, `DELETE /tools/grants/{id}`, `POST /tools/{tool}/invoke` |
| Knowledge Vault | `knowledge/vault.py`, `search.py` | `documents` + classification, collection, access; `collections` (0008) | `PATCH /api/vault/documents/{id}/access`, `GET/POST /vault/collections`, Archive endpoints |
| Observability | `governance/observability.py` | `runs`, `run_events` (0009) | `GET /api/runs`, `/runs/{id}/replay` |
| Budgets | `governance/budgets.py`, `usage.py` | `budget_rules`, `usage_counters` (0007) | `GET/POST /api/budgets`, `DELETE /budgets/{id}` |
| Evaluation gates | `governance/gates.py` | `release_gates`, `gate_runs` (0009) | `GET/POST /api/gates`, `POST /gates/check`; enforced on prompt and model activation |
| Deployment / egress | `governance/egress.py` | `system_state["deployment"]` | `GET/POST /api/deployment`, `GET /deployment/egress/verify` |

Error format: `403 {"detail": "requires permission: …"}` · governed change `202 {"status": "pending_approval", "approval_id",
"category", "reasons"}` · gateway denial `{"status": denied|pending_approval|budget_exhausted|not_configured|invalid|error,
"detail", "approval_id", "decision", "invocation_id"}` · failed release gate `409 {"error": "release gate failed", "blocking", "gate_run"}`.

## 2. Policies, approvals and agent permissions

* **Categories:** 1 AUTONOMOUS · 2 SUPERVISED (allowed, recorded) · 3 APPROVAL_REQUIRED · 4 RESTRICTED (four eyes: not the
  requester, not the person the work is for) · 5 PROHIBITED.
* **Mandatory floors** come from the action permission levels (`security/permissions.py`: level ≤ 1 autonomous, 2–3
  supervised, 4 approval, 5 restricted) and built-ins (tool DELETE / external EXECUTE need approval, ADMINISTER and all
  governance changes are restricted, unknown actions are restricted). Configurable rules can raise a category; a rule
  that would lower a floor is ignored at decision time and refused at creation (422).
* **Agents** can never perform governance actions (policy, grants, budgets, approvals, audit, permissions, users,
  security, deploy, gates, credentials) — PROHIBITED whatever a rule says. Agents have no API tokens; they act inside
  the orchestrator, and through the Tool Gateway only.
* **Approvals** are bound to the action and to a hash of the exact arguments, expire (`APPROVAL_TTL_HOURS`, 72 h), are
  single use (atomic), revocable and delegable to another approver. Pending never turns into approved by waiting.
* **Changing governance is itself governed:** policy rules, tool grants, budgets, release gates, widening document
  access, loosening deployment egress and pruning audit records are RESTRICTED — the first request files an approval; the change applies
  when the same request is repeated with an approval decided by someone else. Tightening (revoking a grant,
  narrowing access, entering AIR_GAPPED) applies at once.
* **Roles** (`/api/rbac/roles`): admin (super admin), security_admin, system_admin, workflow_designer,
  agent_developer, operator, approver, auditor, user, viewer — explicit permission sets, no implicit inheritance. Only
  the super admin creates admins or security admins; approvers cannot change policy; builders cannot approve;
  auditors change nothing.
* **Tool grants:** deny by default. An agent call needs a grant for (tool, operation) to the agent or to its workflow,
  and when the agent works for a user, that user's role must hold a grant too — the agent gets the intersection.
  Default role grants reproduce the previous human access and are visible and revocable.

## 3. Model routing by data classification

| Classification of the data involved | May be processed by |
|---|---|
| PUBLIC, INTERNAL | any permitted provider (offline mode, privacy flag and spend limits still apply) |
| CONFIDENTIAL | local models or self-hosted LAN workers |
| RESTRICTED | this machine's models only |
| HIGHLY_SENSITIVE | in-process local models only |

The retrieved context decides: grounded answering and G-sus chat compute the highest classification among the
retrieved passages and pass it to the router; a model function that cannot receive it is not called (extractive
answer instead). Fallback follows the same plan — a failing local model never falls back to an excluded destination.
The registry (`daemon/catalog.py`, `registry.py`) records licence, deployment location, hardware needs, verified
prices and limits; routing decisions (including what was excluded and why) are in the run events and `llm_calls`.

## 4. Deployment profiles and air-gapped operation

Profiles: LOCAL_DEVELOPMENT, SELF_HOSTED, PRIVATE_NETWORK, CUSTOMER_VPC, ON_PREMISE, AIR_GAPPED (`/governance#deployment`).
In offline mode and AIR_GAPPED a process-wide guard refuses every outbound TCP connection except loopback, private
networks (10/8, 172.16/12, 192.168/16, 100.64/10, link-local, ULA — unless disabled), the database host and the
allow-list; AIR_GAPPED also refuses the configured HTTP proxy and forces offline mode on (no external AI provider, no
research, no external embeddings — never a silent fall back). `/api/deployment/egress/verify` runs a self-test and shows
every refused attempt.

Air-gap setup: 1) install with dependencies from an offline mirror or prebuilt image; 2) import models with
`python -m app.cli` / DAEMON → Models → import file (SHA-256 verified against the catalog); 3) `POST /api/deployment
{"profile": "AIR_GAPPED"}`; 4) run the egress self-test and `python scripts/independence_test.py` (Test B runs the app
in a network namespace with loopback only — OS-level proof). What keeps working offline is listed in the deployment tab.

## 5. Implementation matrix (2026-11-06)

| # | Capability | Existing before | Changes made | Backend enforced | Tests | Status · remaining limitations |
|---|---|---|---|---|---|---|
| 1 | Governed multi-agent orchestration (DAEMON ORCHESTRATION CORE) | task routing, depth/loop/dedupe limits, timeouts, retries, recovery, kill switch, G-sus planner | central PDP/PEP for every consequential action, 5 approval categories, approval lifecycle, governed governance changes, escalation on exhausted retries, policy versions + rollback | yes | 1–4, 11, 18, 20 | **PARTIALLY IMPLEMENTED** — no declarative versioned workflow definitions, conditional branching or parallel execution engine (workflows are code: G-sus plans + task dependencies; the orchestrator drains one task at a time); rollback exists for policies and model slots, not for arbitrary actions |
| 2 | Private RAG (DAEMON KNOWLEDGE VAULT) | extraction, chunking, local embeddings, hybrid BM25+vector, in-memory index, citations, versions | classification, collections with inherited access, per-document readers, access checked before scoring on every path, verified deletion (chunks, embeddings, caches, index token), widening governed, provenance on every hit | yes | 5, 6 | **IMPLEMENTED AND VERIFIED** for the above · no reranker beyond RRF fusion, no multi-tenancy (one deployment per organisation), no cryptographic erasure (backups keep deleted documents until they age out) |
| 3 | Policy-based model routing (DAEMON INTELLIGENT MODEL ROUTER) | profiles, offline, privacy flag, spend limits, breakers, registry with verified prices | classification-aware routing from the retrieved context, HIGHLY_SENSITIVE in-process only, fail-closed model functions | yes | 7, 13 | **IMPLEMENTED AND VERIFIED** for privacy/classification/offline/fallback · vision and audio models: **NOT SUPPORTED** (none installed); capability routing is by tier, not per-task capability scoring |
| 4 | Tool access control (DAEMON TOOL SECURITY GATEWAY) | 4 read tools, role-level check | deny-by-default grants per agent/workflow/role/environment and operation, user-bounded agents, scoped credentials, output redaction, atomic budgets, invocation log + audit, SSRF guard, blocked code execution | yes | 1, 2, 8, 9, 12, 17, 19 | **IMPLEMENTED AND VERIFIED** · credentials are stored secrets with scopes (not short-lived tokens); no sandbox, so code execution stays blocked |
| 5 | Observability & run artifacts (DAEMON OBSERVABILITY CENTER) | llm_calls, task rows, G-sus steps, telemetry | runs + ordered events (policy, model attempts with exclusions, retrieval refs, tools, approvals, retries, escalation, output), replay API and UI | yes | 10, 11 | **PARTIALLY IMPLEMENTED** — tasks and Ask requests are traced; G-sus runs keep their own step records (not yet unified into runs); no OpenTelemetry exporter (the event schema maps onto spans; not wired) |
| 6 | Evaluation & release gates (DAEMON EVALUATION LAB) | 6 offline suites, held-out set, model benchmarks | release gates with thresholds (mandatory/advisory) enforced on prompt and model activation, gate history, governed gate changes | yes | 16 | **PARTIALLY IMPLEMENTED** — suites measure the platform's guards and retrieval, not free-text prompt quality; no dataset management UI, rubric or human-review scoring |
| 7 | Identity, RBAC, SSO (DAEMON IDENTITY & ACCESS) | own auth, 3 roles, token revocation, lockout | 10 roles with explicit permissions, separation of duties, permission-checked endpoints, agents bounded by their user | yes | 17, 18 | **PARTIALLY IMPLEMENTED** — SSO (OIDC/SAML): **DESIGNED BUT NOT IMPLEMENTED** (no identity provider in this environment); agents have identities and grants but no per-agent owner field or delegated tokens |
| 8 | Deployment flexibility & air-gap (DAEMON DEPLOYMENT MANAGER) | offline mode, profiles for compute, Docker Compose, HTTPS profile | 6 deployment profiles, process-wide egress guard, AIR_GAPPED mode, egress self-test, governed loosening | yes (this process) | 14 | **IMPLEMENTED AND VERIFIED** in-process · other processes need OS/network isolation; container images were never built here (**BLOCKED BY INFRASTRUCTURE**: no Docker daemon); profiles other than AIR_GAPPED share one mechanism |
| 9 | Cost, token, RAM, energy governance (DAEMON RESOURCE & COST INTELLIGENCE) | cost dashboard, USD limits, agent token budgets, telemetry, energy estimates | atomic budgets for tool calls, model calls, tokens and USD per user/agent/workflow/global, per day/month; IES with components | yes | 12, 19 | **PARTIALLY IMPLEMENTED** — RAM/VRAM/CPU/energy measured system-wide, not attributed per run; no per-run step or concurrency budget beyond the orchestrator's depth/attempt limits |
| 10 | Exportable audit trail (DAEMON AUDIT & PROVENANCE) | mutable `audit_log` table | keyed hash chain sealed at commit, append-only triggers (SQLite + PostgreSQL), verification, signed ZIP / JSON / CSV export with filters, retention with anchors (minimum age `AUDIT_MIN_RETENTION_DAYS`, default 365, and a second person's approval per cut-off) | yes | 15 | **IMPLEMENTED AND VERIFIED** · no PDF report and no trusted (RFC 3161) timestamps; whoever holds both the database and the audit key can rewrite history — keep exported signed manifests outside the system |
| — | Unified interface | Control Center, Approvals, Archive, DAEMON | `/governance`: policies, tool security, runs & replay, gates, audit & compliance, deployment & egress, budgets, roles | n/a | e2e on desktop, iPad, iPhone, Android | **IMPLEMENTED AND VERIFIED** (Chromium emulation) |

### Acceptance criteria → tests (`backend/tests/test_control_plane.py`)

| # | Criterion | Test |
|---|---|---|
| 1 | no tool without a grant | `test_01_agent_without_a_grant_cannot_use_any_tool`, `test_01_grants_are_per_operation` |
| 2 | no approval-required action without approval | `test_02_approval_required_action_waits_for_a_valid_single_use_approval_bound_to_its_arguments` |
| 3 | no self-approval | `test_03_nobody_approves_their_own_request`, `test_agents_can_never_perform_governance_actions` |
| 4 | expired approvals authorise nothing | `test_04_expired_or_revoked_approvals_authorise_nothing` |
| 5 | no retrieval outside permissions | `test_05_*` (4 tests: roles/levels, agents/system, widening, inheritance) |
| 6 | deleted documents gone from retrieval | `test_06_deleted_documents_never_come_back_from_retrieval` |
| 7 | restricted data never to unapproved external models | `test_07_13_restricted_context_never_reaches_an_external_model_not_even_as_fallback`, `test_07_highly_sensitive_stays_in_process` |
| 8 | credentials scoped and never exposed | `test_08_credentials_are_scoped_to_grants_and_never_leave_the_gateway`, `test_08_a_tool_that_echoes_a_secret_is_redacted` |
| 9 | every tool invocation audited | `test_09_every_tool_request_leaves_an_audit_event` |
| 10 | every workflow execution traced | `test_10_every_workflow_execution_produces_a_reconstructable_trace` |
| 11 | retry and escalation policy | `test_11_failed_steps_follow_the_retry_policy_and_escalate` |
| 12 | budgets enforced at runtime | `test_12_19_tool_budgets_hold_under_concurrency`, `test_12_model_budgets_stop_calls_before_they_run_and_are_not_bypassed` |
| 13 | only authorised fallback | `test_07_13_…`, `test_external_disabled_switch_still_excludes_external_models` |
| 14 | air-gap blocks outbound traffic | `test_14_offline_and_air_gapped_modes_block_unapproved_outbound_connections`, `test_14_only_real_private_networks_count_as_private` |
| 15 | audit tampering detected | `test_15_*` (changed, deleted, truncated, forged) + triggers + concurrency + export |
| 16 | gates block failing releases | `test_16_release_gates_block_a_failing_prompt_release` |
| 17 | agents bounded by the user | `test_17_an_agent_never_exceeds_the_user_it_works_for`, `test_05_agents_and_the_system_read_no_more_than_their_user` |
| 18 | sensitive changes need the right permissions | `test_18_roles_grant_exactly_their_permissions`, `test_18_policy_changes_need_permission_and_a_second_person` |
| 19 | concurrency does not bypass budgets/approvals | `test_12_19_…`, `test_19_one_approval_cannot_be_used_twice_concurrently` (+ PostgreSQL check: 12 callers → 3, 5 uses → 1) |
| 20 | rollback and recovery | `test_20_policy_rollback_restores_a_previous_version`, Independence Test F (crash recovery), migrations down/up |

## 6. Self-improvement without self-modification

The Performance Engineering Agent and the optimiser may analyse, measure and file proposals; they run as agents and
therefore cannot change policies, grants, budgets, gates, audit records or deployments (PROHIBITED for agents,
tested). Releases of prompts and models pass the evaluation gates; every governance change needs a second person.
Not implemented: agents generating patches or release candidates, and automatic rollback of application deploys on
failed health checks (model-slot rollback exists: `POST /api/daemon/library/rollback`).

## 7. Production readiness (honest)

Ready to run as a governed single-organisation deployment on one host or a private network, with SQLite (one process)
or PostgreSQL. Before calling it enterprise-ready: SSO with your identity provider, a declarative workflow engine if
non-developers must design workflows, OpenTelemetry export into your monitoring, per-run resource attribution, a
physical-device and screen-reader pass, container builds in CI, and an external review of the threat model
(docs/SECURITY.md).
