# Installation, deployment and admin access

Nothing is hosted for you: G-SUS & Demonkoncernen AB runs wherever you run it. These steps were run on Linux with
Python 3.13 and Node 22.

## 1. Local install (no Docker)

```bash
# backend
cd backend
pip install -r requirements-dev.txt
pip install -r requirements-local-ai.txt     # optional but needed for local models (llama.cpp, prebuilt CPU wheel)
cp ../.env.example ../.env                   # set SECRET_KEY for anything beyond a laptop
alembic upgrade head
uvicorn app.main:app --port 8000             # binds 127.0.0.1 by default

# frontend (second shell)
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run build && npx next start -p 3000
```

## 2. Becoming admin

Open **http://localhost:3000/login**.

* **Brand-new database:** the login page offers *Create admin*. The first account created becomes **admin**; after that
  the setup endpoint is closed for good.
* **From the server shell (works any time, also when locked out):**

  ```bash
  cd backend
  python -m app.cli create-admin --email you@example.com      # prompts for the password twice
  python -m app.cli list-users
  python -m app.cli reset-password --email you@example.com    # signs out all existing sessions of that user
  python -m app.cli set-role --email someone@example.com --role viewer
  python -m app.cli disable --email someone@example.com       # / enable
  ```

  The CLI uses the same `DATABASE_URL` as the server, never takes passwords on the command line, refuses to remove the
  last active admin, and every change is audited as `cli:<os-user>`.
* **In the app:** *Systems & Integrations → Users & access* (admins) to add users, change roles, disable accounts or
  reset passwords; *Your password* for your own. Changing a role, disabling or resetting signs that user out everywhere.
* Locked out after failed logins? The lock lifts after `LOGIN_WINDOW_S` (default 15 min) or a server restart.

Roles: **admin** — everything, including approvals, settings, models, credentials and users; **operator** — run
agents, G-sus, the internal AI API, uploads; **viewer** — read only.

## 3. Local models (DAEMON CORE)

In the app: **DAEMON CORE → Models → Install** for each model you want (downloads come only from huggingface.co; the
licence and sha256 are re-checked against the Hub before the download and the file is verified after), then
**Use as chat / eco / embedding**. Recommended on a CPU-only 16 GB machine: Qwen2.5 1.5B (chat), Qwen2.5 0.5B (eco),
nomic-embed-text v1.5 (embedding). After activating an embedding model, re-embed the Archive
(`POST /api/archive/reembed`, admin).

Air-gapped machines: copy the `.gguf` files over and `POST /api/daemon/library/<key>/import-file {"path": "..."}` —
accepted only if the file's sha256 matches the verified catalogue.

Then turn on **Offline mode** on the DAEMON CORE status tab if nothing should leave the machine, and run the self-test.
Verify independence end to end with `python scripts/independence_test.py`.

## 4. Optional external providers

Anthropic: set `ANTHROPIC_API_KEY` in `.env`, or (admin) DAEMON CORE → Providers & keys → store a credential after
accepting the owner attestation. Paid calls are bounded by the daily/monthly limits on the Costs tab and never happen
in offline mode or for requests marked private.

## 5. Docker (single host)

```bash
cp .env.example .env              # set SECRET_KEY and POSTGRES_PASSWORD
docker compose up --build         # LOCAL_AI=0 docker compose build  → image without llama.cpp
docker compose exec api python -m app.cli create-admin --email you@example.com
```

Ports are bound to **127.0.0.1** by default. To serve a LAN, put a TLS reverse proxy (Caddy, nginx) in front and set
`CORS_ORIGINS` and `PUBLIC_API_URL` accordingly — do not expose the API port directly. Model weights and Archive files
live in the `models` and `archive` volumes; the `backup` service dumps PostgreSQL and the Archive daily (14-day
retention). See [BACKUP_RECOVERY.md](BACKUP_RECOVERY.md).

The compose file is validated; container images were not built in the development environment (no Docker daemon).

## 6. Production checklist

`APP_ENV=production` (the API refuses to start with the default `SECRET_KEY`), a long random `SECRET_KEY`, a separate
`CREDENTIALS_KEY` (Fernet key) if you store provider credentials, PostgreSQL, TLS in front, backups tested with a
restore, `scripts/verify.sh` green, and `python scripts/independence_test.py` green on the target hardware.
