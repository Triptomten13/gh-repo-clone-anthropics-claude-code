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

Unknown actions are treated as LEVEL 5 (`security/permissions.py`). Only users with the `admin` role can decide
approvals, approve compliance, change agent permissions/budgets/status, and use the kill switch.
Every one of these changes is written to `audit_log`.

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

## Reporting

Report vulnerabilities privately to the repository owner. Do not open public issues for security problems.
