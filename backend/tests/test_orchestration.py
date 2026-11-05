import json

import httpx
import pytest

from app.agents.base import AgentOutput, BaseAgent
from app.agents.catalog import build_orchestrator
from app.agents.orchestrator import GovernanceError
from app.ai import llm
from app.governance import core as gov
from app.integrations import registry
from app.integrations.connectors import YouTubeConnector
from app.models import Agent, Approval, Opportunity, Product, Task, TrendObservation
from app.security import permissions


def _db(fresh_db):
    return fresh_db.SessionLocal()


def test_full_product_pipeline(fresh_db):
    orch = build_orchestrator()
    db = _db(fresh_db)
    p = Product(name="Sourdough starter kit", category="kitchen", wholesale_price=85, shipping_cost=30, delivery_days=10,
                retail_price=499, competitor_prices=[349, 449, 499], purchase_signal=55, search_interest=60, tags=["hobby"])
    db.add(p)
    db.flush()
    orch.submit(db, "ceo.evaluate_product", {"product_id": p.id}, priority=1)
    db.commit()
    orch.drain()
    db.expire_all()
    p = db.get(Product, p.id)
    statuses = {t.type: t.status for t in db.query(Task).all()}
    assert statuses == {"ceo.evaluate_product": "succeeded", "risk.assess": "succeeded", "cfo.economics": "succeeded",
                        "product.score": "succeeded", "opportunity.generate": "succeeded"}, statuses
    assert p.opportunity_score is not None and p.net_margin is not None
    assert p.compliance_status in ("needs_review", "restricted", "blocked")  # never auto-approved
    opp = db.query(Opportunity).one()
    assert len(opp.transformations) >= 10 and len(opp.business_models) == 3
    assert opp.pricing["scenarios"]["standard"]["price"] > 0
    db.close()


def test_missing_data_blocks_not_fabricates(fresh_db):
    orch = build_orchestrator()
    db = _db(fresh_db)
    p = Product(name="Mystery widget")
    db.add(p)
    db.flush()
    t = orch.submit(db, "cfo.economics", {"product_id": p.id})
    db.commit()
    orch.drain()
    db.expire_all()
    t = db.get(Task, t.id)
    assert t.status == "blocked" and "wholesale price" in t.error
    db.close()


def test_llm_agents_block_without_provider(fresh_db):
    orch = build_orchestrator()
    db = _db(fresh_db)
    p = Product(name="Desk lamp")
    db.add(p)
    db.flush()
    t = orch.submit(db, "brand.generate", {"product_id": p.id})
    db.commit()
    orch.drain()
    db.expire_all()
    assert db.get(Task, t.id).status == "blocked"
    db.close()


class FakeProvider:
    name = "fake"

    def complete(self, *, system, prompt, tier="standard", schema=None, max_tokens=16000):
        data = {"concepts": [{"name": "Surdeg & Co", "positioning": "p", "usp": "u", "voice": "v", "palette": ["#111"],
                              "typography": "t", "slogans": ["s"], "personas": ["x"], "story": "st", "packaging": "pk"}]}
        return llm.LLMResult(json.dumps(data), data, "fake-model", 1000, 500, 0.01)


def test_llm_agent_with_provider_records_tokens(fresh_db):
    llm.set_provider(FakeProvider())
    orch = build_orchestrator()
    db = _db(fresh_db)
    p = Product(name="Sourdough kit")
    db.add(p)
    db.flush()
    t = orch.submit(db, "brand.generate", {"product_id": p.id})
    db.commit()
    orch.drain()
    db.expire_all()
    t = db.get(Task, t.id)
    assert t.status == "succeeded", t.error
    assert t.tokens_used == 1500 and t.cost_usd == 0.01
    assert t.result["concepts"][0]["trademark_check"] == "pending"
    assert db.get(Agent, "brand_studio").tokens_today == 1500
    db.close()


def test_token_budget_enforced(fresh_db):
    llm.set_provider(FakeProvider())
    orch = build_orchestrator()
    db = _db(fresh_db)
    a = db.get(Agent, "brand_studio")
    a.daily_token_budget = 0
    p = Product(name="x")
    db.add(p)
    db.flush()
    t = orch.submit(db, "brand.generate", {"product_id": p.id})
    db.commit()
    orch.drain()
    db.expire_all()
    t = db.get(Task, t.id)
    assert t.status == "blocked" and "budget" in t.error
    db.close()


def test_dedupe_depth_and_kill_switch(fresh_db):
    orch = build_orchestrator()
    db = _db(fresh_db)
    t1 = orch.submit(db, "product.score", {"product_id": 1})
    t2 = orch.submit(db, "product.score", {"product_id": 1})
    assert t1.id == t2.id
    t3 = orch.submit(db, "product.score", {"product_id": 1}, force=True)
    assert t3.id != t1.id
    parent = t1
    for _ in range(3):
        parent = orch.submit(db, "product.score", {"product_id": parent.id + 1000}, parent=parent)
    with pytest.raises(GovernanceError, match="depth"):
        orch.submit(db, "product.score", {"product_id": 99999}, parent=parent)
    with pytest.raises(GovernanceError, match="circular"):
        orch.submit(db, "product.score", {"product_id": 1}, parent=t1)
    gov.set_kill_switch(db, True, "test")
    with pytest.raises(GovernanceError, match="kill switch"):
        orch.submit(db, "product.score", {"product_id": 2})
    db.close()


def test_suspended_agent_blocks(fresh_db):
    orch = build_orchestrator()
    db = _db(fresh_db)
    db.get(Agent, "product_analyst").status = "suspended"
    p = Product(name="x")
    db.add(p)
    db.flush()
    t = orch.submit(db, "product.score", {"product_id": p.id})
    db.commit()
    orch.drain()
    db.expire_all()
    assert db.get(Task, t.id).status == "blocked"
    db.close()


def test_failures_are_retried_then_failed(fresh_db):
    orch = build_orchestrator()

    class Flaky(BaseAgent):
        id, name, division, task_types = "flaky", "Flaky", "test", ("test.flaky",)
        calls = 0

        def handle(self, ctx, task):
            Flaky.calls += 1
            raise RuntimeError("boom")

    if "flaky" not in orch.agents:
        orch.register(Flaky())
    db = _db(fresh_db)
    orch.sync_agents(db)
    t = orch.submit(db, "test.flaky", {})
    db.commit()
    Flaky.calls = 0
    orch.drain()
    db.expire_all()
    t = db.get(Task, t.id)
    assert t.status == "failed" and t.attempts == 3 and Flaky.calls == 3
    db.close()


def test_permissions_and_approval_levels():
    assert permissions.needs_approval("ads.launch_campaign")
    assert permissions.needs_approval("unknown.action")  # unknown => most sensitive
    assert not permissions.needs_approval("product.score")
    with pytest.raises(permissions.PermissionDenied):
        permissions.check(1, "content.draft")


def test_supplier_inquiry_requires_approval(fresh_db):
    from app.models import Supplier

    orch = build_orchestrator()
    db = _db(fresh_db)
    s = Supplier(name="Acme")
    db.add(s)
    db.flush()
    t = orch.submit(db, "supplier.inquiry_draft", {"supplier_id": s.id})
    db.commit()
    orch.drain()
    db.expire_all()
    assert db.get(Task, t.id).status == "succeeded"
    a = db.query(Approval).one()
    assert a.action == "supplier.send_inquiry" and a.status == "pending" and a.level == 4
    db.close()


def test_research_connector_with_mock_transport(fresh_db):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/search"):
            return httpx.Response(200, json={"items": [{"id": {"videoId": "a"}}, {"id": {"videoId": "b"}}]})
        return httpx.Response(200, json={"items": [{"statistics": {"viewCount": "1000", "commentCount": "10"}},
                                                   {"statistics": {"viewCount": "500", "commentCount": "5"}}]})

    yt = YouTubeConnector(client=httpx.Client(transport=httpx.MockTransport(handler)), env={"YOUTUBE_API_KEY": "k"})
    registry.register(yt)
    orch = build_orchestrator()
    db = _db(fresh_db)
    gov.set_state(db, "watchlist", {"keywords": ["sourdough"]})
    orch.submit(db, "intel.scan_market", {})
    db.commit()
    orch.drain()
    db.expire_all()
    obs = db.query(TrendObservation).all()
    views = [o.value for o in obs if o.metric == "recent_video_views"]
    assert views == [1500.0]
    types = {t.type: t.status for t in db.query(Task).all()}
    assert types["research.collect"] == "succeeded" and types["trend.analyze"] == "succeeded"
    db.close()


def test_unconfigured_connector_reports_missing():
    yt = YouTubeConnector(env={})
    st = yt.status()
    assert st["state"] == "missing_credentials" and st["missing_env"] == ["YOUTUBE_API_KEY"]
    assert registry.get("temu").status()["state"] == "not_implemented"
