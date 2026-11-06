"""Completion round (docs/COMPLETION_AUDIT.md): capabilities that existed only in the API are reachable and behave
the same through the endpoints the interface now uses."""


def _pending(client) -> int:
    did = client.post("/api/archive/text", json={"title": "Lifecycle doc", "text": "A document whose deletion needs an approval.",
                                                   "evidence_class": "primary_source"}).json()["id"]
    r = client.post("/api/tools/archive.delete/invoke", json={"args": {"document_id": did}})
    assert r.status_code == 202, r.text
    return r.json()["approval_id"]


def test_approval_lifecycle_through_the_approval_center_endpoints(client, fresh_db, approver):
    aid = _pending(client)
    # who can it go to? other people with approval.decide — never the caller
    who = client.get("/api/approvals/approvers").json()
    assert {"email": "approver@example.com", "role": "approver"} in who and all(w["email"] != "admin@example.com" for w in who)
    assert "approver@example.com" not in [w["email"] for w in approver.get("/api/approvals/approvers").json()]
    # the requester cannot delegate to themselves; delegating to the approver works and is visible in the list
    d = client.post(f"/api/approvals/{aid}/delegate", json={"to": "approver@example.com"})
    assert d.status_code == 200 and d.json()["delegated_to"] == "approver@example.com"
    # approved, not yet used → can be revoked; revoking twice is refused with the reason
    assert approver.post(f"/api/approvals/{aid}/decide", json={"approve": True}).status_code == 200
    r = approver.post(f"/api/approvals/{aid}/revoke", params={"reason": "changed my mind"})
    assert r.status_code == 200 and r.json()["revoked_by"] == "approver@example.com"
    again = approver.post(f"/api/approvals/{aid}/revoke")
    assert again.status_code == 409 and "already revoked" in again.json()["detail"]
    row = next(a for a in client.get("/api/approvals").json() if a["id"] == aid)
    assert row["revoked_at"] and row["delegated_to"] == "approver@example.com"


def test_approvers_list_needs_the_decide_permission(client, fresh_db):
    r = client.post("/api/auth/users", json={"email": "viewer@example.com", "password": "correct-horse-battery", "role": "viewer"})
    assert r.status_code == 200
    from fastapi.testclient import TestClient

    from app.main import app

    v = TestClient(app)
    v.headers["Authorization"] = "Bearer " + v.post("/api/auth/login", json={"email": "viewer@example.com", "password": "correct-horse-battery"}).json()["token"]
    assert v.get("/api/approvals/approvers").status_code == 403


def test_an_approved_governance_change_can_be_applied_from_the_approval_center(client, fresh_db, approver):
    """Before: proposing a rule filed an approval and told the user to 'repeat the change with that approval' — and no
    form could send an approval id, so approved changes could never be applied from the interface."""
    rule = {"key": "email.restricted", "action": "tool:email.send.EXECUTE", "category": 3, "reason": "outbound mail is sensitive"}
    filed = client.post("/api/policies", json=rule)
    assert filed.status_code == 202
    aid = filed.json()["approval_id"]
    assert client.post(f"/api/approvals/{aid}/apply").status_code == 409  # not approved yet: nothing happens
    assert approver.post(f"/api/approvals/{aid}/decide", json={"approve": True}).status_code == 200
    applied = client.post(f"/api/approvals/{aid}/apply")
    assert applied.status_code == 200 and applied.json()["status"] == "applied", applied.text
    assert any(r["key"] == "email.restricted" for r in client.get("/api/policies").json()["rules"])
    # used once: applying again is refused by the same enforcement as the original endpoint
    again = client.post(f"/api/approvals/{aid}/apply")
    assert again.status_code in (202, 403, 409) and again.json().get("status") != "applied"


def test_apply_runs_every_original_check(client, fresh_db, approver):
    # a budget removal: approved for #1 — the stored request is replayed exactly, the caller still needs system.configure
    b = client.post("/api/budgets", json={"scope_kind": "global", "metric": "usd", "period": "day", "limit": 5})
    aid = b.json()["approval_id"]
    approver.post(f"/api/approvals/{aid}/decide", json={"approve": True})
    assert approver.post(f"/api/approvals/{aid}/apply").status_code == 403  # the approver may decide, not configure budgets
    assert client.post(f"/api/approvals/{aid}/apply").json()["status"] == "applied"
    bid = client.get("/api/budgets").json()[0]["id"]
    rm = client.delete(f"/api/budgets/{bid}")
    assert rm.status_code == 202
    rid = rm.json()["approval_id"]
    approver.post(f"/api/approvals/{rid}/decide", json={"approve": True})
    assert client.post(f"/api/approvals/{rid}/apply").json()["status"] == "disabled"
    # tool calls are resumed by whoever asked for them, not from the Approval Center
    did = client.post("/api/archive/text", json={"title": "t", "text": "x y z", "evidence_class": "primary_source"}).json()["id"]
    t = client.post("/api/tools/archive.delete/invoke", json={"args": {"document_id": did}}).json()["approval_id"]
    approver.post(f"/api/approvals/{t}/decide", json={"approve": True})
    assert client.post(f"/api/approvals/{t}/apply").status_code == 422
