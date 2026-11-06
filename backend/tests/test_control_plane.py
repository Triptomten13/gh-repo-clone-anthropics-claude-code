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
