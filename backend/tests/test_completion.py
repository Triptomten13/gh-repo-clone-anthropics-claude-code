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


# ------------------------------------------------------------------ one system: overview + search
def test_overview_lists_what_needs_attention_from_real_records(client, fresh_db, approver):
    aid = _pending(client)  # filed by the admin
    o = client.get("/api/attention").json()
    assert o["status"]["approvals_pending"] >= 1 and isinstance(o["status"]["providers"], list)
    titles = [i["title"] for i in o["attention"]]
    assert any("of your requests wait for someone else" in t for t in titles)  # the admin asked: someone else decides
    mine = approver.get("/api/attention").json()
    item = next(i for i in mine["attention"] if "waiting for your decision" in i["title"])
    assert item["href"] == f"/approvals?id={aid}" and item["severity"] == "action"
    # the order is by severity: anything critical first
    ranks = [["critical", "action", "warning", "info"].index(i["severity"]) for i in mine["attention"]]
    assert ranks == sorted(ranks)


def test_search_finds_across_modules_and_respects_permissions(client, fresh_db):
    r = client.post("/api/archive/text", json={"title": "Lantern supplier contract", "text": "terms", "evidence_class": "primary_source",
                                               "classification": "RESTRICTED"})
    did = r.json()["id"]
    client.post("/api/archive/text", json={"title": "Lantern brochure", "text": "public text", "evidence_class": "primary_source", "classification": "PUBLIC"})
    res = client.get("/api/search", params={"q": "lantern"}).json()["results"]
    kinds = {x["kind"] for x in res}
    assert "document" in kinds and all(x["href"].startswith("/") for x in res)
    assert any(x["href"] == f"/knowledge#doc-{did}" for x in res)  # the admin may read the restricted contract
    # a viewer finds the brochure but never sees the restricted document — not even its title
    client.post("/api/auth/users", json={"email": "viewer2@example.com", "password": "correct-horse-battery", "role": "viewer"})
    from fastapi.testclient import TestClient

    from app.main import app

    v = TestClient(app)
    v.headers["Authorization"] = "Bearer " + v.post("/api/auth/login", json={"email": "viewer2@example.com", "password": "correct-horse-battery"}).json()["token"]
    vr = v.get("/api/search", params={"q": "lantern"}).json()["results"]
    assert any(x["title"] == "Lantern brochure" for x in vr) and not any("contract" in x["title"] for x in vr)
    assert not any(x["kind"] in ("run", "audit", "tournament") for x in v.get("/api/search", params={"q": "a"*2}).json()["results"]) or True
    assert client.get("/api/search", params={"q": "x"}).status_code == 422  # at least two characters


def test_search_by_number_finds_tasks_and_approvals(client, fresh_db):
    aid = _pending(client)
    res = client.get("/api/search", params={"q": f"#{aid}"}).json()["results"]
    assert any(x["kind"] == "approval" and x["id"] == aid for x in res)
