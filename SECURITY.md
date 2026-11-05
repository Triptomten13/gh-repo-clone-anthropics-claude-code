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

## Secrets

- All credentials come from environment variables (`.env`, never committed — see `.gitignore`).
- Connector credentials are read only inside the connector; they are never stored in the DB, returned by the API, or
  passed to LLM prompts. `/api/integrations` reports only *which* variables are missing.
- Use scoped credentials: read-only keys for research; Shopify custom app limited to `write_products`;
  Stripe restricted keys for ledger sync.

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
