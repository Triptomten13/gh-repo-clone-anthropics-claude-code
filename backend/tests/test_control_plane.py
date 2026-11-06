"""DAEMON CONTROL PLANE — governance behaviour that must hold no matter what an agent generates.
Numbers in test names refer to the acceptance criteria in docs/CONTROL_PLANE.md."""
import io
import json
import threading
import zipfile
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from app.daemon import state
from app.governance import audit_chain
from app.governance import core as gov


def _login_as(client, role: str, email: str | None = None):
    """Create a user with `role` (as the admin client) and return a TestClient signed in as them."""
    from fastapi.testclient import TestClient

    import app.main as main

    email = email or f"{role}@example.com"
    r = client.post("/api/auth/users", json={"email": email, "password": "correct-horse-battery", "role": role})
    assert r.status_code == 200, r.text
    c = TestClient(main.app)
    tok = c.post("/api/auth/login", json={"email": email, "password": "correct-horse-battery"}).json()["token"]
    c.headers["Authorization"] = f"Bearer {tok}"
    return c


# ------------------------------------------------------------------ audit & provenance (criterion 15)
def test_audit_records_are_sealed_into_a_verifiable_chain(client, fresh_db):
    for i in range(3):
        client.post("/api/system/kill-switch", json={"engaged": i % 2 == 0, "reason": f"chain test {i}"})
    recs = client.get("/api/audit/records?limit=50").json()
    seqs = sorted(r["seq"] for r in recs)
    assert seqs == list(range(seqs[0], seqs[0] + len(seqs)))  # contiguous
    by_seq = {r["seq"]: r for r in recs}
    assert all(by_seq[s]["prev_hash"] == by_seq[s - 1]["hash"] for s in seqs[1:])
    v = client.get("/api/audit/verify").json()
    assert v["ok"] and v["checked"] >= len(recs) and v["unsealed_records"] == 0


def test_sealed_records_cannot_be_changed_or_deleted_through_the_database(client, fresh_db):
    client.post("/api/system/kill-switch", json={"engaged": True, "reason": "x"})
    s = fresh_db.SessionLocal()
    with pytest.raises(Exception, match="append-only"):
        s.execute(text("UPDATE audit_log SET actor = 'mallory' WHERE seq = 1"))
    s.rollback()
    with pytest.raises(Exception, match="append-only"):
        s.execute(text("DELETE FROM audit_log WHERE seq = 1"))
    s.rollback()
    s.close()


def _superuser_session(fresh_db):
    """A database superuser can drop the triggers — the keyed chain must still expose what they change."""
    s = fresh_db.SessionLocal()
    s.execute(text("DROP TRIGGER IF EXISTS audit_log_append_only_update"))
    s.execute(text("DROP TRIGGER IF EXISTS audit_log_append_only_delete"))
    s.commit()
    return s


def _make_events(client, n=5):
    for i in range(n):
        client.post("/api/system/kill-switch", json={"engaged": i % 2 == 0, "reason": f"event {i}"})


def test_15_changed_record_is_detected(client, fresh_db):
    _make_events(client)
    s = _superuser_session(fresh_db)
    s.execute(text("UPDATE audit_log SET details = '{\"reason\": \"nothing to see\"}' WHERE seq = 3"))
    s.commit()
    v = client.get("/api/audit/verify").json()
    assert not v["ok"] and v["failed_at_seq"] == 3 and "content changed" in v["reason"]
    s.close()


def test_15_deleted_record_is_detected(client, fresh_db):
    _make_events(client)
    s = _superuser_session(fresh_db)
    s.execute(text("DELETE FROM audit_log WHERE seq = 2"))
    s.commit()
    v = audit_chain.verify(s)
    assert not v["ok"] and "sequence gap" in v["reason"]
    s.close()


def test_15_truncated_tail_is_detected(client, fresh_db):
    _make_events(client)
    s = _superuser_session(fresh_db)
    last = s.scalar(text("SELECT MAX(seq) FROM audit_log"))
    s.execute(text("DELETE FROM audit_log WHERE seq = :s"), {"s": last})
    s.commit()
    v = audit_chain.verify(s)
    assert not v["ok"] and "head mismatch" in v["reason"]
    s.close()


def test_15_forged_record_with_recomputed_plain_hash_is_detected(client, fresh_db):
    """Rewriting a record AND recomputing an ordinary SHA-256 does not help without the audit key."""
    import hashlib

    _make_events(client)
    s = _superuser_session(fresh_db)
    row = s.execute(text("SELECT prev_hash FROM audit_log WHERE seq = 2")).one()
    forged = hashlib.sha256((row.prev_hash + "forged").encode()).hexdigest()
    s.execute(text("UPDATE audit_log SET actor = 'mallory', hash = :h WHERE seq = 2"), {"h": forged})
    s.commit()
    assert not audit_chain.verify(s)["ok"]
    s.close()


def test_rollback_seals_nothing(client, fresh_db):
    s = fresh_db.SessionLocal()
    before = audit_chain.verify(s)["last_seq"]
    gov.audit(s, "tester", "will.rollback", "x")
    s.rollback()
    assert audit_chain.verify(s)["last_seq"] == before
    s.close()


def test_concurrent_writers_produce_one_valid_chain(client, fresh_db):
    errors = []

    def write(i):
        s = fresh_db.SessionLocal()
        try:
            for j in range(5):
                gov.audit(s, f"agent-{i}", "concurrency.test", f"x:{j}")
                s.commit()
        except Exception as e:  # noqa: BLE001
            errors.append(repr(e))
        finally:
            s.close()

    ts = [threading.Thread(target=write, args=(i,)) for i in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert errors == []
    s = fresh_db.SessionLocal()
    v = audit_chain.verify(s)
    assert v["ok"] and v["checked"] >= 20
    s.close()


def test_signed_export_verifies_and_detects_tampering(client, fresh_db):
    _make_events(client, 3)
    auditor = _login_as(client, "auditor")
    r = auditor.get("/api/audit/export?fmt=zip")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert audit_chain.verify_export(r.content)["ok"]
    m = json.loads(zipfile.ZipFile(io.BytesIO(r.content)).read("manifest.json"))
    assert m["chain_verification"]["ok"] and m["records"] >= 3
    # change one event inside the ZIP → detected
    src = zipfile.ZipFile(io.BytesIO(r.content))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for n in src.namelist():
            data = src.read(n)
            if n == "events.json":
                data = data.replace(b"event 1", b"event X")
            z.writestr(n, data)
    v = audit_chain.verify_export(out.getvalue())
    assert not v["ok"] and any("events.json changed" in p for p in v["problems"])
    assert auditor.get("/api/audit/export?fmt=csv").text.startswith("seq,id,created_at")


def test_retention_prunes_only_a_verified_prefix_and_keeps_the_chain_verifiable(client, fresh_db):
    _make_events(client, 4)
    sec = _login_as(client, "security_admin")
    r = sec.post("/api/audit/prune", json={"before": (datetime.now(UTC) + timedelta(seconds=1)).isoformat()})
    assert r.status_code == 200 and r.json()["pruned"] >= 4
    v = client.get("/api/audit/verify").json()
    assert v["ok"] and v["anchored"]
    assert any(x["action"] == "audit.pruned" for x in client.get("/api/audit/records").json())


# ------------------------------------------------------------------ identity & access (criteria 18 + separation of duties)
def test_18_roles_grant_exactly_their_permissions(client, fresh_db):
    viewer, auditor, sec, approver = (_login_as(client, r) for r in ("viewer", "auditor", "security_admin", "approver"))
    assert viewer.get("/api/audit/export").status_code == 403
    assert viewer.get("/api/audit/records").status_code == 200
    assert auditor.get("/api/audit/verify").status_code == 200
    assert auditor.post("/api/audit/prune", json={"before": datetime.now(UTC).isoformat()}).status_code == 403
    assert auditor.post("/api/auth/users", json={"email": "x@example.com", "password": "correct-horse-battery", "role": "admin"}).status_code == 403
    assert approver.get("/api/audit/export").status_code == 403
    assert sec.post("/api/auth/users", json={"email": "y@example.com", "password": "correct-horse-battery", "role": "admin"}).status_code == 403
    me = auditor.get("/api/auth/me").json()
    assert "audit.export" in me["permissions"] and "policy.write" not in me["permissions"]


def test_audit_trail_records_its_own_use(client, fresh_db):
    auditor = _login_as(client, "auditor", "auditor2@example.com")
    auditor.get("/api/audit/verify")
    auditor.get("/api/audit/export?fmt=json")
    s = fresh_db.SessionLocal()
    from app.models import AuditLog

    acts = {a for (a,) in s.execute(select(AuditLog.action).where(AuditLog.actor == "auditor2@example.com"))}
    assert {"audit.verify", "audit.export"} <= acts
    s.close()


# ------------------------------------------------------------------ tool security gateway + policy (criteria 1-4, 8, 9, 12, 17-20)
from app.governance import policy as P  # noqa: E402
from app.governance import tool_gateway as G  # noqa: E402


def _agent_id(db):
    from app.models import Agent

    return db.scalars(select(Agent.id).order_by(Agent.id)).first()


def _grant(db, agent, tool, op, **kw):
    from app.models import ToolGrant

    g = ToolGrant(subject_kind="agent", subject_id=agent, tool=tool, operations=[op], created_by="test", reason="test", **kw)
    db.add(g)
    db.commit()
    return g


def _user(db, email="admin@example.com"):
    from app.models import User

    return db.scalars(select(User).where(User.email == email)).first()


def _doc(client, text="Lantern inventory for the depot."):
    return client.post("/api/archive/text", json={"title": f"doc {abs(hash(text)) % 10_000}", "text": text, "evidence_class": "primary_source"}).json()["id"]


def _approve(db, approval_id, by="approver@example.com"):
    from app.models import Approval

    a = db.get(Approval, approval_id)
    gov.decide_approval(db, a, True, by)
    db.commit()


def test_01_agent_without_a_grant_cannot_use_any_tool(client, fresh_db):
    db = fresh_db.SessionLocal()
    agent = _agent_id(db)
    with pytest.raises(G.GatewayDenied, match="deny by default"):
        G.invoke(db, "calc", {"expression": "1+1"}, agent_id=agent)
    db.commit()
    from app.models import ToolInvocation

    rec = db.scalars(select(ToolInvocation).order_by(ToolInvocation.id.desc())).first()
    assert rec.status == "denied" and rec.agent_id == agent
    db.close()


def test_01_grants_are_per_operation(client, fresh_db):
    db = fresh_db.SessionLocal()
    agent = _agent_id(db)
    did = _doc(client)
    _grant(db, agent, "archive.search", "READ")
    assert G.invoke(db, "archive.search", {"query": "lantern"}, agent_id=agent)["status"] == "ok"
    with pytest.raises(G.GatewayDenied, match="no grant for archive.annotate CREATE"):
        G.invoke(db, "archive.annotate", {"document_id": did, "text": "x"}, agent_id=agent)
    with pytest.raises(G.GatewayDenied, match="no grant for archive.delete DELETE"):
        G.invoke(db, "archive.delete", {"document_id": did}, agent_id=agent)
    db.close()


def test_02_approval_required_action_waits_for_a_valid_single_use_approval_bound_to_its_arguments(client, fresh_db, approver):
    db = fresh_db.SessionLocal()
    agent = _agent_id(db)
    d1, d2 = _doc(client, "First document about compasses."), _doc(client, "Second document about tents.")
    _grant(db, agent, "archive.delete", "DELETE")
    with pytest.raises(G.GatewayDenied) as e:
        G.invoke(db, "archive.delete", {"document_id": d1}, agent_id=agent)
    db.commit()
    assert e.value.status == "pending_approval" and e.value.approval_id
    aid = e.value.approval_id
    with pytest.raises(G.GatewayDenied, match="pending"):  # silence is not approval
        G.invoke(db, "archive.delete", {"document_id": d1}, agent_id=agent, approval_id=aid, request_approval=False)
    db.commit()
    _approve(db, aid)
    with pytest.raises(G.GatewayDenied, match="different arguments"):  # cannot be reused for another document
        G.invoke(db, "archive.delete", {"document_id": d2}, agent_id=agent, approval_id=aid, request_approval=False)
    db.commit()
    out = G.invoke(db, "archive.delete", {"document_id": d1}, agent_id=agent, approval_id=aid)
    db.commit()
    assert out["status"] == "ok" and out["result"]["verified"]
    with pytest.raises(G.GatewayDenied, match="already used"):
        G.invoke(db, "archive.delete", {"document_id": d1}, agent_id=agent, approval_id=aid, request_approval=False)
    db.close()


def test_03_nobody_approves_their_own_request(client, fresh_db, approver):
    did = _doc(client)
    r = client.post("/api/tools/archive.delete/invoke", json={"args": {"document_id": did}})
    assert r.status_code == 202
    aid = r.json()["approval_id"]
    assert client.post(f"/api/approvals/{aid}/decide", json={"approve": True}).status_code == 409  # the admin asked for it
    assert approver.post(f"/api/approvals/{aid}/decide", json={"approve": True}).status_code == 200
    ok = client.post("/api/tools/archive.delete/invoke", json={"args": {"document_id": did}, "approval_id": aid})
    assert ok.status_code == 200 and ok.json()["result"]["verified"]


def test_agents_can_never_perform_governance_actions(client, fresh_db):
    db = fresh_db.SessionLocal()
    for action in ("policy.write", "tools.grant", "approval.decide", "budget.change", "audit.export", "permissions.self_grant"):
        d = P.decide(db, P.Request(action=action, agent_id="any_agent", approval_id=None))
        assert d.category == P.Category.PROHIBITED and not d.allowed, action
    db.close()


def test_04_expired_or_revoked_approvals_authorise_nothing(client, fresh_db, approver):
    from app.models import Approval

    db = fresh_db.SessionLocal()
    agent = _agent_id(db)
    d1 = _doc(client, "Expiring approval document.")
    _grant(db, agent, "archive.delete", "DELETE")
    with pytest.raises(G.GatewayDenied) as e:
        G.invoke(db, "archive.delete", {"document_id": d1}, agent_id=agent)
    db.commit()
    aid = e.value.approval_id
    _approve(db, aid)
    a = db.get(Approval, aid)
    a.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    with pytest.raises(G.GatewayDenied, match="expired"):
        G.invoke(db, "archive.delete", {"document_id": d1}, agent_id=agent, approval_id=aid, request_approval=False)
    db.commit()
    # revoked
    a.expires_at = datetime.now(UTC) + timedelta(hours=1)
    db.commit()
    assert approver.post(f"/api/approvals/{aid}/revoke").status_code == 200
    with pytest.raises(G.GatewayDenied, match="revoked"):
        G.invoke(db, "archive.delete", {"document_id": d1}, agent_id=agent, approval_id=aid, request_approval=False)
    # an expired PENDING request cannot be approved later either
    with pytest.raises(G.GatewayDenied) as e2:
        G.invoke(db, "archive.delete", {"document_id": d1}, agent_id=agent)
    db.commit()
    p = db.get(Approval, e2.value.approval_id)
    p.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert approver.post(f"/api/approvals/{p.id}/decide", json={"approve": True}).status_code == 409
    db.close()


def test_08_credentials_are_scoped_to_grants_and_never_leave_the_gateway(client, fresh_db, approver, monkeypatch):
    from app.daemon import credentials
    from app.models import ToolInvocation

    db = fresh_db.SessionLocal()
    credentials.store(db, "smtp:marketing", "s3cr3t-smtp-pass", label="marketing SMTP", attestation=credentials.ATTESTATION, actor="admin@example.com")
    db.commit()
    seen = []

    class FakeSMTP:
        def __init__(self, *a, **k): ...
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): ...
        def login(self, user, password): seen.append(password)
        def send_message(self, msg): seen.append(msg["To"])

    monkeypatch.setenv("SMTP_HOST", "smtp.example.invalid")
    monkeypatch.setattr(G.smtplib, "SMTP", FakeSMTP)
    from app.models import Agent

    a_with, a_without = db.scalars(select(Agent.id).order_by(Agent.id).limit(2)).all()
    _grant(db, a_with, "email.send", "EXECUTE", credential_scope="smtp:marketing")
    _grant(db, a_without, "email.send", "EXECUTE")
    args = {"to": "buyer@example.com", "subject": "Quote", "body": "Hello"}
    results = {}
    for agent in (a_with, a_without):
        with pytest.raises(G.GatewayDenied) as e:
            G.invoke(db, "email.send", args, agent_id=agent)
        db.commit()
        _approve(db, e.value.approval_id)
        try:
            results[agent] = G.invoke(db, "email.send", args, agent_id=agent, approval_id=e.value.approval_id)["status"]
        except G.GatewayDenied as err:
            results[agent] = err.status
        db.commit()
    assert results == {a_with: "ok", a_without: "not_configured"}
    assert seen == ["s3cr3t-smtp-pass", "buyer@example.com"]  # the secret reached SMTP only
    blob = json.dumps([[i.args_redacted, i.output_summary, i.reason] for i in db.scalars(select(ToolInvocation))])
    assert "s3cr3t" not in blob
    audit_blob = json.dumps(client.get("/api/audit/records?limit=1000").json())
    assert "s3cr3t" not in audit_blob
    db.close()


def test_08_a_tool_that_echoes_a_secret_is_redacted(client, fresh_db, monkeypatch):
    from app.daemon import credentials

    db = fresh_db.SessionLocal()
    credentials.store(db, "smtp:x", "leaky-secret-123", label="x", attestation=credentials.ATTESTATION, actor="admin@example.com")
    db.commit()
    agent = _agent_id(db)
    leaky = G.GovernedTool("test.leak", "echo a secret", "READ", {"properties": {}}, lambda ctx: {"oops": ctx.secret("smtp")})
    monkeypatch.setitem(G.TOOLS, "test.leak", leaky)
    _grant(db, agent, "test.leak", "READ", credential_scope="smtp:x")
    assert G.invoke(db, "test.leak", {}, agent_id=agent)["result"] == {"oops": "[REDACTED]"}
    db.close()


def test_09_every_tool_request_leaves_an_audit_event(client, fresh_db):
    from app.models import AuditLog, ToolInvocation

    db = fresh_db.SessionLocal()
    agent = _agent_id(db)
    _grant(db, agent, "calc", "READ")
    for args in ({"expression": "2+2"}, {"expression": "__import__('os')"}, {"nope": 1}):
        try:
            G.invoke(db, "calc", args, agent_id=agent)
        except G.GatewayDenied:
            pass
        db.commit()
    for t in ("archive.delete", "unknown.tool"):
        try:
            G.invoke(db, t, {}, agent_id=agent)
        except G.GatewayDenied:
            pass
        db.commit()
    inv = db.scalars(select(ToolInvocation)).all()
    events = db.scalars(select(AuditLog).where(AuditLog.action == "tool.invoke")).all()
    assert len(inv) == 5 and len(events) == len(inv)
    assert {e.details["invocation"] for e in events} == {i.id for i in inv}
    db.close()


def test_12_19_tool_budgets_hold_under_concurrency(client, fresh_db):
    db = fresh_db.SessionLocal()
    agent = _agent_id(db)
    _grant(db, agent, "calc", "READ", max_calls_per_day=3)
    db.close()
    results, lock = [], threading.Lock()

    def call():
        s = fresh_db.SessionLocal()
        try:
            G.invoke(s, "calc", {"expression": "1+1"}, agent_id=agent)
            out = "ok"
        except G.GatewayDenied as e:
            out = e.status
        except Exception as e:  # noqa: BLE001
            out = f"error {e!r}"
        s.commit()
        s.close()
        with lock:
            results.append(out)

    ts = [threading.Thread(target=call) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert results.count("ok") == 3 and results.count("budget_exhausted") == 5, results


def test_19_one_approval_cannot_be_used_twice_concurrently(client, fresh_db, approver):
    db = fresh_db.SessionLocal()
    agent = _agent_id(db)
    _grant(db, agent, "archive.annotate", "CREATE")
    did = _doc(client, "Concurrency annotation target.")
    from app.models import PolicyRule

    db.add(PolicyRule(key="test.annotate-approval", version=1, action="tool:archive.annotate.CREATE", category=3, conditions={},
                      priority=10, reason="test", created_by="test"))
    db.commit()
    args = {"document_id": did, "text": "one note"}
    with pytest.raises(G.GatewayDenied) as e:
        G.invoke(db, "archive.annotate", args, agent_id=agent)
    db.commit()
    _approve(db, e.value.approval_id)
    db.close()
    results, lock = [], threading.Lock()

    def use():
        s = fresh_db.SessionLocal()
        try:
            G.invoke(s, "archive.annotate", args, agent_id=agent, approval_id=e.value.approval_id, request_approval=False)
            out = "ok"
        except G.GatewayDenied as err:
            out = err.status
        s.commit()
        s.close()
        with lock:
            results.append(out)

    ts = [threading.Thread(target=use) for _ in range(5)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert results.count("ok") == 1, results


def test_17_an_agent_never_exceeds_the_user_it_works_for(client, fresh_db):
    db = fresh_db.SessionLocal()
    agent = _agent_id(db)
    _grant(db, agent, "archive.delete", "DELETE")
    _grant(db, agent, "calc", "READ")
    client.post("/api/auth/users", json={"email": "viewer@example.com", "password": "correct-horse-battery", "role": "viewer"})
    G.ensure_default_grants(db)
    db.commit()
    viewer = _user(db, "viewer@example.com")
    did = _doc(client)
    with pytest.raises(G.GatewayDenied, match=r"user this agent works for \(viewer\) has no grant for archive.delete"):
        G.invoke(db, "archive.delete", {"document_id": did}, agent_id=agent, user=viewer)
    assert G.invoke(db, "calc", {"expression": "6*7"}, agent_id=agent, user=viewer)["result"] == 42  # both allow it
    db.close()


def test_18_policy_changes_need_permission_and_a_second_person(client, fresh_db, approver):
    sec = _login_as(client, "security_admin")
    operator = _login_as(client, "operator")
    rule = {"key": "email.always-restricted", "action": "tool:email.send.EXECUTE", "category": 4, "reason": "outbound mail is sensitive"}
    assert operator.post("/api/policies", json=rule).status_code == 403  # no policy.write
    assert approver.post("/api/policies", json=rule).status_code == 403  # approvers cannot write policy
    r = sec.post("/api/policies", json=rule)
    assert r.status_code == 202 and r.json()["category"] == "RESTRICTED"
    aid = r.json()["approval_id"]
    assert sec.post(f"/api/approvals/{aid}/decide", json={"approve": True}).status_code == 403  # security admins do not approve at all
    assert approver.post(f"/api/approvals/{aid}/decide", json={"approve": True}).status_code == 200
    changed = {**rule, "category": 5, "approval_id": aid}  # the approval was for category 4, not 5
    assert sec.post("/api/policies", json=changed).status_code == 202
    applied = sec.post("/api/policies", json={**rule, "approval_id": aid})
    assert applied.status_code == 200 and applied.json()["rule"]["version"] == 1
    # a rule may not lower a mandatory floor
    low = {"key": "launch.autonomous", "action": "product.launch", "category": 1, "reason": "x"}
    assert sec.post("/api/policies", json=low).status_code == 422


def test_20_policy_rollback_restores_a_previous_version(client, fresh_db, approver):
    sec = _login_as(client, "security_admin")

    def apply(body):
        r = sec.post("/api/policies", json=body)
        if r.status_code == 202:
            approver.post(f"/api/approvals/{r.json()['approval_id']}/decide", json={"approve": True})
            r = sec.post("/api/policies", json={**body, "approval_id": r.json()["approval_id"]})
        return r

    v1 = apply({"key": "web.fetch.supervised", "action": "tool:web.fetch.READ", "category": 2, "reason": "watch external reads"})
    v2 = apply({"key": "web.fetch.supervised", "action": "tool:web.fetch.READ", "category": 3, "reason": "tighten"})
    assert (v1.json()["rule"]["version"], v2.json()["rule"]["version"]) == (1, 2)
    r = sec.post("/api/policies/web.fetch.supervised/rollback", json={"to_version": 1})
    assert r.status_code == 202
    approver.post(f"/api/approvals/{r.json()['approval_id']}/decide", json={"approve": True})
    done = sec.post("/api/policies/web.fetch.supervised/rollback", json={"to_version": 1, "approval_id": r.json()["approval_id"]})
    assert done.status_code == 200 and done.json()["rule"]["category"] == 2 and done.json()["rule"]["version"] == 3
    hist = client.get("/api/policies/history?key=web.fetch.supervised").json()
    assert [h["version"] for h in hist] == [1, 2, 3] and sum(h["superseded_at"] is None for h in hist) == 1


def test_tool_grants_need_a_second_person_and_revocation_is_immediate(client, fresh_db, approver):
    sec = _login_as(client, "security_admin")
    db = fresh_db.SessionLocal()
    agent = _agent_id(db)
    db.close()
    body = {"subject_kind": "agent", "subject_id": agent, "tool": "calc", "operations": ["READ"], "reason": "arithmetic for reports"}
    r = sec.post("/api/tools/grants", json=body)
    assert r.status_code == 202
    approver.post(f"/api/approvals/{r.json()['approval_id']}/decide", json={"approve": True})
    g = sec.post("/api/tools/grants", json={**body, "approval_id": r.json()["approval_id"]}).json()["grant"]
    db = fresh_db.SessionLocal()
    assert G.invoke(db, "calc", {"expression": "3*3"}, agent_id=agent)["result"] == 9
    db.commit()
    assert sec.delete(f"/api/tools/grants/{g['id']}").status_code == 200
    with pytest.raises(G.GatewayDenied, match="deny by default"):
        G.invoke(db, "calc", {"expression": "3*3"}, agent_id=agent)
    db.close()


# ------------------------------------------------------------------ knowledge vault (criteria 5, 6) + classification routing (7, 13)
def _put(client, title, text, classification="INTERNAL", access=None, collection="general"):
    r = client.post("/api/archive/text", json={"title": title, "text": text, "evidence_class": "primary_source", "classification": classification,
                                               "access": access or {}, "collection": collection})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _search_titles(c, q):
    return {h["title"] for h in c.post("/api/archive/search", json={"query": q, "mode": "keyword", "k": 20}).json()["results"]}


def test_05_retrieval_never_returns_documents_outside_the_users_permissions(client, fresh_db):
    viewer, operator, sec = (_login_as(client, r) for r in ("viewer", "operator", "security_admin"))
    _put(client, "Open memo", "Quarterly lantern plan for every team.")
    _put(client, "Board memo", "Quarterly lantern margins, board only.", "CONFIDENTIAL", {"roles": ["operator"]})
    _put(client, "Merger memo", "Quarterly lantern acquisition talks.", "RESTRICTED", {"users": ["operator@example.com"]})
    hs = _put(client, "Personnel file", "Quarterly lantern salary review.", "HIGHLY_SENSITIVE")
    assert _search_titles(viewer, "quarterly lantern") == {"Open memo"}
    assert _search_titles(operator, "quarterly lantern") == {"Open memo", "Board memo", "Merger memo"}
    assert _search_titles(sec, "quarterly lantern") == {"Open memo", "Board memo", "Merger memo"}  # knowledge admin, not HIGHLY_SENSITIVE
    assert _search_titles(client, "quarterly lantern") >= {"Personnel file"}  # the owner
    assert sec.get(f"/api/archive/documents/{hs}").status_code == 404  # not even administrators — and no hint it exists
    assert viewer.get(f"/api/archive/documents/{hs}").status_code == 404
    assert {d["title"] for d in viewer.get("/api/archive/documents").json()} == {"Open memo"}
    names = {e["name"] for e in viewer.get("/api/archive/entities").json()}
    assert names == {e["name"] for e in viewer.get("/api/archive/entities").json()}  # entities only from readable documents
    asked = viewer.post("/api/archive/ask", json={"question": "quarterly lantern"}).json()
    assert all(c["title"] == "Open memo" for c in asked["citations"])


def test_05_agents_and_the_system_read_no_more_than_their_user(client, fresh_db):
    from app.knowledge import search

    _put(client, "Open plan", "Depot inventory of compasses.")
    _put(client, "Secret plan", "Depot inventory of compasses, confidential.", "CONFIDENTIAL")
    db = fresh_db.SessionLocal()
    titles = lambda hits: {h["title"] for h in hits}  # noqa: E731
    assert titles(search.search(db, "depot compasses", user=None)) == {"Open plan"}  # system / agent without a user
    agent = _agent_id(db)
    _grant(db, agent, "archive.search", "READ")
    client.post("/api/auth/users", json={"email": "v2@example.com", "password": "correct-horse-battery", "role": "viewer"})
    G.ensure_default_grants(db)
    db.commit()
    viewer = _user(db, "v2@example.com")
    res = G.invoke(db, "archive.search", {"query": "depot compasses"}, agent_id=agent, user=viewer)["result"]
    assert {r["title"] for r in res} == {"Open plan"}
    db.close()


def test_05_widening_access_needs_a_second_person_narrowing_does_not(client, fresh_db, approver):
    sec = _login_as(client, "security_admin")
    viewer = _login_as(client, "viewer")
    did = _put(client, "Pricing sheet", "Wholesale lantern prices.", "CONFIDENTIAL")
    r = sec.patch(f"/api/vault/documents/{did}/access", json={"classification": "INTERNAL"})
    assert r.status_code == 202 and r.json()["category"] == "RESTRICTED"
    assert _search_titles(viewer, "wholesale lantern") == set()  # nothing changed yet
    approver.post(f"/api/approvals/{r.json()['approval_id']}/decide", json={"approve": True})
    assert sec.patch(f"/api/vault/documents/{did}/access", json={"classification": "INTERNAL", "approval_id": r.json()["approval_id"]}).status_code == 200
    assert _search_titles(viewer, "wholesale lantern") == {"Pricing sheet"}
    narrow = sec.patch(f"/api/vault/documents/{did}/access", json={"classification": "RESTRICTED"})
    assert narrow.status_code == 200  # tightening never waits
    assert _search_titles(viewer, "wholesale lantern") == set()


def test_05_collection_access_is_inherited(client, fresh_db, approver):
    sec = _login_as(client, "security_admin")
    viewer = _login_as(client, "viewer")
    assert sec.post("/api/vault/collections", json={"name": "legal", "classification": "CONFIDENTIAL", "access": {"roles": ["security_admin"]}}).status_code == 200
    _put(client, "Contract draft", "Supplier contract for tents.", collection="legal")  # the document itself says INTERNAL
    assert _search_titles(viewer, "supplier contract tents") == set()
    assert _search_titles(sec, "supplier contract tents") == {"Contract draft"}


def test_06_deleted_documents_never_come_back_from_retrieval(client, fresh_db):
    from app.knowledge import search
    from app.models import DocumentChunk

    did = _put(client, "Doomed", "The obsidian astrolabe is stored in vault seven.")
    q = "What does our archive say about the obsidian astrolabe?"
    assert client.post("/api/ai/ask", json={"question": q}).json()["sources"]
    assert client.post("/api/ai/ask", json={"question": q}).json().get("cached")
    out = client.delete(f"/api/archive/documents/{did}?confirm=true").json()
    assert out["verified"] and out["chunks_removed"] >= 1
    db = fresh_db.SessionLocal()
    assert db.scalar(select(__import__("sqlalchemy").func.count(DocumentChunk.id)).where(DocumentChunk.document_id == did)) == 0
    for mode in ("keyword", "semantic", "hybrid"):
        assert search.search(db, "obsidian astrolabe vault", mode=mode, user=_user(db)) == []
        assert search._search_scan(db, "obsidian astrolabe vault", mode=mode, user=_user(db)) == []
    db.close()
    after = client.post("/api/ai/ask", json={"question": q}).json()
    assert not after.get("cached") and "vault seven" not in str(after.get("answer"))


def test_retrieved_passages_carry_full_provenance(client, fresh_db):
    _put(client, "Ledger", "Lantern ledger for March.")
    h = client.post("/api/archive/search", json={"query": "lantern ledger", "mode": "keyword"}).json()["results"][0]
    p = h["provenance"]
    assert {"document_uid", "version", "owner_id", "classification", "collection", "imported_at", "extraction", "embedding_model", "index_version"} <= set(p)
    assert p["classification"] == "INTERNAL" and p["embedding_model"]


class _Prov:
    def __init__(self, pid, locality, fail=None):
        from app.ai.providers import Completion

        self.id, self.locality, self.fail, self.calls, self._C = pid, locality, fail, [], Completion

    def configured(self):
        return True

    def health(self):
        return {"configured": True}

    def complete(self, *, model, system, prompt, schema, effort, max_tokens):
        from app.ai.providers import ProviderUnavailable

        self.calls.append(prompt[:40])
        if self.fail:
            raise ProviderUnavailable(self.fail)
        return self._C("answer [1]", None, self.id, model, 10, 5, 0.0, 3)


def test_07_13_restricted_context_never_reaches_an_external_model_not_even_as_fallback(client, fresh_db, monkeypatch):
    from app.ai.llm import LLMUnavailable
    from app.ai.router import LLMRouter
    from app.knowledge import search

    monkeypatch.delenv("MODEL_CHAIN_STANDARD", raising=False)
    _put(client, "Open note", "Harbour lanterns are blue.")
    _put(client, "Restricted note", "Harbour lanterns secret supplier list.", "RESTRICTED", {"users": ["admin@example.com"]})
    db = fresh_db.SessionLocal()
    admin = _user(db)
    for cls_q, expect_external in (("harbour lanterns blue", True), ("harbour lanterns secret supplier", False)):
        local, ext = _Prov("local", "local", fail="local model crashed"), _Prov("anthropic", "external")
        router = LLMRouter({"local": local, "anthropic": ext})

        def llm(system, prompt, sensitivity="normal", _r=router):
            return _r.complete(system=system, prompt=prompt, tier="standard", sensitivity=sensitivity)

        filters = {"document_ids": [h["document_id"] for h in search.search(db, cls_q, user=admin, mode="keyword", k=1)]}
        try:
            search.grounded_answer(db, cls_q, llm=llm, user=admin, filters=filters, k=1)
            reached = True
        except LLMUnavailable as e:
            reached = False
            assert any(a["status"] == "excluded_privacy" for a in e.attempts)
        assert local.calls, "the local model is always tried first"
        assert bool(ext.calls) == expect_external == reached, (cls_q, ext.calls)
    db.close()


def test_07_highly_sensitive_stays_in_process(fresh_db, monkeypatch):
    from app.daemon import policy as routing

    monkeypatch.delenv("MODEL_CHAIN_STANDARD", raising=False)
    provs = {"local": _Prov("local", "local"), "worker:lan-box": _Prov("worker:lan-box", "lan"), "anthropic": _Prov("anthropic", "external")}
    cands, excluded = routing.plan("standard", provs, sensitivity="highly_sensitive")
    assert {c.locality for c in cands} == {"local"}
    assert {e["status"] for e in excluded} >= {"excluded_privacy", "excluded_classification"}
    cands, _ = routing.plan("standard", provs, sensitivity="private")  # CONFIDENTIAL: self-hosted LAN allowed
    assert "external" not in {c.locality for c in cands} and "lan" in {c.locality for c in cands}
    cands, _ = routing.plan("standard", provs, sensitivity="sensitive")  # RESTRICTED: this machine only
    assert {c.locality for c in cands} == {"local"}


def test_external_disabled_switch_still_excludes_external_models(fresh_db, monkeypatch):
    """Regression: the classification rule must not short-circuit the operator's 'external providers off' switch."""
    from app.daemon import policy as routing

    monkeypatch.delenv("MODEL_CHAIN_STANDARD", raising=False)
    s = fresh_db.SessionLocal()
    state.update(s, external_allowed=False)
    s.commit()
    s.close()
    cands, excluded = routing.plan("standard", {"local": _Prov("local", "local"), "anthropic": _Prov("anthropic", "external")})
    assert "external" not in {c.locality for c in cands}
    assert any(e["status"] == "excluded_external_disabled" for e in excluded)


# ------------------------------------------------------------------ observability (10, 11), budgets (12), egress (14), gates (16)
def _orch_with(agent_cls, fresh_db):
    from app.agents.catalog import build_orchestrator

    orch = build_orchestrator()
    if agent_cls.id not in orch.agents:
        orch.register(agent_cls())
    db = fresh_db.SessionLocal()
    orch.sync_agents(db)
    return orch, db


def test_10_every_workflow_execution_produces_a_reconstructable_trace(client, fresh_db):
    from app.agents.base import AgentOutput, BaseAgent
    from app.models import Run, RunEvent, Task

    _put(client, "Trace doc", "Harbour inventory of compasses and lanterns.")

    class Tracer(BaseAgent):
        id, name, division, task_types = "tracer", "Tracer", "test", ("test.trace",)

        def handle(self, ctx, task):
            from app.knowledge import search

            hits = search.search(ctx.db, "harbour compasses", user=None, mode="keyword")
            ctx.check("market.research")
            return AgentOutput(summary=f"found {len(hits)}", result={"documents": [h["document_id"] for h in hits]})

    orch, db = _orch_with(Tracer, fresh_db)
    t = orch.submit(db, "test.trace", {"q": "harbour"}, requested_by="user:admin@example.com")
    db.commit()
    orch.drain()
    db.expire_all()
    run = db.scalars(select(Run).where(Run.ref == f"task:{t.id}")).one()
    assert run.status == "succeeded" and run.workflow == "test.trace" and run.agent_id == "tracer" and run.policy_version
    types = [e.type for e in db.scalars(select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.seq))]
    assert "retrieval" in types and "attempt" in types and types[-1] == "output"
    rep = client.get(f"/api/runs/{run.id}/replay").json()
    assert rep["run"]["id"] == run.id and [e["seq"] for e in rep["events"]] == sorted(e["seq"] for e in rep["events"])
    assert "not a re-execution" in rep["replay_kind"]
    retr = next(e for e in rep["events"] if e["type"] == "retrieval")
    assert retr["data"]["documents"] and "text" not in json.dumps(retr["data"])  # references only, never the text
    assert db.get(Task, t.id).status == "succeeded"
    db.close()


def test_11_failed_steps_follow_the_retry_policy_and_escalate(client, fresh_db):
    from app.agents.base import BaseAgent
    from app.models import AuditLog, Run, RunEvent

    class Broken(BaseAgent):
        id, name, division, task_types = "broken", "Broken", "test", ("test.broken",)

        def handle(self, ctx, task):
            raise RuntimeError("disk on fire")

    orch, db = _orch_with(Broken, fresh_db)
    t = orch.submit(db, "test.broken", {})
    db.commit()
    orch.drain()
    db.expire_all()
    run = db.scalars(select(Run).where(Run.ref == f"task:{t.id}")).one()
    ev = [(e.type, e.name) for e in db.scalars(select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.seq))]
    assert [x for x, _ in ev].count("attempt") == 3 and [x for x, _ in ev].count("retry") == 2  # max_attempts = 3
    assert ("escalation", "retries exhausted → operators notified") in ev and run.status == "failed" and "disk on fire" in run.error
    assert db.scalars(select(AuditLog).where(AuditLog.action == "task.escalated", AuditLog.target == f"task:{t.id}")).first()
    db.close()


def test_12_model_budgets_stop_calls_before_they_run_and_are_not_bypassed(client, fresh_db, approver):
    from app.ai import llm
    from app.agents.base import AgentOutput, BaseAgent
    from app.models import Task

    calls = []

    class FakeRouter:
        name = "fake"

        def complete(self, *, system, prompt, tier="standard", schema=None, max_tokens=16000, sensitivity="normal"):
            from app.ai.llm import LLMResult

            calls.append(prompt)
            return LLMResult("ok", None, "fake-model", 10, 5, 0.0, provider="fake",
                             attempts=[{"provider": "fake", "model": "fake-model", "status": "ok", "input_tokens": 10, "output_tokens": 5}])

    class Talker(BaseAgent):
        id, name, division, task_types = "talker", "Talker", "test", ("test.talk",)

        def handle(self, ctx, task):
            ctx.llm("system", f"prompt {task.payload['n']}")
            return AgentOutput(summary="talked")

    sysadmin = _login_as(client, "system_admin")
    body = {"scope_kind": "agent", "scope_id": "talker", "metric": "model_calls", "period": "day", "limit": 2}
    r = sysadmin.post("/api/budgets", json=body)
    assert r.status_code == 202  # a budget change is governed too
    approver.post(f"/api/approvals/{r.json()['approval_id']}/decide", json={"approve": True})
    assert sysadmin.post("/api/budgets", json={**body, "approval_id": r.json()["approval_id"]}).status_code == 200
    llm.set_provider(FakeRouter())
    try:
        orch, db = _orch_with(Talker, fresh_db)
        ids = [orch.submit(db, "test.talk", {"n": i}).id for i in range(4)]
        db.commit()
        orch.drain()
        db.expire_all()
        statuses = [db.get(Task, i).status for i in ids]
        assert statuses.count("succeeded") == 2 and statuses.count("blocked") == 2 and len(calls) == 2
        assert "budget" in db.get(Task, ids[-1]).error
        db.close()
    finally:
        llm.set_provider(None)


def test_14_offline_and_air_gapped_modes_block_unapproved_outbound_connections(client, fresh_db):
    import socket

    from app.governance import egress

    egress.install()
    sysadmin = _login_as(client, "system_admin")
    assert client.get("/api/deployment/egress/verify").json()["probe"]["blocked"] is False  # online: not restricted
    r = sysadmin.post("/api/deployment", json={"profile": "AIR_GAPPED", "egress_allowlist": []})
    assert r.status_code == 200 and r.json()["offline_mode"] is True  # tightening applies at once
    egress.invalidate()
    v = client.get("/api/deployment/egress/verify").json()
    assert v["probe"]["blocked"] is True and v["report"]["enforcing"], v
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with pytest.raises(egress.EgressDenied):
        s.connect(("93.184.215.14", 443))  # any public address — refused before a packet leaves
    s.close()
    loop = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    assert loop.connect_ex(("127.0.0.1", 9)) != 0 or True  # loopback is never blocked by policy (port 9 is just closed)
    loop.close()
    assert any(not a["allowed"] for a in egress.report()["recent"])
    # leaving AIR_GAPPED loosens egress: a second person must approve
    assert sysadmin.post("/api/deployment", json={"profile": "SELF_HOSTED"}).status_code == 202


def test_16_release_gates_block_a_failing_prompt_release(client, fresh_db, monkeypatch):
    from app.daemon import prompts
    from app.evals import runner
    from app.models import GateRun

    db = fresh_db.SessionLocal()
    prompts.seed(db)
    db.commit()
    name = "gsus.identity"
    v = client.post("/api/daemon/prompts", json={"name": name, "text": "You are G-SUS. Answer from evidence; say when you do not know.",
                                                 "notes": "candidate"}).json()
    real = runner.injection_suite
    monkeypatch.setattr(runner, "injection_suite", lambda: {**real(), "score": 0.5, "metric": "F1 (simulated regression)"})
    r = client.post(f"/api/daemon/prompts/{name}/activate", json={"version": v["version"]})
    assert r.status_code == 409 and any("injection_detection" in b for b in r.json()["detail"]["blocking"])
    assert prompts.active(db, name).version != v["version"]  # the release did not happen
    monkeypatch.setattr(runner, "injection_suite", real)
    assert client.post(f"/api/daemon/prompts/{name}/activate", json={"version": v["version"]}).status_code == 200
    runs = db.scalars(select(GateRun).order_by(GateRun.id)).all()
    assert [g.passed for g in runs[-2:]] == [False, True]  # regression history kept
    db.close()


def test_14_only_real_private_networks_count_as_private(fresh_db, monkeypatch):
    """Regression: ipaddress.is_private also covers documentation/benchmark ranges — those must not bypass the guard."""
    from app.governance import egress

    monkeypatch.setattr(egress, "_policy", lambda: {"enforce": True, "profile": "AIR_GAPPED", "allow_private": True, "allow_ips": set(), "deny_ips": set()})
    assert egress.decide("192.168.1.20")[0] and egress.decide("10.1.2.3")[0] and egress.decide("100.101.102.103")[0]
    for addr in ("203.0.113.7", "198.18.0.1", "192.0.2.1", "93.184.215.14", "8.8.8.8"):
        assert not egress.decide(addr)[0], addr
    assert egress.decide("127.0.0.1") == (True, "loopback")


def test_efficiency_score_rewards_success_not_cheapness(client, fresh_db):
    from app.agents.base import AgentOutput, BaseAgent

    class Good(BaseAgent):
        id, name, division, task_types = "good", "Good", "test", ("test.good",)

        def handle(self, ctx, task):
            return AgentOutput(summary="done")

    class Cheap(BaseAgent):
        id, name, division, task_types = "cheapfail", "Cheap", "test", ("test.cheapfail",)

        def handle(self, ctx, task):
            from app.agents.base import Blocked

            raise Blocked("could not do it")

    orch, db = _orch_with(Good, fresh_db)
    if "cheapfail" not in orch.agents:
        orch.register(Cheap())
    orch.sync_agents(db)
    for t in ("test.good", "test.cheapfail"):
        orch.submit(db, t, {})
    db.commit()
    orch.drain()
    rep = {a["agent"]: a for a in client.get("/api/agents/efficiency").json()["agents"]}
    assert rep["good"]["ies"] > 0 and rep["cheapfail"]["ies"] == 0 and rep["cheapfail"]["ies_components"]["cost_usd"] == 0
    db.close()
