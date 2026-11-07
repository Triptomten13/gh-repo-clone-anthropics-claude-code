---
name: test-and-verify
description: Run the full verification for this repo (lint, backend tests, type check, frontend build, optional PostgreSQL smoke and browser check) and report results honestly. Use before committing or when asked whether something works.
---
1. `scripts/verify.sh` — ruff, pytest, `tsc --noEmit`, `next build`. Report pass/fail counts exactly as printed.
2. If models, migrations or queries changed: start PostgreSQL and run `DATABASE_URL=postgresql+psycopg://… python scripts/pg_smoke.py`
   — it migrates the database and exercises the main endpoints (catches SQLite-only SQL).
3. If UI changed: start the API (`uvicorn app.main:app --port 8000` in `backend/`) and the web app (`npx next start` after build),
   then drive the changed page with Playwright and look at a screenshot. Check the browser console for errors.
4. Never mark a step as passed that you did not run. If something could not run (no Docker, no API key), say so.
