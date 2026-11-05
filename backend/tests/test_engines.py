from datetime import datetime, timedelta, timezone

import pytest

from app.engines import business_models, compliance, economics, experiments, finance, pricing, scoring, transformation, trends


def test_weights_sum_to_one():
    assert abs(sum(scoring.WEIGHTS.values()) - 1) < 1e-9


def test_engagement_only_demand_is_capped():
    viral = scoring.compute_score(scoring.ScoreInput(engagement_signal=100))
    buyers = scoring.compute_score(scoring.ScoreInput(purchase_signal=100, search_interest=100))
    assert viral.components["demand"]["score"] <= scoring.ENGAGEMENT_ONLY_DEMAND_CAP
    assert buyers.components["demand"]["score"] > 90
    assert any("engagement_only" in f for f in viral.flags)


def test_missing_data_lowers_confidence_not_score_inflation():
    empty = scoring.compute_score(scoring.ScoreInput())
    assert empty.confidence < 0.1
    full = scoring.compute_score(scoring.ScoreInput(purchase_signal=70, search_interest=60, trend_velocity=70, net_margin=0.25,
                                                    competitor_count=20, competition_quality=40, differentiation_potential=60,
                                                    supplier_reliability=80, marketing_potential=70, scalability=60, return_risk=0.05,
                                                    compliance_status="approved", sentiment=0.3))
    assert full.confidence > 0.9 and full.score > empty.score


def test_compliance_block_caps_score():
    r = scoring.compute_score(scoring.ScoreInput(purchase_signal=100, net_margin=0.5, compliance_status="blocked"))
    assert r.score <= 25


def test_adjustments_are_bounded():
    r = scoring.compute_score(scoring.ScoreInput(), [{"delta": 500, "reason": "x"}])
    assert r.components["_adjustments"]["items"][0]["delta"] == 30


def test_economics_vat_and_contribution():
    e = economics.compute(economics.CostInputs(retail_price_incl_vat=250, unit_cost=50, return_rate=0, payment_fee_pct=0, payment_fee_fixed=0))
    assert e.net_revenue == 200 and e.vat == 50
    assert e.contribution_before_ads == 150
    assert e.break_even_roas == round(250 / 150, 2)


def test_returns_reduce_contribution():
    base = dict(retail_price_incl_vat=500, unit_cost=100, return_cost_per_return=50)
    a = economics.compute(economics.CostInputs(**base, return_rate=0.0))
    b = economics.compute(economics.CostInputs(**base, return_rate=0.2))
    assert b.contribution_before_ads < a.contribution_before_ads
    assert b.expected_return_cost > 0


def test_pricing_scenarios_and_omnibus_rule():
    c = economics.CostInputs(retail_price_incl_vat=1, unit_cost=60, inbound_shipping=20, packaging=8)
    sc = pricing.scenarios(c, [399, 449, 499])
    assert sc["scenarios"]["margin_floor"]["contribution_margin_pct"] >= 0.25
    assert sc["scenarios"]["standard"]["price"] == 449  # market price when above the floor
    assert sc["scenarios"]["standard"]["price"] >= sc["scenarios"]["margin_floor"]["price"]
    assert sc["scenarios"]["promotional"]["price"] is None  # no history -> no reference price
    now = datetime.now(timezone.utc)
    hist = [(now - timedelta(days=40), 199.0), (now - timedelta(days=10), 349.0), (now - timedelta(days=2), 399.0)]
    sc2 = pricing.scenarios(c, [399], price_history=hist)
    assert sc2["scenarios"]["promotional"]["reference_price"] == 349.0  # 40-day-old 199 is ignored


def test_psychological_round():
    assert pricing.psychological_round(231) == 249
    assert pricing.psychological_round(87) == 89


def test_trend_classification():
    now = datetime.now(timezone.utc)
    grow = [trends.Obs(p, 100 * (1.4 ** w), now - timedelta(weeks=10 - w)) for p in ("a", "b") for w in range(10)]
    a = trends.analyze("x", grow)
    assert a.stage == "exploding" and a.cross_platform_growth == 2 and a.velocity_score > 80
    decl = [trends.Obs("a", 100 * (0.85 ** w), now - timedelta(weeks=10 - w)) for w in range(10)]
    assert trends.analyze("y", decl).stage == "declining"
    assert trends.analyze("z", decl[:2]).stage == "insufficient_data"
    flat = [trends.Obs("a", 100 + (w % 2), now - timedelta(weeks=30 - w)) for w in range(30)]
    assert trends.analyze("f", flat).stage == "evergreen"


def test_seasonal_detection():
    now = datetime.now(timezone.utc)
    obs = []
    for d in range(0, 430, 7):
        at = now - timedelta(days=430 - d)
        days_ago = 430 - d
        peak = days_ago < 28 or 365 <= days_ago <= 393
        obs.append(trends.Obs("a", 300 if peak else 100, at))
    assert trends.analyze("xmas", obs).stage == "seasonal"


def test_compliance_flags():
    r = compliance.assess("Bluetooth speaker", "Rechargeable lithium battery")
    assert r.status == "restricted" and {"electronics", "batteries"} <= set(r.categories) and not r.blockers
    r2 = compliance.assess("Replica designer bag")
    assert any("replica" in b for b in r2.blockers)
    r3 = compliance.assess("Herbal tea", marketing_copy="This tea cures headaches")
    assert any("cure" in b for b in r3.blockers)
    r4 = compliance.assess("Wooden bookend")
    assert r4.status == "needs_review"  # never auto-approved
    assert compliance.assess("Linen sleep mask").status == "needs_review"  # 'mask' alone is not PPE
    assert compliance.assess("Replica LED lamp").status == "blocked"  # hard blocker beats restriction


def test_business_models_not_default_dropshipping():
    t = business_models.ProductTraits(delivery_days=18, customization_potential=85, giftable=True)
    res = business_models.evaluate(t)
    assert len(res["recommended"]) == 3 and len(res["all"]) == 25
    assert "dropshipping" not in [m["model"] for m in res["recommended"]]
    names = [m["model"] for m in res["recommended"]]
    assert any(n in names for n in ("print_on_demand", "custom_gift_business", "digital_downloads"))


def test_transformations_at_least_ten():
    titles = [i["title"] for i in transformation.generate("Sourdough starter kit")]
    assert "Sourdough starter kit" in titles and not any("kit starter kit" in t for t in titles)
    ideas = transformation.generate("Yoga mat", "fitness", ["too slippery"])
    assert len(ideas) >= 10
    assert {i["family"] for i in ideas} >= {"personalization", "improvement", "bundling", "digital", "service", "content", "private_label"}
    assert all(i["epistemic"] == "hypothesis" for i in ideas)


def test_experiment_decisions():
    m = {"min_roas": 2, "min_contribution_margin": 0, "min_orders": 20, "kill_roas": 1}
    assert experiments.decide(m, {"orders": 5, "roas": 1.5, "spend": 100})["decision"] == "continue"
    assert experiments.decide(m, {"orders": 30, "roas": 2.5, "contribution_margin": 100})["decision"] == "scale"
    assert experiments.decide(m, {"orders": 30, "roas": 0.8, "contribution_margin": -100})["decision"] == "abandon"
    assert experiments.decide(m, {"orders": 30, "roas": 1.5, "contribution_margin": -1})["decision"] == "iterate"
    ab = experiments.two_proportion_z(100, 5000, 140, 5000)
    assert ab["significant_95"]


def test_finance_forecast_requires_data():
    assert finance.forecast([])["available"] is False

    class E:  # minimal ledger row
        def __init__(s, k, a, d):
            s.kind, s.amount, s.occurred_at, s.product_id, s.store_id, s.channel = k, a, d, 1, None, "x"

    now = datetime.now(timezone.utc)
    rows = [E("revenue", 100 + i, now - timedelta(days=30 - i)) for i in range(30)] + [E("ad_spend", 20, now - timedelta(days=i)) for i in range(30)]
    s = finance.summarize(rows)
    assert s["revenue"] > 0 and s["roas"] is not None
    f = finance.forecast(finance.daily_series(rows))
    assert f["available"] and f["horizons"]["30"]["revenue"]["expected"] > 0


def test_capital_allocation_keeps_reserve():
    r = finance.capital_allocation(100_000, [{"product_id": 1, "name": "a", "contribution_margin": 5000, "roas": 3}])
    assert r["allocation"]["cash_reserve"] == 25_000 and r["requires_approval"]
    assert abs(sum(r["allocation"].values()) - 100_000) < 1


def test_supplier_reliability_unknown():
    class S:
        rating = years_active = response_rate = dispute_rate = avg_delivery_days = None
        has_product_documentation = eu_based = offers_private_label = False

    assert scoring.supplier_reliability_score(S())[0] is None
