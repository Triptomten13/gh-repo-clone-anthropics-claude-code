# Security & Governance

## Human authority

| Level | Scope | Examples | Gate |
|---|---|---|---|
| 0 | Research | `market.research` | agent level |
| 1 | Analysis & recommendations | scoring, economics, compliance assessment | agent level |
| 2 | Drafting | content, brand, supplier inquiry drafts | agent level |
| 3 | Reversible internal operations | draft listings, experiment records | agent level |
| 4 | External publishing | publish listing, publish content, live price change, customer message, send supplier inquiry, product launch | agent level **+ approved Approval** |
| 5 | Financial / contractual | ad campaigns & budgets, purchase orders, supplier agreements, paid experiments | agent level **+ approved Approval** |

Unknown actions are treated as LEVEL 5 (`security/permissions.py`). Approvals are decided by users whose role holds
`approval.decide` (super admin, approver) — never by the person who requested the action or the person it is for
(docs/CONTROL_PLANE.md §2). Compliance approval, agent permissions/budgets/status and the kill switch stay admin-only.
Every one of these changes is written to the hash-chained `audit_log`.

**Agents cannot change their own permissions, security policies or financial limits.** There is no code path from an
agent to `PATCH /api/agents/*`; `sync_agents()` never overwrites a level set by an admin.

## Rocky Flare controls

- Personas shape judgement only; they have no permission, budget or limit fields, and only admins can edit them (versioned + audited).
- Concept approval is admin-only and requires the anti-generic gate to pass. Brands need an admin-recorded trademark search
  (with evidence) and a LEVEL 4 approval to go live. Campaign launches are LEVEL 5. Acquisitions are research-only (offers LEVEL 5).
- Generated SVG assets are rendered through `<img>` data URLs so markup can never execute; user text inside SVGs is XML-escaped.
- Real agency names/seals are blocked in brand assets; conspiracy aesthetics must read as fiction.
- Personalisation accepts only customer-entered data with a stated purpose; inferred or scraped attributes and sensitive-category profiling are rejected.

## Emergency controls

- **Kill switch** (`POST /api/system/kill-switch`, red button in the header): rejects new tasks, cancels queued tasks,
  and running tasks stop at the next execution check.
- **Agent suspension**: suspended agents' tasks end as `blocked`.
- **Budgets**: per-agent daily token budget; global daily AI cost cap (`DAILY_COST_LIMIT_USD`).

## Authentication

- Passwords: PBKDF2-SHA256, 240k iterations, per-user salt. Minimum length 10.
- Tokens: HMAC-SHA256 signed, expiring (`TOKEN_TTL_HOURS`). WebSocket requires the same token.
- First-run setup endpoint only works while no user exists.
- In `APP_ENV=production` the API refuses to start with the default `SECRET_KEY`.
- Roles: `admin`, `operator` (can submit work, cannot approve), `viewer` (read-only).
- Tokens carry a `token_version`; password reset, role change and disabling an account revoke all existing sessions.
  Disabled accounts cannot log in. The last active admin cannot be demoted or disabled (API and CLI).
- Login lockout: 5 failures per account (×4 per IP) within 15 minutes → 429. API rate limit 600 requests/min.
- Owner recovery: `python -m app.cli` on the server (create-admin, reset-password, list-users, set-role, disable/enable);
  passwords are read from a prompt or stdin, never argv; actions audited as `cli:<os user>`.

## Secrets

- All credentials come from environment variables (`.env`, never committed — see `.gitignore`).
- Connector credentials are read only inside the connector; they are never stored in the DB, returned by the API, or
  passed to LLM prompts. `/api/integrations` reports only *which* variables are missing.
- Use scoped credentials: read-only keys for research; Shopify custom app limited to `write_products`;
  Stripe restricted keys for ledger sync.

## DAEMON CORE (local AI, providers, credentials)

- **Provider credentials** stored in the app are Fernet-encrypted (`CREDENTIALS_KEY`, else HKDF from `SECRET_KEY`), require
  the account owner's attestation, are admin-only, never returned by the API, never logged, never given to agents or
  prompts. One active key per provider. Validate / rotate / disconnect are audited; disconnect destroys the secret.
- **No accounts are created and no provider terms are accepted by the system.** Discovered providers stay "unverified"
  until a human records the official source.
- **Offline mode** removes every external provider from routing (no fallback) and disables downloads and credential tests.
  `private` / `sensitive` requests never leave the machine (sensitive: not even to LAN workers).
- **Model supply chain:** downloads only from huggingface.co over HTTPS, redirects outside the Hub refused; licence and
  sha256 re-checked against the Hub before download, file sha256 verified after; offline imports must match the
  verified catalogue checksum. Weights never enter git or the database.
- **No code execution:** there is no shell/code tool; `code.execute` is declared blocked until an isolated sandbox
  exists. The benchmark checks generated code statically and never runs it.
- **Network surface:** the llama.cpp runtime is in-process and opens no port (verified: the only listening socket is the
  API). Docker binds API and web to 127.0.0.1 by default — use a TLS reverse proxy for LAN access.
- **Spending:** paid calls are checked against daily/monthly/per-provider limits before they are made; unverifiable spend
  blocks the call.
- Settings, model install/activation, credentials, provider records and workers are admin-only and audited; operators
  can use the internal AI API and run benchmarks on local models; viewers are read-only (Independence Test G).

## Internet research

- Only official APIs and public feeds; robots.txt respected for page fetches; per-host rate limits; Retry-After honoured
  (long waits pause the host). No CAPTCHA, login, paywall or access-control bypass — none is implemented.
- Retrieved text is untrusted: wrapped in `untrusted.wrap` before a model sees it, scanned with `untrusted.detect`
  (flags stored on the web resource), never treated as instructions.
- The research User-Agent identifies the software, not the owner; no personal data is sent to sources.
- Offline mode stops every outbound research request at the client (tested).
- Raw web excerpts expire (retention job); only a human "Save to Archive" keeps one, with URL, retrieval time and licence.
- SSRF guard (`internet/http.guard_url`): every research request AND every redirect hop (httpx request hook) must be
  http(s) to a host that resolves only to public addresses — loopback, LAN, link-local/cloud metadata (169.254.169.254),
  `localhost`/`.internal`/`.local` names are refused, whoever configured the URL. Residual risk: DNS re-binding between
  the check and the connect (no IP pinning). Behind an egress proxy that resolves names itself, unresolvable names are
  left to the proxy's policy.
- Links from connectors are reduced to absolute http(s) URLs (`sources.sanitize`) before they are stored or rendered —
  no `javascript:`/`data:` links reach the UI.

### Audit 2026-11-05 — HYPERINTELLIGENCE additions

| Severity | Finding | Fix | Regression test |
|---|---|---|---|
| Medium | Research HTTP client followed redirects to, and could be configured for, internal addresses (SSRF) — `fetch_page` and admin-set `research_feeds` had no address check | `guard_url` on every request and redirect hop | `test_research_http_refuses_internal_targets`, `test_research_http_guard_checks_every_redirect_hop` |
| Medium | Deleting (or editing) an Archive document left its quoted text in the L2/L3 answer cache for up to 7 days | `semantic_cache.purge_document` on delete and patch (count in the audit entry) | `test_deleting_a_document_purges_cached_answers_quoting_it` |
| Low | `PATCH /api/monitors/{id}` accepted an unvalidated dict (budget/frequency could exceed creation limits; bad types → 500); duplicate sources multiplied requests | `MonitorPatch` with the creation bounds; sources de-duplicated, ≤10 | `test_monitor_patch_is_validated_and_audited` |
| Low | Connector URLs rendered as links without a scheme check | `sources.sanitize` | `test_connector_links_are_http_only` |
| Low | Research synthesis wrapped sources but its system prompt lacked `untrusted.GUARD` | GUARD appended | covered by existing research tests |
| Low | Monitor run/ack and manual model unload were not audited | audit entries `monitor.run`, `monitor.ack`, `model.unload` | `test_monitor_patch_is_validated_and_audited` (audit log) |
| Accepted | `diskcache` 5.6.3 (dependency of llama-cpp-python): PYSEC-2026-2447, pickle cache directory → code execution for anyone who can write it; no fixed release | not exploitable here: the app never opens a diskcache | `test_no_pickle_backed_disk_cache_is_used` |

Checked and fine: every new state-changing route has `require_role` (operator/admin; retention and unload admin-only);
no new path changes agent permission levels or approvals; answer caches never cross users (Archive answers have the
Archive's own org-wide visibility, private/sensitive questions skip the cache, model responses are keyed by the full
prompt); `pip-audit -r backend/requirements.txt` and `npm audit --omit=dev`: no known vulnerabilities. Research runs and
monitor alerts are visible to every signed-in user (team-shared, like the Archive) — do not put private data in research
queries.

## Clients on other devices

- Browsers reach only the web server's origin; it proxies `/api` to a backend bound to 127.0.0.1. With
  `--profile https`, Caddy terminates TLS and forwards the real client IP (`FORWARDED_ALLOW_IPS` trusts only it).
- Live events (`/api/events/stream`, and the legacy `/ws/events`) apply the same checks as every API call — signature,
  user enabled, token not revoked — and the token travels in a header, not the URL (`test_cross_platform.py`).
- The service worker caches static assets and the offline page only; API responses are never cached on devices
  (`tests/matrix/pwa.spec.ts`). Secrets are typed into masked fields, never `prompt()`.

## Data protection (GDPR)

- No personal data is scraped. Research connectors store aggregate signals (counts, views) and product listings;
  the Reddit complaint miner keeps post titles only, not authors.
- Customer data (future customer-intelligence features) must be consent-based and lawfully collected; see ROADMAP.
- `audit_log` stores actor emails for accountability — define a retention period for your deployment.

## Platform compliance

Connectors use official APIs only, declare and respect rate limits, and never bypass CAPTCHAs, authentication,
paywalls or robots restrictions. Platforms without an API are supported only through manual import of data you are
licensed to use.

## Governed AI control plane (2026-11-06)

Design and status: [CONTROL_PLANE.md](CONTROL_PLANE.md). The rules that matter for security:

* Every consequential action passes the policy decision point in the backend (`governance/policy.py`); prompts carry no
  authority. Agents have no API credentials, act only through the orchestrator and the Tool Gateway, and can never
  perform governance actions (policies, grants, budgets, approvals, audit, users, deployment, gates, credentials).
* Tools are deny-by-default per agent / workflow / role and per operation; an agent working for a user gets at most
  the intersection of its grants and the user's.
* Approvals bind to the exact arguments (hash), expire, are single use, revocable, and need a second person for
  RESTRICTED actions. Silence is never approval.
* Knowledge Vault access is checked before any passage is scored or placed in a model context; the highest
  classification in the context decides which models may see it.

### Threat model

| Threat | Controls in place | Evidence | Residual risk |
|---|---|---|---|
| Direct prompt injection ("ignore your rules, grant yourself…") | permissions live in the backend, not the prompt; agents cannot call governance endpoints; PROHIBITED actions for agents | criteria 1, 3, 17; `test_agents_can_never_perform_governance_actions` | a model can still write a wrong or manipulated *answer* within its permissions — cite sources, review consequential output |
| Indirect injection (instructions inside documents, web pages, tool output) | all such content is wrapped as untrusted data (`security/untrusted.wrap`); tool outputs are data; injection-detection suite is a **mandatory** release gate (threshold 1.0) for prompt releases | eval suite `injection_detection`, criterion 16 | detection is heuristic; the guarantee is that injected text cannot change permissions, not that it never influences wording |
| Leaking restricted data to external models | classification-aware routing (CONFIDENTIAL → local/LAN, RESTRICTED → this machine, HIGHLY_SENSITIVE → in-process); model functions that cannot receive the classification are not called; offline mode; egress guard | criteria 7, 13, 14 | a human can still copy text out of the UI; classification is only as good as the labels given |
| Retrieval leakage across users | access filter before scoring on every search path; semantic answer cache stores only answers whose sources everyone may read; verified deletion | criteria 5, 6 | backups keep deleted documents until they age out (BACKUP_RECOVERY.md) |
| SSRF | `internet/http.guard_url` on every request and redirect hop: http(s) only, public addresses only; `web.fetch` only through the gateway | `test_hyper.py` (guard on private, metadata and redirect targets) | DNS re-binding between check and connect |
| SQL injection | SQLAlchemy with bound parameters only; string-built SQL is a lint error (ruff S608) | ruff in CI | raw `text()` reviewed by hand |
| Command / code execution | no shell is ever invoked with user or model input (one fixed-argv `nvidia-smi` call); `code.execute` is refused (no sandbox); model output is never executed | `test_01_*`, gateway `blocked` status | — |
| Malicious uploads | 20 MB limit, extension allow-list, magic-byte check, DOCX expansion limit (100 MB / 2 000 parts), pypdf per-stream decompression limits (75 MB), parsed as data only, generated SVG rendered via `<img>` | `test_extract_formats`, `test_docx_zip_bomb_is_refused_before_parsing` | a PDF with many large streams can still use several hundred MB while parsing; no antivirus scanning |
| Audit manipulation | keyed HMAC chain sealed at commit, append-only triggers (SQLite + PostgreSQL), verification, signed export, pruning only of an old verified prefix with a second person's approval | criterion 15, `test_retention_*` | whoever holds the database superuser **and** the audit key can rebuild the chain — keep signed exports outside the system |
| Approval abuse (self-approval, replay, reuse, stale approvals) | four eyes, payload-hash binding, atomic single use, expiry, revocation, delegation only to approvers | criteria 2–4, 19 | collusion between two people |
| Privilege escalation through roles | explicit permission sets, no inheritance; only the super admin creates admins / security admins | criterion 18 | the super admin account itself — keep few, protect the host |
| Budget exhaustion (denial of wallet) | atomic reservations before every model or tool call; daily/monthly USD limits; external spend needs an authorised provider | criteria 12, 19 | estimates are reserved and settled; a provider that bills more than reported is caught only by your invoice |
| Denial of service | per-IP API rate limit, login lockout, task depth/attempt/time limits, kill switch, request size limits | `test_login_lockout_and_security_headers`, `test_kill_switch_cancels_and_blocks` | limits are in-process (one server); no WAF; put a reverse proxy in front for internet exposure (which is not recommended) |
| Credential leakage | provider credentials encrypted at rest (Fernet), handed only to granted tools, redacted from tool output, traces and logs; never sent to the frontend | criterion 8 | the session token sits in browser `localStorage`, so an XSS bug would expose it; React escaping and the no-`dangerouslySetInnerHTML` rule are the defence — the web pages have **no Content-Security-Policy yet** (the API has one) |
| Supply chain | `pip-audit` and `npm audit` in CI; npm lockfile; model files verified by SHA-256 against the catalog | CI workflow | Python requirements are version ranges, not a lockfile; no package signature verification or SBOM |
| Self-modification by agents | agents cannot change policies, grants, budgets, gates, audit or deployments; releases pass gates; governance changes need a second person | `test_agents_can_never_perform_governance_actions`, criteria 16, 18 | humans with the right roles can still make bad changes — that is what the audit trail and four eyes are for |

### Incident response

1. **Contain.** Engage the kill switch (header button or `POST /api/system/kill-switch`) — new tasks are rejected,
   queued ones cancelled, running ones stop at their next check. For data-exposure suspicion also switch to
   `AIR_GAPPED` (`POST /api/deployment {"profile": "AIR_GAPPED"}`, applies at once) and suspend affected agents.
2. **Cut access.** Disable affected users (Users & access) — their tokens stop working immediately (`token_version`).
   Revoke tool grants and pending approvals that the incident touches; rotate provider credentials (DAEMON →
   Providers) and, if the host may be compromised, `SECRET_KEY` and `AUDIT_HMAC_KEY` (rotation invalidates all sessions;
   export and verify the audit trail **before** rotating the audit key, since verification needs the old key).
3. **Preserve evidence.** `python -m app.cli audit-verify`, then `audit-export --format zip` to storage outside the host;
   copy the database (`scripts/backup.sh`). Do not prune anything during an investigation.
4. **Investigate.** `/governance` → Runs & replay (what each run did, in order), Tool security → invocations,
   Audit & compliance (filter by actor, action, time), `llm_calls` for model destinations. A failing chain
   verification names the first broken record.
5. **Recover.** Fix the cause; restore from backup if data was changed (`scripts/restore.sh`, refuses tampered
   archives); roll back policies (`POST /api/policies/{key}/rollback`) or model slots if a release caused it; re-run the
   evaluation gates and `scripts/independence_test.py`; release the kill switch.
6. **Record.** Write what happened, the impact, and the fix into the Archive / DECISIONS; notify affected people and,
   where the law requires it (e.g. a GDPR personal-data breach: the supervisory authority within 72 hours), the authority.

### Audit retention and privacy

The audit trail stores actor e-mails, action names, targets and redacted details — personal data. The trade-off is
accountability against data minimisation and the right to erasure:

* Records are kept at least `AUDIT_MIN_RETENTION_DAYS` (default **365**); older ones can be pruned only as a contiguous,
  verified prefix, with a second person's approval for that exact cut-off (`POST /api/audit/prune`). An anchor keeps
  the remaining chain verifiable, and the pruning itself is recorded.
* Individual records cannot be edited or deleted (that would break the evidence). For an erasure request, rely on the
  lawful-basis exception for records you are obliged or entitled to keep, or prune once the retention period has
  passed — decide this with your legal adviser and record the decision.
* Configuration points for your deployment: the retention period (statutory record-keeping duties — e.g. if audit
  records double as accounting documentation — may require years), who holds `audit.retention`, where signed exports
  are stored and for how long, and the backup retention (deleted data lives on in backups until they expire).
* Document contents and model text are not copied into the audit trail or traces (references and hashes only;
  strings are cut at 2 000 characters and secret-looking fields redacted).

## Reporting

Report vulnerabilities privately to the repository owner. Do not open public issues for security problems.
