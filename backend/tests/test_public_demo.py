"""PUBLIC DEMO MODE: anonymous visitors explore the real application with least privilege, isolated sample data and
hard limits — and can never reach administration, approvals, tools, private data or external services."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def demo_app(fresh_db, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    from app.daemon import state
    from app.demo import public as demo

    demo.reset_limits()
    state.invalidate()
    from app.main import app

    with TestClient(app) as c:
        yield c
    state.invalidate()


def _visitor(app_client) -> TestClient:
    from app.main import app

    r = app_client.post("/api/demo/session")
    assert r.status_code == 200, r.text
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return c


def _admin(fresh_db) -> TestClient:
    """The demo operator's account, created on the server (the browser setup is disabled)."""
    from app.main import app
    from app.models import User
    from app.security.auth import hash_password, issue_token

    s = fresh_db.SessionLocal()
    u = User(email="operator@example.com", password_hash=hash_password("correct-horse-battery"), role="admin")
    s.add(u)
    s.commit()
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {issue_token(u)}"
    s.close()
    return c


def test_anonymous_visitor_gets_a_temporary_least_privilege_session(demo_app):
    st = demo_app.get("/api/auth/status").json()
    assert st["demo_mode"] is True and st["setup_required"] is False
    r = demo_app.post("/api/demo/session").json()
    assert r["user"]["role"] == "demo" and r["user"]["email"].endswith("@demo.invalid") and r["expires_in_s"] == 120 * 60
    v = _visitor(demo_app)
    perms = set(v.get("/api/auth/me").json()["permissions"])
    assert {"knowledge.read", "runs.read", "work.run"} <= perms
    assert not perms & {"approval.decide", "tools.invoke", "tools.grant", "policy.write", "users.manage", "system.configure",
                        "models.manage", "knowledge.write", "knowledge.admin", "audit.export", "audit.retention"}


def test_nobody_can_claim_the_administrator_account_on_a_public_server(demo_app):
    r = demo_app.post("/api/auth/setup", json={"email": "attacker@example.com", "password": "correct-horse-battery"})
    assert r.status_code == 403 and "disabled on the public demo" in r.text


def test_admin_operations_settings_and_uploads_are_refused(demo_app):
    v = _visitor(demo_app)
    assert v.get("/api/auth/users").status_code == 403
    assert v.post("/api/auth/users", json={"email": "x@example.com", "password": "correct-horse-battery", "role": "admin"}).status_code == 403
    assert v.patch("/api/daemon/settings", json={"offline_mode": False}).status_code == 403
    assert v.post("/api/archive/text", json={"title": "x", "text": "y"}).status_code == 403
    assert v.post("/api/system/kill-switch", json={"engaged": True, "reason": "x"}).status_code == 403
    assert v.get("/api/daemon/credentials").status_code == 403
    assert v.post("/api/demo").status_code == 403  # loading/clearing sample data is the operator's


def test_visitors_run_only_the_approved_sample_workflows_and_see_only_their_own(demo_app):
    a, b = _visitor(demo_app), _visitor(demo_app)
    assert a.post("/api/gsus/runs", json={"objective": "Launch every product and buy ads"}).status_code == 403
    r = a.post("/api/gsus/runs", json={"objective": "Evaluate the winter commuter pannier and create brand concepts"})
    assert r.status_code == 200 and r.json()["status"] == "completed", r.text
    rid, trace = r.json()["id"], r.json()["trace_run_id"]
    assert [x["id"] for x in a.get("/api/gsus/runs").json()] == [rid]
    assert b.get("/api/gsus/runs").json() == [] and b.get(f"/api/gsus/runs/{rid}").status_code == 404
    assert {x["id"] for x in a.get("/api/runs").json()} >= {trace} and b.get("/api/runs").json() == []
    # the owner can follow the trace down into the delegated tasks; another visitor cannot open it
    rep = a.get(f"/api/runs/{trace}/replay").json()
    assert rep["children"] and a.get(f"/api/runs/{rep['children'][0]['id']}/replay").status_code == 200
    assert b.get(f"/api/runs/{trace}/replay").status_code == 404


def test_an_approval_required_workflow_stops_and_a_visitor_cannot_approve_it(demo_app):
    v = _visitor(demo_app)
    r = v.post("/api/gsus/runs", json={"objective": "Launch the hand-crank emergency radio"}).json()
    assert r["status"] == "waiting_for_approval"
    gate = next(s for s in r["steps"] if s["kind"] == "approval_gate")
    d = v.post(f"/api/approvals/{gate['approval_id']}/decide", json={"approve": True})
    assert d.status_code == 403 and "approval.decide" in d.text


def test_tools_are_denied_without_a_grant(demo_app):
    v = _visitor(demo_app)
    r = v.post("/api/tools/calc/invoke", json={"args": {"expression": "6*7"}})
    assert r.status_code == 403 and "tools.invoke" in r.text


def test_sample_vault_search_never_returns_the_restricted_memo(demo_app, fresh_db):
    v = _visitor(demo_app)
    hits = v.post("/api/archive/search", json={"query": "LANTERN-RESTRICTED-7 approvals", "k": 10}).json()
    titles = [h["title"] for h in hits["results"]]
    assert titles and "Restricted memo (synthetic sample)" not in titles  # public docs match "approvals"; the memo is filtered
    admin = _admin(fresh_db)
    hits = admin.post("/api/archive/search", json={"query": "LANTERN-RESTRICTED-7", "k": 10}).json()
    assert "Restricted memo (synthetic sample)" in [h["title"] for h in hits["results"]]
    docs = [d["title"] for d in v.get("/api/archive/documents").json()]
    assert "How consequential actions are approved" in docs and "Restricted memo (synthetic sample)" not in docs


def test_the_demo_is_always_offline_whatever_is_saved(demo_app, fresh_db):
    from app.daemon import state

    s = fresh_db.SessionLocal()
    state.save(s, {**state.load(s), "offline_mode": False})
    s.commit()
    s.close()
    state.invalidate()
    assert state.load()["offline_mode"] is True
    ext = next(c for c in demo_app.get("/api/status").json()["components"] if c["id"] == "external_ai")
    assert ext["status"] == "disabled"


def test_each_session_has_an_action_budget(demo_app, monkeypatch):
    monkeypatch.setenv("DEMO_ACTIONS_PER_SESSION", "2")
    v = _visitor(demo_app)
    assert v.post("/api/ai/ask", json={"question": "What is 25% of 480?"}).status_code == 200
    assert v.post("/api/ai/evals/run").status_code == 200
    r = v.post("/api/ai/ask", json={"question": "What is 10% of 50?"})
    assert r.status_code == 429 and "actions" in r.text
    assert v.get("/api/demo/catalog").json()["actions_left"] == 0


def test_session_creation_is_rate_limited(demo_app, monkeypatch):
    monkeypatch.setenv("DEMO_SESSIONS_PER_CLIENT_HOUR", "2")
    h = {"X-Forwarded-For": "198.51.100.9"}
    assert [demo_app.post("/api/demo/session", headers=h).status_code for _ in range(3)] == [200, 200, 429]
    assert demo_app.post("/api/demo/session", headers={"X-Forwarded-For": "198.51.100.10"}).status_code == 200
    monkeypatch.setenv("DEMO_SESSIONS_PER_HOUR", "3")  # 3 sessions exist: the global cap holds whatever address is claimed
    assert demo_app.post("/api/demo/session", headers={"X-Forwarded-For": "198.51.100.11"}).status_code == 429


def test_activity_is_audited(demo_app):
    v = _visitor(demo_app)
    v.post("/api/gsus/runs", json={"objective": "Evaluate the magnetic LED reading lamp", "mode": "watchman"})
    me = v.get("/api/auth/me").json()["email"]
    actions = {(x["actor"], x["action"]) for x in v.get("/api/audit/records?limit=500").json()}
    assert (me, "demo.session") in actions and (me, "gsus.run") in actions


def test_scheduled_reset_removes_visitors_and_reseeds(demo_app):
    from app.demo import public as demo

    v = _visitor(demo_app)
    assert v.post("/api/ai/ask", json={"question": "What is 25% of 480?"}).status_code == 200
    out = demo.reset()
    assert out["reset"] is True
    assert v.get("/api/auth/me").status_code == 401  # the visitor account is gone
    w = _visitor(demo_app)
    assert w.get("/api/runs").json() == []
    assert "How consequential actions are approved" in [d["title"] for d in w.get("/api/archive/documents").json()]
    assert w.get("/api/agents").status_code == 200 and len(w.get("/api/agents").json()) > 10


def test_public_status_ready_and_version_reveal_no_internals(demo_app):
    for path in ("/health", "/ready", "/api/version", "/api/status"):
        assert demo_app.get(path).status_code == 200, path
    st = demo_app.get("/api/status").json()
    assert st["environment"] == "public-demo" and st["overall"] == "operational"
    assert {c["id"] for c in st["components"]} >= {"backend", "database", "agents", "local_models", "external_ai"}
    raw = demo_app.get("/api/status").text.lower()
    for leak in ("sqlite:///", "postgresql", "secret", "password", "/home/", "@demo.invalid", "traceback"):
        assert leak not in raw, leak


def test_demo_endpoints_do_not_exist_on_a_private_server(client):
    assert client.post("/api/demo/session").status_code == 404
    st = client.get("/api/status").json()
    assert st["demo_mode"] is False and st["environment"] == "development"
    assert client.get("/api/auth/status").json()["demo_mode"] is False


def test_unexpected_errors_never_leak_internals(demo_app, monkeypatch):
    """A crash inside a public endpoint returns a bare 500 — no stack trace, file path or exception text."""
    from fastapi.testclient import TestClient

    import app.api.public_routes as pr
    from app.main import app

    def boom() -> str:
        raise RuntimeError("secret internals: /home/app/config.py password=hunter2")

    monkeypatch.setattr(pr, "_env_label", boom)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/version")
    assert r.status_code == 500
    assert "hunter2" not in r.text and "Traceback" not in r.text and "config.py" not in r.text and "RuntimeError" not in r.text
    assert r.text.strip() == "Internal Server Error"
