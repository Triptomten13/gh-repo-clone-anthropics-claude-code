import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("LLM_ENABLED", "false")
os.environ.setdefault("SECRET_KEY", "test-secret")

from app import db as dbmod  # noqa: E402


@pytest.fixture()
def fresh_db(tmp_path):
    dbmod.configure(f"sqlite:///{tmp_path / 'test.db'}")
    dbmod.init_db()
    from app.agents.catalog import build_orchestrator
    from app.ai import llm
    from app.integrations import registry

    from app.security.ratelimit import api_requests, login_failures

    from app.daemon import credentials, quota, state, workers

    llm.set_provider(None)
    registry.reset()
    api_requests.reset()
    login_failures.reset()
    state.invalidate()
    quota.reset()
    credentials.invalidate()
    workers.invalidate()
    os.environ["ARCHIVE_DIR"] = str(tmp_path / "archive")
    s = dbmod.SessionLocal()
    build_orchestrator().sync_agents(s)
    s.close()
    yield dbmod
    llm.set_provider(None)
    registry.reset()
    state.invalidate()
    quota.reset()
    credentials.invalidate()


@pytest.fixture()
def client(fresh_db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        r = c.post("/api/auth/setup", json={"email": "admin@example.com", "password": "correct-horse-battery"})
        assert r.status_code == 200, r.text
        c.headers["Authorization"] = f"Bearer {r.json()['token']}"
        yield c
