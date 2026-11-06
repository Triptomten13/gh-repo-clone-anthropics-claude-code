# Public launch — Public Demo and Private Control Center

Status words: **LIVE AND VERIFIED** · **RUNNING LOCALLY** · **CONFIGURATION REQUIRED** · **DEMO ONLY** · **NOT IMPLEMENTED** ·
**BLOCKED**. Nothing below is called live unless it was deployed and checked; no URL is invented.

## 1. Two environments, one codebase

| | **Public Demo** | **Private Control Center** |
|---|---|---|
| Who | anyone with the link — no account | you and the people you create accounts for |
| Runs | the all-in-one image (`Dockerfile`) with `DEMO_MODE=1` | `docker-compose.yml` (PostgreSQL + API + web [+ Caddy HTTPS]) or `make prod` |
| Data | its own temporary database: synthetic sample products, a sample Knowledge Vault built from the platform's own documentation, one synthetic RESTRICTED memo | your real database, documents, agents, approvals, audit trail |
| AI | no models, offline mode forced — no external call, no spending, whatever is saved | local models (llama.cpp) and, if you configure them, external providers |
| Access | temporary visitor sessions (`demo` role): read sample data, run the approved sample workflows | full roles (admin, security admin, approver, auditor, operator …) |
| Lifetime | full reset + reseed every `DEMO_RESET_HOURS` (6) and on restart | persistent, backed up (`docs/BACKUP_RECOVERY.md`) |

They share **code and the release pipeline**, never a database, credentials, models or user accounts. The demo cannot
reach the private instance; visitors can never be given its keys. That is the separation recommended for showing
Demonkoncernen to others without handing over the server room.

```
 visitor ──https──▶ [ public demo container ]                    you ──https/VPN──▶ [ private Control Center ]
                     web :$PORT (public)                                              web :3000 ── Caddy TLS
                       └─ /api /health /ready ─▶ API 127.0.0.1:8000                     └─ API (loopback) ─ PostgreSQL
                     temporary SQLite · DEMO_MODE=1 · offline                         models · archive · backups
```

## 2. Audit of the project before launch (2026-11-06)

| Area | Found | Launch-relevant finding |
|---|---|---|
| Frontend | Next.js 16 / React 19 / Tailwind 4, `output: standalone`, PWA; same-origin proxy for `/api`, `/ws`, `/health` | `/ready` was not proxied → a load balancer on the public origin would get 404 (found by the demo suite; fixed) |
| Backend | FastAPI, 6 routers + public router, in-process orchestrator (threads), SSE live events | long-running process with background threads: **not serverless-compatible** |
| Database | SQLite (dev) / PostgreSQL 16, Alembic 0001–0010 | migrations verified on both; `alembic upgrade head` runs at container start |
| AI | llama.cpp local models (CPU), Anthropic adapter (no key in this environment) | demo host gets no models: model-backed features are shown as unavailable, never faked |
| Agents | 30+ agents, G-sus head orchestrator, Tool Gateway, policies, approvals | all run in-process; no external orchestration service |
| Auth | own HMAC tokens with revocation, 10 roles, first-run setup | first-run setup on a public server would let anyone claim admin → **disabled in demo mode** |
| Config | `.env.example`, `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, Caddy | **bug**: `FORWARDED_ALLOW_IPS` was nested under `depends_on` (invalid compose) → fixed; **bug**: `backend/.dockerignore` did not exclude `data/` → 9.1 GB of model weights and uploaded Archive files would have been copied into the API image → fixed |
| Tests | 239 backend tests, 77 browser tests (4 devices, responsive, axe, PWA, CSP, performance), PostgreSQL smoke, Independence Tests A–G | added: public demo suite (10 scenarios) + PASS/FAIL report |

Feature status on a demo server is reported by the server itself (`GET /api/status` → `features`) and shown on the
landing page; nothing is listed as available that the server cannot do.

## 3. Hosting choice

| Option | Fit | Why |
|---|---|---|
| Vercel / Netlify / Cloudflare Pages | frontend only | serverless functions cannot host a long-running Python process with background threads, SQLite/PostgreSQL sessions, SSE and local models |
| **Render** (chosen for the public demo) | ✔ | runs the Docker image as one web service, automatic HTTPS + stable `*.onrender.com` URL, health check on `/ready`, Blueprint in the repo (`render.yaml`), free plan possible |
| Fly.io / Railway | ✔ (equivalent) | same image works unchanged (`PORT` is honoured); not configured to avoid redundant platforms |
| Self-hosted Docker + Caddy (chosen for the private Control Center) | ✔ | local models need RAM/CPU you control; keep it on your network or behind a VPN — `docker compose --profile https up -d` |

Local models on the demo: a free/starter container (0.5 GB RAM, shared CPU) cannot run them usefully (measured on 4
vCPU here: 6–10 s per short answer with a 1.5 B model, 1–5 min for deep reasoning). The demo therefore runs without
models and says so.

## 4. Demo mode (`DEMO_MODE=1`) — what a visitor can and cannot do

Can: open the landing page and status page; start a temporary session (`POST /api/demo/session`, 120 min); browse
agents, policies, approvals, runs, audit records, the sample Knowledge Vault (PUBLIC/INTERNAL only) and every page;
run the approved sample workflows in the **Demo Center** — product evaluation by several agents, risk review with
contradictions, a launch that stops at a human approval checkpoint, retrieval with citations, a deterministic
answer, a routing dry run, the offline evaluation suites, and a tool call that is refused.

Cannot (enforced by the API, tested): approve anything, use tools, upload or change documents, change settings,
policies, grants, budgets or users, engage the emergency stop, start G-sus runs other than the catalog ones, see other
visitors' runs, read the RESTRICTED sample memo, reach any external service, claim the administrator account.

Limits: `DEMO_ACTIONS_PER_SESSION` (30) per session; `DEMO_SESSIONS_PER_CLIENT_HOUR` (10) per client address — best
effort, an address behind proxies can be shared or forged — and `DEMO_SESSIONS_PER_HOUR` (300) in total, which holds
regardless; the API's per-address request limit. Cleanup: the whole demo database is dropped and reseeded every
`DEMO_RESET_HOURS` (postponed while a task runs) and on every restart of a container with temporary storage.

Labels in the interface: **LIVE DATA** (read from this server), **DEMO DATA** (synthetic records), **RULE-BASED · NO AI
MODEL** (computed by rules, not a language model), **SIMULATED OUTPUT** (never shown as if it were real),
**CONNECTED SERVICE**, **UNAVAILABLE SERVICE**. A permission refusal reads "Not available in the public demo (requires …)".

## 5. Environments

| Environment | How to run | Database | Credentials / models | Data |
|---|---|---|---|---|
| development | `make dev` | `backend/rocky.db` (SQLite) | yours, optional | yours |
| test | `make test` (pytest: temp SQLite per test; Playwright: throw-away stack on 8100/3100) | temporary | none (fakes) | generated |
| staging | the private compose stack on a second host / project name, `APP_ENV=staging` | its own PostgreSQL | separate keys | copy or synthetic — never production records without authorisation |
| production (private Control Center) | `docker compose up -d` (+ `--profile https`) | PostgreSQL volume, daily backups | `.env` on the host only | real |
| public demo | `make demo` (local) · `make demo-docker` · Render Blueprint | temporary SQLite inside the container | none — offline forced | synthetic + platform docs |

## 6. One-command startup

```bash
git clone <repository> && cd <repository>
cp .env.example .env            # set SECRET_KEY (and POSTGRES_PASSWORD) before anything public
make install && make dev        # development: http://localhost:3000 (first visit creates the admin)
make demo                       # the public demo locally: http://localhost:3300 (no Docker needed)
docker compose up --build       # private stack in containers: http://localhost:3000
make demo-docker                # the public demo as a container: http://localhost:3300
make test && make test-demo     # every automated test, then the public demo suite + PASS/FAIL report
make health WEB=http://localhost:3000
```

Missing Python/Node dependencies, busy ports, a failed build or a process that dies are reported with the last log
lines and a non-zero exit (`scripts/dev.sh`, `deploy/start.sh`); a container without `SECRET_KEY` refuses to start
unless it is a demo on temporary storage (then it generates one for its lifetime).

## 7. Health and status (public, no internals)

| Endpoint | Purpose |
|---|---|
| `GET /health` | liveness (process answers) |
| `GET /ready` | readiness: database answers and the schema is at the newest migration → 200, else 503 (platform health check) |
| `GET /api/version` | version, build commit, environment |
| `GET /api/status` | core components (backend, database, agents) vs optional ones (local models, external AI, research) with states — `not_configured`/`disabled` are not failures; feature availability; no hosts, paths, keys, user data or error text (tested) |
| `/status` | the public status page built on it |

Errors: unexpected exceptions return a bare `500 Internal Server Error` (tested — no stack trace, path or message).
Logs: the API and web server log to stdout (the platform's log view); structured run traces live in `/governance#runs`.

## 8. Persistence

Persistent on the private instance: PostgreSQL (all records, audit chain), the archive volume (uploaded files), the
models volume, backups (`./backups`, 14 days). Temporary by design: the public demo's whole database, visitor sessions,
in-memory caches and the retrieval index (rebuilt from the database), Playwright/pytest databases.

## 9. Security review for public access

| Check | Result |
|---|---|
| Secrets in the repository / example files | `.env` is git-ignored; `.env.example` holds placeholders only |
| Secrets in the frontend bundle | only `NEXT_PUBLIC_API_URL` / `NEXT_PUBLIC_COMPANY_NAME` exist; build output scanned for key patterns — see §11 |
| Local state in images | `.dockerignore` (root + backend) excludes databases, model weights, uploaded files, `.env`, backups |
| Authentication / authorisation | server-side on every endpoint (roles + permissions); demo role least-privilege; setup disabled in demo |
| Admin routes | API admin endpoints need admin/security roles; the API's own docs (`/docs`, `/openapi.json`) are not proxied to the public origin |
| CORS | the browser uses one origin (the web server proxies the API); `CORS_ORIGINS` only matters for a separate API host |
| Sessions | bearer token (no cookies → no CSRF); revocable; demo tokens expire after `DEMO_SESSION_TTL_MIN`; token kept in `localStorage` — XSS would expose it: CSP + React escaping (residual risk in SECURITY.md) |
| HTTPS | provided by the platform (Render) or Caddy (`--profile https`); the API itself never listens publicly |
| Rate limiting / abuse | per-address API limit, login lockout, demo session limits + global cap, per-session action budget, offline mode (no paid calls) |
| Inputs / uploads | Pydantic validation; uploads disabled for visitors; size, type, magic-byte and zip-bomb checks for everyone else |
| Tool execution | deny-by-default gateway; visitors have no tool permission; model output is never executed |
| Dependencies | `pip-audit` and `npm audit` in CI |
| Error leakage | bare 500s (tested) |

## 10. Deployment pipeline

`.github/workflows/ci.yml` (every push): backend tests + ruff + PostgreSQL smoke + `pip-audit`; type check + build +
`npm audit`; browser suites; **`demo-image`**: validates the compose file, builds the all-in-one image, starts it with
`DEMO_MODE=1`, waits for `/ready` and runs the public demo suite against the container.
`.github/workflows/deploy-demo.yml` (manual only, type `DEPLOY`): tests → deploy hook (protected `public-demo`
environment — add required reviewers) → waits until `/api/version` reports the new commit and `/ready` is 200 → runs
the public demo suite against the live URL. Rollback: Render → Events → Rollback to the previous deploy, or re-run the
workflow on the previous commit. The private Control Center is never deployed automatically.

## 11. Readiness matrix (2026-11-06)

See the final table in this section (kept current with each verification run).
