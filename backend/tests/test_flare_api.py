"""Rocky Flare + Field Ops end-to-end through the API and the orchestrator (acceptance criteria 1–16)."""
import json

import pytest

from app.ai import llm


@pytest.fixture()
def product(client):
    r = client.post("/api/products", json={
        "name": "Waterproof roll-top handlebar bag for e-scooter", "category": "mobility", "tags": ["commuter", "winter", "giftable"],
        "description": "Roll-top bag with reflective piping that straps to the scooter stem.", "wholesale_price": 95, "shipping_cost": 30,
        "retail_price": 449, "competitor_prices": [299, 399, 449, 499], "engagement_signal": 70, "search_interest": 55, "competitor_count": 60,
        "marketing_potential": 75})
    pid = r.json()["id"]
    client.post(f"/api/products/{pid}/evaluate")
    return pid


def run(client, type_, **payload):
    r = client.post("/api/flare/run", json={"type": type_, "payload": payload})
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["status"] == "succeeded", t
    return t["result"]


def test_1_2_personas_editable_versioned_and_distinct(client):
    ps = client.get("/api/flare/personas").json()
    ids = {p["id"] for p in ps}
    assert {"the_architect", "the_accountant", "the_scout", "devils_advocate", "the_visionary", "the_operator"} <= ids
    assert len([p for p in ps if p["division"] == "field_ops"]) >= 20
    assert len({json.dumps(p["evaluation_lens"], sort_keys=True) for p in ps}) >= 10  # genuinely different lenses
    r = client.patch("/api/flare/personas/the_accountant", json={"novelty_appetite": 0.9, "personality": "Still cynical, now curious."})
    assert r.status_code == 200 and r.json()["version"] == 2
    detail = client.get("/api/flare/personas/the_accountant").json()
    assert detail["versions"][0]["version"] == 2 and detail["versions"][0]["changed_by"] == "admin@example.com"
    assert client.patch("/api/flare/personas/the_accountant", json={"genre_affinities": {"made_up": 1}}).status_code == 422
    assert client.patch("/api/flare/personas/the_accountant", json={"permission_level": 5}).json()["metrics"]["permission_level"] == 1  # ignored
    assert client.post("/api/flare/personas/the_accountant/reset").json()["novelty_appetite"] == 0.15
    assert any(a["action"] == "persona.update" for a in client.get("/api/audit").json())


def test_3_4_genres_compared_and_hybrids_fused(client, product):
    g = client.get(f"/api/flare/products/{product}/genres").json()
    assert len(g["matches"]) >= 10 and len(g["directions"]) >= 5
    assert {"audience_relevance", "competitive_differentiation", "visual_recognition", "brand_scalability", "marketing_potential",
            "production_cost", "expected_positioning"} <= set(g["directions"][0]["scores"])
    f = client.post("/api/flare/genres/fuse", json={"components": ["nordic_survival", "botanical_illustration", "biblical_heritage"],
                                                    "name": "Eden Fieldworks"}).json()
    assert f["novel"] and f["palette"] and any(x["code"] == "religious_imagery" for x in f["originality_flags"])
    assert any(d["id"].startswith("nordic_survival+botanical") for d in client.get("/api/flare/genres").json()["discovered"])


def test_5_mutation_engine_and_graph(client, product):
    res = run(client, "flare.mutate", product_id=product)
    assert len(res["nodes"]) >= 15 and res["edges"]
    graph = client.get(f"/api/flare/graphs/mutation:{product}").json()
    assert len(graph["nodes"]) == len(res["nodes"]) and graph["edges"]
    statuses = {n["status"] for n in res["nodes"]}
    assert {"existing_product", "proposed_modification", "original_concept"} <= statuses


def test_6_think_sideways_and_challenges(client, product):
    res = run(client, "flare.sideways", product_id=product, question="Give this product three radically different identities")
    assert res["mode"] == "identities" and len(res["identities"]) == 3
    assert len([i for i in res["items"] if i["category"] == "alternative customer group"]) == 5
    assert client.get(f"/api/flare/graphs/sideways:{product}").json()["nodes"]
    ch = run(client, "flare.sideways", challenge_id="winter_commute")
    assert ch["ecosystems"] and ch["ecosystems"][0]["label"]
    fusion = run(client, "flare.sideways", challenge_id="manuscript_edc")
    assert "illuminated_manuscript" in fusion["hybrid"]["components"]


def test_7_8_9_competition_panel_compare_and_no_forced_consensus(client, product):
    sid = run(client, "flare.competition", product_id=product)["session_id"]
    s = client.get(f"/api/flare/sessions/{sid}").json()
    assert s["status"] == "concluded" and len(s["concepts"]) == 5
    authors = {c["author_persona"] for c in s["concepts"]}
    assert len(authors) == 5
    ranking = s["decision"]["ranking"]
    assert len(ranking) == 5 and all("stdev" in r and "consensus" in r for r in ranking)
    judged = [t for t in s["turns"] if t["seat"].startswith("judge:")]
    assert len(judged) == 5 * 5  # every judge scored every concept independently
    cmp = client.post("/api/flare/concepts/compare", json={"ids": [c["id"] for c in s["concepts"][:3]]}).json()
    assert len(cmp) == 3 and all(c["panel_mean"] is not None for c in cmp)
    panel = run(client, "flare.panel", concept_ids=[c["id"] for c in s["concepts"][:2]], product_id=product)
    ps = client.get(f"/api/flare/sessions/{panel['session_id']}").json()
    assert {t["persona_id"] for t in ps["turns"]} == {"creative_director", "marketing_strategist", "audience_analyst", "commercial_analyst", "devils_advocate"}
    assert all(t["message"] for t in ps["turns"])


def test_10_assets_versioned_and_approval(client, product):
    sid = run(client, "flare.competition", product_id=product)["session_id"]
    cid = client.get(f"/api/flare/sessions/{sid}").json()["concepts"][0]["id"]
    a1 = run(client, "flare.assets", concept_id=cid, kinds=["wordmark", "sigil", "palette_board", "photography_brief"])
    a2 = run(client, "flare.assets", concept_id=cid, kinds=["wordmark"])
    assets = client.get(f"/api/flare/assets?concept_id={cid}&kind=wordmark&latest_only=false").json()
    assert len(assets) == 2 and {a["version"] for a in assets} == {1, 2}
    assert assets[0]["content"].startswith("<svg") and "<script" not in assets[0]["content"]
    versions = client.get(f"/api/flare/assets/{a2['asset_ids'][0]}/versions").json()
    assert [v["version"] for v in versions] == [1, 2] and versions[1]["parent_id"] == versions[0]["id"]
    assert client.post(f"/api/flare/assets/{a1['asset_ids'][0]}/status", json={"status": "approved"}).json()["status"] == "approved"
    assert client.get("/api/flare/assets?q=sigil").json()


def test_11_12_campaigns_performance_learning(client, product):
    sid = run(client, "flare.competition", product_id=product)["session_id"]
    concept = client.get(f"/api/flare/sessions/{sid}").json()["concepts"][0]
    res = run(client, "flare.campaign_matrix", product_id=product, concept_id=concept["id"])
    ids = res["campaign_ids"]
    assert len(ids) >= 6 and res["cells"][0]["budget_recommendation_sek"]
    camps = {c["id"]: c for c in client.get("/api/flare/campaigns").json()}
    good, viral = ids[0], next(i for i in ids if camps[i]["identity"] != camps[ids[0]]["identity"])
    for i in range(4):
        client.post(f"/api/flare/campaigns/{good}/performance", json=[{"period_start": f"2026-10-0{i + 1}T00:00:00Z", "impressions": 10000,
                    "clicks": 300, "engagements": 50, "spend": 1000, "orders": 12, "revenue": 5388, "contribution": 2150}])
        client.post(f"/api/flare/campaigns/{viral}/performance", json=[{"period_start": f"2026-10-0{i + 1}T00:00:00Z", "impressions": 90000,
                    "clicks": 2000, "engagements": 8000, "spend": 1000, "orders": 2, "revenue": 898, "contribution": 360}])
    an = client.get("/api/flare/campaigns/analysis").json()
    assert an["campaigns"][0]["campaign_id"] == good and an["insight"]
    dna = client.get("/api/flare/style-dna").json()
    assert dna["identity"][camps[good]["identity"]] > dna["identity"][camps[viral]["identity"]]
    # persona memory: panel scores on that concept became calibration points
    mem = [m for p in ("creative_director", "devils_advocate") for m in client.get(f"/api/flare/personas/{p}").json()["memory"]]
    assert any(m["kind"] == "calibration" for m in mem) or not concept.get("panel_scores")
    assert client.post(f"/api/flare/campaigns/{good}/request-launch").json()["level"] == 5


def test_13_brand_portfolio_overlap_and_launch_gate(client, product, approver):
    sid = run(client, "flare.competition", product_id=product)["session_id"]
    concepts = client.get(f"/api/flare/sessions/{sid}").json()["concepts"]
    clean = [c for c in concepts if not c["originality"]["requires_revision"]]
    a, b = clean[0], clean[1]
    assert client.post("/api/flare/brands", json={"concept_id": a["id"]}).status_code == 409  # not approved yet
    for c in (a, b):
        assert client.post(f"/api/flare/concepts/{c['id']}/status", json={"status": "approved"}).status_code == 200
    brand = client.post("/api/flare/brands", json={"concept_id": a["id"]}).json()
    dup = client.post("/api/flare/brands", json={"concept_id": b["id"]})
    if dup.status_code == 409:  # same product/segments → recommended to extend the existing brand
        assert "overlaps" in dup.json()["detail"]
        dup = client.post("/api/flare/brands", json={"concept_id": b["id"], "force": True, "reason": "separate premium audience test"})
    assert dup.status_code == 200
    data = client.get("/api/flare/brands").json()
    assert len(data["brands"]) == 2 and all("operational_complexity" in m for m in data["brands"])
    assert client.post(f"/api/flare/brands/{brand['id']}/request-launch").status_code == 409  # trademark not cleared
    assert client.patch(f"/api/flare/brands/{brand['id']}", json={"trademark_status": "clear"}).status_code == 400  # evidence required
    client.patch(f"/api/flare/brands/{brand['id']}", json={"trademark_status": "clear", "trademark_note": "EUIPO+PRV search 2026-11-05: no conflicts"})
    appr = client.post(f"/api/flare/brands/{brand['id']}/request-launch").json()
    assert client.post(f"/api/flare/brands/{brand['id']}/activate").status_code == 403
    assert client.post(f"/api/approvals/{appr['id']}/decide", json={"approve": True}).status_code == 409  # not one's own launch
    assert approver.post(f"/api/approvals/{appr['id']}/decide", json={"approve": True}).status_code == 200
    assert client.post(f"/api/flare/brands/{brand['id']}/activate").json()["status"] == "live"


def test_discussion_log_disagreement_and_decision(client, product):
    sid = run(client, "flare.discussion", product_id=product)["session_id"]
    s = client.get(f"/api/flare/sessions/{sid}").json()
    seats = [t["seat"] for t in s["turns"]]
    assert seats == ["scout", "visionary", "architect", "accountant", "devils_advocate", "creative_director", "ceo"]
    da = next(t for t in s["turns"] if t["seat"] == "devils_advocate")
    assert da["stance"] in ("oppose", "caution") and "engagement" in da["message"]
    assert s["decision"]["outcome"] in ("iterate", "approve_validation_experiment", "reject") and s["decision"]["dissent"]
    assert len(s["concepts"]) == 3


def test_council_outputs(client, product):
    sid = run(client, "flare.council", product_id=product)["session_id"]
    d = client.get(f"/api/flare/sessions/{sid}").json()["decision"]
    assert set(d["council"]) == {"best_functional_design", "best_creative_direction", "best_brand_opportunity", "best_monetization_strategy",
                                 "main_technical_risks", "main_regulatory_risks", "recommended_next_experiment"}
    assert d["council"]["recommended_next_experiment"]["requires_approval"] is True
    assert len({t for t in client.get(f"/api/flare/sessions/{sid}").json()["members"]}) == 8


def test_revision_creates_version(client, product):
    r = client.post("/api/flare/concepts", json={"product_id": product, "name": "EcoPro Smart Hub", "primary_genre": "urban_commuter",
                                                 "secondary_genre": "secret_archive", "tagline": "Elevate your commute. Unlock the ultimate ride.",
                                                 "audience": "everyone", "story": "Cutting-edge."}).json()
    assert r["status"] == "needs_revision"
    assert client.post(f"/api/flare/concepts/{r['id']}/status", json={"status": "approved"}).status_code == 409
    res = run(client, "flare.revise", concept_id=r["id"])
    new = client.get(f"/api/flare/concepts/{res['concept_id']}").json()
    assert new["version"] == 2 and new["parent_id"] == r["id"] and new["name"] != "EcoPro Smart Hub"
    assert [v["version"] for v in new["versions"]] == [1, 2]
    assert not res["requires_revision"]


def test_14_financial_and_compliance_controls_still_hold(client, product):
    # LLM-backed requests still block without a provider; agents can't launch campaigns; kill switch halts Flare too.
    llm.set_provider(None)
    client.post("/api/system/kill-switch", json={"engaged": True, "reason": "test"})
    assert client.post("/api/flare/run", json={"type": "flare.mutate", "payload": {"product_id": product}}).status_code == 409
    client.post("/api/system/kill-switch", json={"engaged": False})
    client.patch("/api/agents/flare_engine", json={"status": "suspended"})
    t = client.post("/api/flare/run", json={"type": "flare.mutate", "payload": {"product_id": product}}).json()
    assert t["status"] == "blocked"
    client.patch("/api/agents/flare_engine", json={"status": "active"})
    bad = client.post("/api/field/compatibility", json={"product_id": product, "target": "Xiaomi 4 Pro", "status": "verified"})
    assert bad.status_code == 400
    ok = client.post("/api/field/compatibility", json={"product_id": product, "target": "Xiaomi 4 Pro", "status": "verified",
                                                       "evidence": "Fitted and ride-tested 2026-11-04, stem Ø35 mm, 20 km loop"})
    assert ok.json()["verified_by"] == "admin@example.com"


def test_15_field_ops_endpoints(client, product):
    ov = client.get("/api/field/overview").json()
    assert ov["subsections"]["escooter"] >= 1 and ov["pillars"]["C_e_mobility"]["products"] >= 1
    assert client.get("/api/field/products?sub=escooter").json()[0]["mobility_class"] == "ordinary_accessory"
    assert len(client.get("/api/field/segments").json()) == 16
    assert len(client.get("/api/field/ecosystems").json()["ecosystems"]) == 3
    arch = client.get("/api/field/archive").json()
    assert arch["preset_trademark_checks"]["Black Mirror EDC"]["status"] == "known_conflict"
    fa = run(client, "flare.field_analysis", product_id=product)
    assert "C_e_mobility" in fa["pillars"] and fa["personalization"]["validation"]["valid"]
    inn = client.get(f"/api/field/innovation/{product}").json()
    assert len(inn["innovation"]) >= 13
    for m in ("subscription_intel", "local_opportunity", "b2b_opportunity"):
        assert run(client, f"flare.commercial.{m}", product_id=product)["opportunities"]


class FakeLLM:
    name = "fake"

    def __init__(self):
        self.calls = []

    def complete(self, *, system, prompt, tier="standard", schema=None, max_tokens=16000):
        self.calls.append(system)
        if schema and "ideas" in schema.get("properties", {}):
            data = {"ideas": [{"title": "Night-walk kit for dog owners", "description": "d", "bridge": "lighting", "how_to_validate": "search data"}] * 5}
        else:
            data = {"name": "Vinterarkiv", "tagline": "Built for the dark half of the year.", "audience": "e-scooter commuters in Nordic cities",
                    "usp": "Proposed: roll-top seal with reflective piping, verified by IPX test before any claim.",
                    "story": "Vinterarkiv treats the commute as a field file: tactical construction, archive-style labels and reflective details for "
                             "riders who commute through Stockholm winters in darkness."}
        return llm.LLMResult(json.dumps(data), data, "fake-model", 400, 200, 0.002)


def test_llm_persona_voice_and_sideways_enrichment(client, product):
    fake = FakeLLM()
    llm.set_provider(fake)
    try:
        res = run(client, "flare.sideways", product_id=product, question="What else could we do with this product?", use_llm=True)
        assert len(res["llm"]["ideas"]) == 5 and res["llm"]["method"] == "llm"
        sid = run(client, "flare.competition", product_id=product, competitors=["creative_director"], judges=["devils_advocate"])["session_id"]
        # rerun competitor with the LLM voice explicitly through the orchestrator
        from app.agents.catalog import build_orchestrator
        from app.db import SessionLocal
        orch = build_orchestrator()
        db = SessionLocal()
        orch.submit(db, "persona.concept", {"session_id": sid, "persona_id": "the_visionary", "product_id": product, "use_llm": True},
                        agent_id="transformation_lab", force=True)
        db.commit()
        orch.drain()
        db.close()
        names = [c["name"] for c in client.get(f"/api/flare/concepts?session_id={sid}").json()]
        assert "Vinterarkiv" in names
        assert any("The Visionary" in s for s in fake.calls)  # persona-specific system prompt reached the provider
    finally:
        llm.set_provider(None)


def test_demo_clear_removes_flare_dependents(client):
    client.post("/api/demo")
    pid = client.get("/api/products?q=stem bag").json()[0]["id"]
    run(client, "flare.competition", product_id=pid, competitors=["creative_director", "the_visionary"], judges=["devils_advocate"])
    client.post("/api/field/compatibility", json={"product_id": pid, "target": "Handlebar Ø22.2 mm", "target_kind": "mount_standard"})
    r = client.delete("/api/demo")
    assert r.status_code == 200 and r.json()["concepts"] >= 2 and r.json()["sessions"] == 1
    assert client.get("/api/products").json() == []
