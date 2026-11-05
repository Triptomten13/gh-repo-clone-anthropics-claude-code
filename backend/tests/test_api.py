def test_auth_required(fresh_db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        assert c.get("/api/auth/status").json()["setup_required"] is True
        assert c.get("/api/overview").status_code == 401
        assert c.post("/api/auth/setup", json={"email": "a@b.se", "password": "short"}).status_code == 422
        assert c.post("/api/auth/setup", json={"email": "a@b.se", "password": "long-enough-pw"}).status_code == 200
        assert c.post("/api/auth/setup", json={"email": "x@b.se", "password": "long-enough-pw"}).status_code == 409
        assert c.post("/api/auth/login", json={"email": "a@b.se", "password": "wrong-password"}).status_code == 401
        tok = c.post("/api/auth/login", json={"email": "a@b.se", "password": "long-enough-pw"}).json()["token"]
        assert c.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()["role"] == "admin"
        assert c.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}x"}).status_code == 401


def test_viewer_cannot_mutate(client):
    client.post("/api/auth/users", json={"email": "v@b.se", "password": "viewer-password", "role": "viewer"})
    tok = client.post("/api/auth/login", json={"email": "v@b.se", "password": "viewer-password"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/products", headers=h).status_code == 200
    assert client.post("/api/products", json={"name": "x"}, headers=h).status_code == 403
    assert client.post("/api/system/kill-switch", json={"engaged": True}, headers=h).status_code == 403


def test_demo_flow_end_to_end(client):
    r = client.post("/api/demo")
    assert r.status_code == 200 and r.json()["products"] == 9
    r = client.post("/api/tasks", json={"type": "ceo.evaluate_pipeline", "payload": {}})
    assert r.status_code == 200
    r = client.post("/api/tasks", json={"type": "trend.analyze", "payload": {}})
    prods = client.get("/api/products").json()
    assert all(p["is_demo"] for p in prods)
    assert all(p["opportunity_score"] is not None for p in prods)
    lamp = next(p for p in prods if "LED" in p["name"])
    assert lamp["compliance_status"] == "restricted"  # electronics + battery
    mask = next(p for p in prods if "sleep mask" in p["name"])
    assert mask["compliance_status"] == "needs_review"
    assert len({p["opportunity_score"] for p in prods}) > 1  # scores still discriminate
    trends = client.get("/api/trends").json()
    assert {t["keyword"] for t in trends} >= {"sourdough", "lighting"}
    sd = next(t for t in trends if t["keyword"] == "sourdough")
    assert sd["stage"] in ("emerging", "exploding")
    ov = client.get("/api/overview").json()
    assert ov["finance"]["contains_demo_data"] is True and ov["finance"]["revenue"] > 0
    assert client.get("/api/finance/forecast").json()["available"] is True
    assert len(client.get("/api/opportunities").json()) == 9
    agents = client.get("/api/agents").json()
    assert any(a["tasks_succeeded"] > 0 for a in agents)
    cleared = client.delete("/api/demo").json()
    assert cleared["products"] == 9
    assert client.get("/api/products").json() == []


def test_compliance_human_approval_and_launch_request(client):
    pid = client.post("/api/products", json={"name": "Linen tote bag", "category": "textiles", "wholesale_price": 30,
                                             "retail_price": 299, "shipping_cost": 10, "purchase_signal": 85, "search_interest": 80,
                                             "trend_velocity": 85, "competitor_count": 5, "competition_quality": 20,
                                             "differentiation_potential": 80, "customization_potential": 85, "marketing_potential": 80,
                                             "scalability": 80, "return_risk": 0.02, "sentiment": 0.6}).json()["id"]
    assert client.post(f"/api/products/{pid}/compliance-decision", json={"approve": True, "note": "looks fine"}).status_code == 400
    r = client.post(f"/api/products/{pid}/compliance-decision", json={"approve": True, "note": "docs verified", "checklist_confirmed": True})
    assert r.json()["compliance_status"] == "approved"
    client.post(f"/api/products/{pid}/evaluate")
    p = client.get(f"/api/products/{pid}").json()
    assert p["compliance_status"] == "approved"  # risk agent doesn't override a human decision
    client.post("/api/tasks", json={"type": "ceo.weekly_review", "payload": {}})
    approvals = client.get("/api/approvals?status=pending").json()
    assert any(a["action"] == "product.launch" for a in approvals), (p["opportunity_score"], p["score_confidence"])
    aid = approvals[0]["id"]
    assert client.post(f"/api/approvals/{aid}/decide", json={"approve": True, "note": "go"}).json()["status"] == "approved"
    assert client.post(f"/api/approvals/{aid}/decide", json={"approve": False}).status_code == 409
    actions = [a["action"] for a in client.get("/api/audit").json()]
    assert "compliance.human_decision" in actions and "approval.approved" in actions


def test_paid_experiment_needs_approval(client):
    e = client.post("/api/experiments", json={"name": "TikTok test", "hypothesis": "h", "budget_sek": 2000,
                                              "predicted": {"roas": 2.5}}).json()
    assert e["status"] == "pending_approval"
    assert client.post(f"/api/experiments/{e['id']}/start").status_code == 403
    a = next(a for a in client.get("/api/approvals").json() if a["action"] == "experiment.run_paid")
    assert a["level"] == 5
    client.post(f"/api/approvals/{a['id']}/decide", json={"approve": True})
    assert client.post(f"/api/experiments/{e['id']}/start").json()["status"] == "running"
    client.post(f"/api/experiments/{e['id']}/results", json={"orders": 40, "roas": 0.7, "contribution_margin": -500, "spend": 2000})
    ex = client.get("/api/experiments").json()[0]
    assert ex["decision"] == "abandon" and ex["status"] == "abandoned"
    assert len(client.get("/api/lessons").json()) == 1


def test_kill_switch_cancels_and_blocks(client):
    client.put("/api/watchlist", json={"keywords": ["x"]})
    client.post("/api/tasks", json={"type": "intel.scan_market", "payload": {}, "run": False})
    client.post("/api/system/kill-switch", json={"engaged": True, "reason": "test"})
    assert all(t["status"] == "cancelled" for t in client.get("/api/tasks").json())
    assert client.post("/api/tasks", json={"type": "trend.analyze", "payload": {}}).status_code == 409
    client.post("/api/system/kill-switch", json={"engaged": False})
    assert client.post("/api/tasks", json={"type": "trend.analyze", "payload": {}}).status_code == 200


def test_tools_and_integrations(client):
    r = client.post("/api/tools/economics", json={"retail_price_incl_vat": 399, "unit_cost": 80, "competitor_prices": [349, 399]})
    assert r.json()["economics"]["vat"] == round(399 - 399 / 1.25, 2)
    assert "standard" in r.json()["pricing"]["scenarios"]
    st = {i["id"]: i["state"] for i in client.get("/api/integrations").json()}
    assert st["youtube"] == "missing_credentials" and st["tiktok"] == "not_implemented"
    assert client.post("/api/tools/compliance", json={"name": "kids toy"}).json()["status"] == "restricted"


def test_admin_permission_change_is_audited(client):
    r = client.patch("/api/agents/content", json={"permission_level": 1})
    assert r.json()["permission_level"] == 1
    assert any(a["action"] == "agent.update" for a in client.get("/api/audit").json())
    assert client.patch("/api/agents/content", json={"permission_level": 9}).status_code == 422


def test_reevaluation_recomputes_children(client):
    pid = client.post("/api/products", json={"name": "Wool socks", "wholesale_price": 20, "retail_price": 149}).json()["id"]
    client.post(f"/api/products/{pid}/evaluate")
    client.patch(f"/api/products/{pid}", json={"retail_price": 199})
    client.post(f"/api/products/{pid}/evaluate")
    econ = [t for t in client.get("/api/tasks?limit=100").json() if t["type"] == "cfo.economics"]
    assert len(econ) == 2 and all(t["status"] == "succeeded" for t in econ)
    p = client.get(f"/api/products/{pid}").json()
    assert p["opportunities"][0]["economics"]["assumptions"]["retail_price_incl_vat"] == 199


def test_company_identity(client):
    st = client.get("/api/auth/status").json()
    assert st["company_name"] == "G-SUS & Demonkoncernen AB" and st["platform_name"] == "Rocky"
    assert client.get("/api/system/status").json()["company_name"] == "G-SUS & Demonkoncernen AB"
    sid = client.post("/api/suppliers", json={"name": "Nordic Bags AB", "country": "SE", "eu_based": True}).json()["id"]
    client.post("/api/tasks", json={"type": "supplier.inquiry_draft", "payload": {"supplier_id": sid}})
    draft = next(t for t in client.get("/api/tasks").json() if t["type"] == "supplier.inquiry_draft")
    body = client.get(f"/api/tasks/{draft['id']}").json()["result"]["draft"]
    assert body.rstrip().endswith("G-SUS & Demonkoncernen AB")
