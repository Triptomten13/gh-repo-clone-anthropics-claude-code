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

Results and the final completion matrix are in §4 (filled in as each step is verified).
