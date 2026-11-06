# Completion audit — finish what exists before building anything new

Owner's governing principle for this round: **finish and connect the existing application before adding features.**
Status words: COMPLETE AND VERIFIED · FUNCTIONAL BUT INCOMPLETE · FRONTEND ONLY · BACKEND ONLY · PLACEHOLDER · MOCKED ·
BROKEN · MISSING · BLOCKED BY EXTERNAL DEPENDENCY.

## 1. How the audit was done (measured, not guessed)

| Check | Method | Result |
|---|---|---|
| Dead buttons | Playwright crawl of all 30 signed-in pages and their 18 tabs; every `button`, `[role=button]`, `[role=tab]` inspected through React's props for an `onClick`/submit handler (the detector was proven by injecting a handler-less button) | **0** buttons without a handler; 29 disabled buttons, all waiting for input (empty question, nothing selected) |
| Dead links | every internal `a[href]` checked against the route table | **0** links to missing pages |
| Runtime errors | console errors, page errors, `/api` responses ≥ 400 while loading every page and tab | **0** |
| Placeholder text | visible text scanned for TODO, coming soon, lorem, not implemented, placeholder, mock, NaN, undefined, `[object Object]`, Invalid Date | **0** |
| Source markers | `TODO`, `FIXME`, `XXX`, `HACK`, mock / dummy / fake data in backend and frontend source | **0** |
| Backend ↔ frontend | 262 endpoints from the OpenAPI schema matched against every `/api/...` string in the frontend | **50** endpoints without a frontend reference; checked one by one (§2) |
| Connections | internal links per page | **26 of 30 pages link nowhere else** — agents, runs, approvals, models and documents are not connected |

So the surface is clean; the gaps are capabilities the UI cannot reach, modules that do not lead to each other, and
three overview pages that do not answer "what needs my attention?".

## 2. Findings

### 2.1 BACKEND ONLY — built and tested on the server, unreachable from the interface

| Capability | Endpoint(s) | Why it matters |
|---|---|---|
| Revoke / delegate an approval; see expiry, delegation, revocation, consumption | `POST /api/approvals/{id}/revoke`, `/delegate` | Approval lifecycle (control plane CP2) exists, the Approval Center shows only approve/reject; its text still says "only an admin can decide" although the approver role decides |
| Policy history, rollback, disable | `GET /api/policies/history`, `POST /api/policies/{key}/rollback`, `/disable` | Governed policy changes can be proposed but not undone or inspected |
| Delete a budget rule | `DELETE /api/budgets/{id}` | Budgets can be created, never removed |
| Knowledge Vault collections and per-document access | `GET/POST /api/vault/collections`, `PATCH /api/vault/documents/{id}/access` | Classification-aware access (CP4) cannot be managed in the Archive |
| Audit retention (governed, four eyes) | `POST /api/audit/prune` | Retention can only be requested through the API |
| Ledger entry | `POST /api/finance/ledger` | Finance and the Operating picture show "No ledger data"; a single entry could not be recorded anywhere, and the CSV/JSON ledger import (`/api/import/ledger`, reachable but hidden in Opportunity database → Import) was not mentioned on the Finance page — the static map missed it because the URL is built at runtime |
| Telemetry retention, cache purge, model unload | `POST /api/control/retention`, `/api/daemon/cache/purge`, `/api/control/unload/{key}` | Operator maintenance only through the API |

Intentionally API-only (no UI needed): `/api/ai/*` (internal AI API for programs), `/health`, `/ready`, `/api/version`,
`/api/events/stream` (used by the live feed), streaming variants.

### 2.1b BROKEN — a workflow that could not be completed

* **Governed changes could never be applied from the interface.** Proposing a policy rule, a budget, a grant, an egress
  change, a release gate or wider document access files an approval and says "repeat the change with that approval" —
  but no form can send an approval id, so once someone approved it, nothing in the interface could apply it.

### 2.2 MISSING — needed for the application to work as one system

1. **Connections between modules**: an approval does not lead to what it governs, a run does not lead to its agent,
   a failed task does not lead to its trace, a tournament model does not lead to its quality profile.
2. **One attention-first command centre**: `/` (commerce), `/hq` (departments) and `/control` (system) each show part
   of the picture; none lists what is waiting, failing or blocked across the organisation.
3. **Global search**: Ctrl+K finds pages only; agents, tasks, runs, approvals, documents, models, tournaments, products
   and experiments cannot be found from one place.
4. **Settings overview**: settings live in Settings, DAEMON CORE, Governance and Creative; nothing shows where each
   one is and what it is set to.

## 3. Plan (dependency order)

1. Approval lifecycle in the Approval Center (foundation for every governed action).
2. Governance: policy history / rollback / disable, budget delete, audit retention request.
3. Knowledge Vault collections and document access in the Archive.
4. Finance: ledger entry and import.
5. Deep links + cross-links between runs, agents, tasks, approvals, documents and models.
6. Global, permission-aware search in the Ctrl+K finder.
7. Command centre on `/`: attention list and system status from real data, adjustable widgets.
8. Settings overview.
9. Verification: backend tests, journey e2e tests, crawl again, screenshots on three device classes, completion matrix.

## 4. Results

### 4.1 What was finished (in dependency order)

| # | Work | Before | After | Verification |
|---|---|---|---|---|
| 1 | **Apply an approved governance change** | BROKEN: "repeat the change with that approval" — no form could | `POST /api/approvals/{id}/apply` repeats the stored request through the original route (every check runs again); "Apply once approved" where the change was proposed and in the Approval Center | `test_completion.py` (apply, re-check, approver may decide but not configure, tool calls refused); e2e propose → approve → apply |
| 2 | Approval lifecycle | approve / reject only | expiry, delegation (to listed approvers), revoke with reason, used, link to what it governs, `?id=` deep link | API + e2e delegate → revoke |
| 3 | Policies | propose only | history, rollback per version, disable (all governed) | e2e history |
| 4 | Budgets, audit retention | create only / API only | remove a budget, request pruning (both governed) | tsc, matrices |
| 5 | Knowledge Vault | API only | collections (create, inherited access) and per-document classification / collection / roles / people in the Archive | e2e collection |
| 6 | Finance | no way to record a ledger entry | record an entry; link to the CSV/JSON import (`/lab?import=ledger`) | e2e entry recorded |
| 7 | Connections | 27 of 30 pages linked nowhere; 5 cross-links on first view | deep links `/agents?agent=` `?task=`, `/approvals?id=`, `/creative#t-`, `/daemon#models` …; task → agent, trace, parent, children; run replay → agent, task, tournament, G-sus; AI call → run; approval → governing page; settings → each setting's home | 20 cross-links on first view (re-crawl), many more inside rows and details |
| 8 | **Global search** | pages only | Ctrl+K / More also finds agents, tasks, approvals, runs, tournaments, documents, products, experiments, research, models, audit records — each kind with its own list endpoint's permission; Vault read check for documents | `test_search_finds_across_modules_and_respects_permissions` (a viewer never sees a restricted title); e2e search → open |
| 9 | **Command center** | commerce figures only | "Needs attention" (sorted critical → your action → warning → info, each linked) + "System" (agents, tasks, approvals, spend, providers, models today) above the business figures, which can be hidden | `test_overview_lists_what_needs_attention…`; e2e attention → approvals |
| 10 | Settings | settings in four places, nothing showed where | "Where every setting lives": current value + the single page that changes it; honest rows for what has no setting | e2e map → DAEMON CORE Models |
| 11 | Reliability / accessibility | Ctrl+K could close itself right after a navigation (1 in 5); colour-only in-text links | finder state derived from the page it was opened on (20/20); in-text links underlined | repeat runs; axe matrix with data present |

### 4.2 Re-audit (same crawler, same database, after the work)

| Check | Before | After |
|---|---|---|
| Buttons without a handler | 0 | 0 |
| Links to missing pages | 0 | 0 |
| Console errors / failing API calls | 0 / 0 | 0 / 0 |
| Placeholder text | 0 | 1 — the deliberate "e-mail / push not implemented" on Settings |
| Cross-links visible on first load | 5 | 20 |
| Endpoints without a frontend reference (excluding API-only by design and runtime-built URLs) | 38 | 27 (§4.4) |

### 4.3 Completion matrix

| Area | Before | Work completed | Verification | Remaining issues | Status |
|---|---|---|---|---|---|
| Navigation | pages only; finder could close itself | record search, deep links, race fixed | e2e navigation + search, desktop and phone | three overview pages remain (`/` command center, `/hq` departments, `/control` system internals) — now different in purpose, not merged | IMPROVED AND VERIFIED |
| Agent Management | no link from a task to its trace | `?agent=` / `?task=`, task → agent, run, parent, children | tsc, e2e (search) | agent configuration has no model picker per agent (tiers are chosen by policy) | IMPROVED AND VERIFIED |
| Orchestration | runs were dead ends | run replay → origin; failed runs in Needs attention | API tests | no visual workflow designer (workflows are code) | PARTIALLY COMPLETE |
| Model Intelligence | — | models in search, DAEMON tabs addressable | e2e settings → models | per-agent model selection not exposed | IMPROVED AND VERIFIED |
| Creative Intelligence | no deep link | `#t-<id>`, tournaments in search, below-target results in Needs attention | API tests | quality gain not demonstrated on local models (CREATIVE_INTELLIGENCE.md §7) | IMPROVED AND VERIFIED |
| Knowledge Vault | access control API only | collections + document access in the Archive | e2e collection | relations and re-embedding still API only | IMPROVED AND VERIFIED |
| Tool Management | — | grants applied from approvals | API test (tools.grant path) | — | COMPLETE AND VERIFIED |
| Identity & Security | approvals: approve/reject only; apply impossible | full lifecycle, apply with re-checks, approvers list | `test_completion.py`, e2e | no SSO | COMPLETE AND VERIFIED |
| Observability | — | run ↔ agent/task/tournament/call links | tsc | no OpenTelemetry export | IMPROVED AND VERIFIED |
| Evaluation | — | gates applied from approvals | API path | — | IMPROVED AND VERIFIED |
| Resource Intelligence | — | spend near limit in Needs attention; budgets removable | API test | cache purge / telemetry retention / model unload API only | PARTIALLY COMPLETE |
| Audit System | retention API only | request retention (governed) | tsc, matrix | — | COMPLETE AND VERIFIED |
| Settings | scattered, no overview | settings map with live values | e2e | dashboard preference is per device (browser storage), not per account | IMPROVED AND VERIFIED |
| Desktop UX | — | command center, search, links | e2e desktop | — | IMPROVED AND VERIFIED |
| Mobile UX | — | same journeys on phone (finder via More) | e2e phone, responsive matrix | no physical device test | IMPROVED AND VERIFIED |
| Performance | — | search debounced, stale answers dropped; one shared `/api/auth/me` | performance matrix passes | search and attention not benchmarked at large data volumes | PARTIALLY COMPLETE |
| Accessibility | — | in-text links underlined, labelled controls | axe matrix (serious/critical = 0) with data present | manual screen-reader pass not done | IMPROVED AND VERIFIED |

### 4.4 Still backend only (prioritised)

1. Operator maintenance: telemetry retention (`/api/control/retention`), cache purge (`/api/daemon/cache/purge`), model unload (`/api/control/unload/{key}`) — next candidates for a Maintenance card on DAEMON CORE.
2. Archive relations and re-embedding (`/api/archive/relations`, `/api/archive/reembed`); Archivum chapter edit (`PATCH /api/archivum/chapters/{id}`).
3. Rocky Flare assets (versions, status), providers, personalization validation, originality check; HQ department detail.
4. Fine-tuning datasets (`/api/daemon/finetune/datasets`) — feasibility is shown; training needs a GPU and a training stack.
5. Agent-internal tools (`/api/tools/compliance`, `/business-models`, `/scoring-weights`, `/api/daemon/context/assemble`, `/api/daemon/tools/{name}/invoke`) — used by agents and programs; a UI is optional.

Static-match false positives (they are used, with URLs built at runtime): `/api/flare/campaigns`, `/api/flare/graphs/…`, `/api/archive/documents`, `/api/audit/export`, `/api/research/sources/{id}/promote`, `/api/daemon/library/{key}/import-file`.
