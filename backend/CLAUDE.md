# Backend rules (FastAPI / SQLAlchemy)

- Layers: `api/` (HTTP, auth, validation) → `agents/` (orchestrated work) → `engines/`, `flare/`, `knowledge/`, `gsus/` (logic) → `models.py` / `db.py`.
  Engines are pure where possible and unit-tested; agents stay thin.
- All agent work goes through `agents/orchestrator.py` (`submit` + `drain`): budgets, kill switch, dedupe, dependencies, audit.
- Model calls only via `ai/llm.get_provider()` (router: tiers → provider chain, fallback, breaker). Record attempts with `ai/tracing.record`.
  Never hard-code a vendor model in an agent; ask for a tier. Check refusals; never fake output when `LLMUnavailable`.
- New tables/columns ⇒ Alembic migration (`alembic revision --autogenerate`), with server defaults for NOT NULL columns on existing tables
  and named constraints (SQLite batch mode). Test upgrade → downgrade → upgrade on SQLite **and** PostgreSQL.
- Portable SQL only: no equality on JSON columns (PostgreSQL `json` has no `=`), no SQLite-only functions.
- Audit every state-changing endpoint with `governance.core.audit`. Permissions: `require_role(...)` + `permissions.ACTION_LEVELS`.
- Lint: `ruff check .` (config in `pyproject.toml`). Tests: `python -m pytest` (fixtures in `tests/conftest.py` reset DB and rate limiters).
