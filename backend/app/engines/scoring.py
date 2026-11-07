"""Opportunity scoring (spec section 4).

Design rules
* Unknown inputs are NOT replaced by optimistic defaults. A missing signal scores a
  neutral 50 but reduces confidence, so thin data cannot produce a confident score.
* Viral attention is not purchasing demand: engagement alone can contribute at most
  a capped share of the demand component.
* CFO/Risk agents may apply explicit, audited adjustments (``adjustments``).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

WEIGHTS: dict[str, float] = {
    "demand": 0.20,
    "trend_momentum": 0.15,
    "profit_potential": 0.20,
    "competition_opportunity": 0.10,
    "differentiation": 0.10,
    "supplier_reliability": 0.10,
    "marketing_potential": 0.05,
    "scalability": 0.05,
    "risk_adjusted_viability": 0.05,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9

NEUTRAL = 50.0
ENGAGEMENT_ONLY_DEMAND_CAP = 45.0  # attention without purchase evidence never scores as strong demand


@dataclass
class ScoreInput:
    purchase_signal: float | None = None  # 0-100: sales rank, orders, reviews/time
    engagement_signal: float | None = None  # 0-100: views/likes/shares
    search_interest: float | None = None  # 0-100
    trend_velocity: float | None = None  # 0-100 (from trend engine)
    net_margin: float | None = None  # fraction, e.g. 0.22
    competitor_count: int | None = None
    competition_quality: float | None = None  # 0-100 (high = strong incumbents)
    differentiation_potential: float | None = None
    customization_potential: float | None = None
    supplier_reliability: float | None = None  # 0-100
    marketing_potential: float | None = None
    scalability: float | None = None
    return_risk: float | None = None  # 0-1
    compliance_status: str = "unreviewed"
    sentiment: float | None = None  # -1..1
    review_complaint_rate: float | None = None  # 0..1 (complaints = improvement room)


@dataclass
class ScoreResult:
    score: float
    confidence: float
    components: dict[str, dict[str, Any]] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"score": self.score, "confidence": self.confidence, "components": self.components, "flags": self.flags}


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _avg(vals: list[float | None]) -> float | None:
    known = [v for v in vals if v is not None]
    return sum(known) / len(known) if known else None


def score_demand(i: ScoreInput, flags: list[str]) -> tuple[float, float]:
    """Returns (score, data_coverage 0..1)."""
    if i.purchase_signal is not None:
        s = 0.7 * i.purchase_signal + 0.3 * (i.search_interest if i.search_interest is not None else i.purchase_signal)
        return _clamp(s), 1.0 if i.search_interest is not None else 0.8
    if i.search_interest is not None:
        # Search intent is a reasonable demand proxy, engagement less so.
        s = 0.8 * i.search_interest + 0.2 * (i.engagement_signal or i.search_interest)
        return _clamp(min(s, 70.0)), 0.6
    if i.engagement_signal is not None:
        flags.append("demand_from_engagement_only: viral attention is not proven purchase demand")
        return _clamp(min(i.engagement_signal * 0.5, ENGAGEMENT_ONLY_DEMAND_CAP)), 0.3
    return NEUTRAL, 0.0


def score_profit(net_margin: float | None) -> tuple[float, float]:
    if net_margin is None:
        return NEUTRAL, 0.0
    # 0% -> 20, 15% -> 55, 30%+ -> ~90; negative margins collapse toward 0.
    if net_margin <= 0:
        return _clamp(20 + net_margin * 200), 1.0
    return _clamp(20 + 100 * (1 - math.exp(-net_margin / 0.18)) * 0.8), 1.0


def score_competition(count: int | None, quality: float | None) -> tuple[float, float]:
    if count is None and quality is None:
        return NEUTRAL, 0.0
    parts, cov = [], 0.0
    if count is not None:
        # few sellers = more room; log scale
        parts.append(_clamp(100 - 22 * math.log10(1 + count)))
        cov += 0.5
    if quality is not None:
        parts.append(100 - quality)
        cov += 0.5
    return _clamp(sum(parts) / len(parts)), cov


def compute_score(i: ScoreInput, adjustments: list[dict[str, Any]] | None = None) -> ScoreResult:
    flags: list[str] = []
    comp: dict[str, tuple[float, float]] = {}

    comp["demand"] = score_demand(i, flags)
    if i.trend_velocity is not None:
        comp["trend_momentum"] = (_clamp(i.trend_velocity), 1.0)
    else:
        comp["trend_momentum"] = (NEUTRAL, 0.0)
    comp["profit_potential"] = score_profit(i.net_margin)
    comp["competition_opportunity"] = score_competition(i.competitor_count, i.competition_quality)

    diff = _avg([i.differentiation_potential, i.customization_potential])
    if i.review_complaint_rate is not None and diff is not None:
        # recurring complaints about incumbents = improvement opportunity
        diff = _clamp(diff + 25 * i.review_complaint_rate)
    comp["differentiation"] = (diff, 1.0) if diff is not None else (NEUTRAL, 0.0)
    comp["supplier_reliability"] = (i.supplier_reliability, 1.0) if i.supplier_reliability is not None else (NEUTRAL, 0.0)
    comp["marketing_potential"] = (i.marketing_potential, 1.0) if i.marketing_potential is not None else (NEUTRAL, 0.0)
    comp["scalability"] = (i.scalability, 1.0) if i.scalability is not None else (NEUTRAL, 0.0)

    viability, vcov = 70.0, 0.0
    if i.return_risk is not None:
        viability -= 60 * i.return_risk
        vcov += 0.5
    if i.sentiment is not None:
        viability += 15 * i.sentiment
        vcov += 0.25
    status_penalty = {"approved": 0, "unreviewed": 10, "needs_review": 15, "restricted": 30, "blocked": 70}.get(i.compliance_status, 10)
    viability -= status_penalty
    vcov += 0.25 if i.compliance_status in {"approved", "blocked", "restricted", "needs_review"} else 0.0
    comp["risk_adjusted_viability"] = (_clamp(viability), vcov)

    total = sum(WEIGHTS[k] * v for k, (v, _) in comp.items())
    coverage = sum(WEIGHTS[k] * c for k, (_, c) in comp.items())

    applied = []
    for adj in adjustments or []:
        delta = float(adj.get("delta", 0))
        delta = max(-30.0, min(30.0, delta))  # bounded so no single agent can dominate
        total += delta
        applied.append({**adj, "delta": delta})

    if i.compliance_status == "blocked":
        flags.append("compliance_blocked: launch prohibited pending human review")
        total = min(total, 25.0)
    elif i.compliance_status == "restricted":
        flags.append("compliance_restricted: regulated category, launch gated on verified documentation")
    if i.net_margin is not None and i.net_margin < 0:
        flags.append("negative_unit_economics")

    components = {
        k: {"score": round(v, 1), "weight": WEIGHTS[k], "weighted": round(v * WEIGHTS[k], 2), "coverage": round(c, 2)}
        for k, (v, c) in comp.items()
    }
    if applied:
        components["_adjustments"] = {"items": applied}
    return ScoreResult(score=round(_clamp(total), 1), confidence=round(coverage, 2), components=components, flags=flags)


def input_from_product(p: Any, supplier_reliability: float | None = None) -> ScoreInput:
    return ScoreInput(
        purchase_signal=p.purchase_signal,
        engagement_signal=p.engagement_signal,
        search_interest=p.search_interest,
        trend_velocity=p.trend_velocity,
        net_margin=p.net_margin,
        competitor_count=p.competitor_count,
        competition_quality=p.competition_quality,
        differentiation_potential=p.differentiation_potential,
        customization_potential=p.customization_potential,
        supplier_reliability=supplier_reliability,
        marketing_potential=p.marketing_potential,
        scalability=p.scalability,
        return_risk=p.return_risk,
        compliance_status=p.compliance_status,
        sentiment=p.sentiment,
        review_complaint_rate=p.review_complaint_rate,
    )


def supplier_reliability_score(s: Any) -> tuple[float | None, float]:
    """0-100 reliability from supplier attributes. Returns (score, coverage)."""
    parts: list[tuple[float, float]] = []  # (score, weight)
    if s.rating is not None:
        parts.append((_clamp((s.rating - 3.0) / 2.0 * 100), 0.3))
    if s.years_active is not None:
        parts.append((_clamp(100 * (1 - math.exp(-s.years_active / 3))), 0.15))
    if s.response_rate is not None:
        parts.append((_clamp(s.response_rate * 100), 0.15))
    if s.dispute_rate is not None:
        parts.append((_clamp(100 - s.dispute_rate * 1000), 0.2))
    if s.avg_delivery_days is not None:
        parts.append((_clamp(100 - (s.avg_delivery_days - 3) * 5), 0.1))
    bonus_w = 0.1
    bonus = 50 + (20 if s.has_product_documentation else 0) + (15 if s.eu_based else 0) + (15 if s.offers_private_label else 0)
    parts.append((_clamp(bonus), bonus_w))
    known_w = sum(w for _, w in parts)
    if known_w <= bonus_w:
        return None, 0.0
    return round(sum(v * w for v, w in parts) / known_w, 1), round(known_w, 2)
