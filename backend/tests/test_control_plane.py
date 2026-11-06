"""DAEMON CONTROL PLANE — governance behaviour that must hold no matter what an agent generates.
Numbers in test names refer to the acceptance criteria in docs/CONTROL_PLANE.md."""
import io
import json
import threading
import zipfile
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

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
