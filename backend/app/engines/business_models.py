"""Business model generator (spec section 6).

Each of the 25 models has baseline attributes on a 1-5 scale. Product traits
shift the fit. The result ranks all models and recommends the top three with
explicit reasons. Dropshipping gets no special treatment, and is penalised when
long delivery times would hurt EU customers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# capital, complexity, margin, scalability, legal_burden, cac, time_to_profit, risk, recurring  (1=low, 5=high)
_BASE: dict[str, tuple[int, int, int, int, int, int, int, int, int]] = {
    "affiliate_marketing":        (1, 2, 2, 4, 1, 3, 4, 2, 1),
    "dropshipping":               (1, 2, 2, 3, 3, 4, 2, 3, 1),
    "traditional_ecommerce":      (3, 3, 3, 3, 3, 4, 3, 3, 1),
    "wholesale_resale":           (4, 3, 2, 3, 3, 2, 3, 3, 2),
    "private_label":              (4, 4, 4, 4, 4, 4, 4, 3, 2),
    "white_label":                (3, 3, 3, 4, 3, 4, 3, 3, 2),
    "print_on_demand":            (1, 2, 2, 4, 2, 4, 2, 2, 1),
    "custom_manufacturing":       (5, 5, 4, 3, 4, 3, 5, 4, 2),
    "subscription_commerce":      (3, 3, 3, 4, 3, 4, 4, 3, 5),
    "digital_downloads":          (1, 1, 5, 5, 1, 3, 2, 1, 2),
    "online_courses":             (2, 3, 5, 5, 2, 4, 3, 2, 2),
    "membership_community":       (1, 3, 4, 4, 2, 3, 4, 2, 5),
    "b2b_distribution":           (4, 4, 3, 4, 3, 2, 4, 3, 4),
    "product_licensing":          (2, 3, 4, 3, 4, 2, 5, 3, 3),
    "lead_generation":            (1, 2, 3, 4, 3, 3, 3, 2, 3),
    "comparison_website":         (1, 2, 3, 4, 2, 2, 4, 2, 2),
    "niche_marketplace":          (3, 5, 3, 5, 4, 4, 5, 4, 3),
    "recommendation_service":     (2, 3, 3, 4, 2, 3, 3, 2, 3),
    "bundled_product_store":      (3, 3, 4, 3, 3, 3, 3, 3, 2),
    "rental":                     (4, 4, 3, 3, 3, 3, 4, 3, 4),
    "product_as_a_service":       (4, 4, 4, 3, 3, 3, 4, 3, 5),
    "custom_gift_business":       (2, 3, 4, 3, 2, 3, 2, 2, 1),
    "seasonal_store":             (2, 3, 3, 2, 3, 4, 2, 3, 1),
    "ai_product_configuration":   (3, 4, 4, 4, 2, 3, 4, 3, 3),
    "automated_content_business": (1, 2, 3, 4, 2, 2, 4, 2, 2),
}
ATTRS = ("startup_capital", "operational_complexity", "profit_margin", "scalability", "legal_requirements",
         "customer_acquisition_cost", "time_to_profitability", "risk", "recurring_revenue")
# +1 = higher is better, -1 = lower is better
_DIRECTION = (-1, -1, +1, +1, -1, -1, -1, -1, +1)
_WEIGHT = (0.10, 0.10, 0.18, 0.12, 0.08, 0.10, 0.10, 0.10, 0.12)

ALL_MODELS = tuple(_BASE)


@dataclass
class ProductTraits:
    unit_cost: float | None = None
    retail_price: float | None = None
    delivery_days: float | None = None
    customization_potential: float | None = None  # 0-100
    differentiation_potential: float | None = None
    demand: float | None = None
    competition_quality: float | None = None
    consumable: bool = False
    seasonal: bool = False
    educational_depth: bool = False  # needs skill / instructions to use well
    giftable: bool = False
    high_ticket: bool = False
    b2b_relevant: bool = False
    compliance_heavy: bool = False
    capital_available_sek: float | None = None


def _fit_adjustments(m: str, t: ProductTraits) -> tuple[float, list[str]]:
    adj, why = 0.0, []

    def bump(v: float, reason: str) -> None:
        nonlocal adj
        adj += v
        why.append(f"{'+' if v >= 0 else ''}{v:.2f}: {reason}")

    cust = t.customization_potential or 0
    if m in {"print_on_demand", "custom_gift_business", "ai_product_configuration"} and cust >= 60:
        bump(0.5, "high customisation potential")
    if m in {"custom_gift_business", "seasonal_store", "bundled_product_store"} and t.giftable:
        bump(0.35, "giftable product")
    if m == "subscription_commerce":
        bump(0.6 if t.consumable else -0.6, "consumable / replenishable" if t.consumable else "not consumable: weak subscription fit")
    if m in {"online_courses", "digital_downloads", "membership_community", "automated_content_business"} and t.educational_depth:
        bump(0.45, "users need know-how: information products add value")
    if m in {"rental", "product_as_a_service"}:
        bump(0.5 if t.high_ticket else -0.7, "high-ticket item" if t.high_ticket else "low-ticket: rental not worthwhile")
    if m == "seasonal_store":
        bump(0.4 if t.seasonal else -0.6, "seasonal demand" if t.seasonal else "not seasonal")
    if m == "b2b_distribution":
        bump(0.5 if t.b2b_relevant else -0.5, "B2B buyers exist" if t.b2b_relevant else "no B2B buyer signal")
    if m == "dropshipping" and t.delivery_days is not None and t.delivery_days > 10:
        bump(-0.6, f"{t.delivery_days:.0f}-day delivery hurts EU conversion and raises disputes")
    if m in {"private_label", "white_label", "custom_manufacturing"}:
        d = t.differentiation_potential or 0
        if d >= 60:
            bump(0.45, "strong differentiation room")
        if t.capital_available_sek is not None and t.capital_available_sek < 30_000:
            bump(-0.6, "requires inventory capital beyond what is available")
    if m in {"affiliate_marketing", "comparison_website"} and (t.competition_quality or 0) >= 70:
        bump(0.3, "strong incumbent brands: earn by recommending instead of competing")
    if m in {"dropshipping", "traditional_ecommerce", "private_label"} and t.compliance_heavy:
        bump(-0.4, "compliance-heavy category: being importer/seller of record adds liability")
    if m in {"affiliate_marketing", "comparison_website", "automated_content_business", "lead_generation"} and t.compliance_heavy:
        bump(0.25, "lower product-liability exposure than selling the item")
    if m == "product_licensing" and (t.differentiation_potential or 0) < 60:
        bump(-0.5, "nothing proprietary to license yet")
    return adj, why


def evaluate(t: ProductTraits) -> dict[str, Any]:
    ranked = []
    for m, attrs in _BASE.items():
        base = sum(w * (a if d > 0 else 6 - a) for a, d, w in zip(attrs, _DIRECTION, _WEIGHT))  # 1..5
        adj, why = _fit_adjustments(m, t)
        score = max(0.0, min(100.0, (base + adj - 1) / 4 * 100))
        ranked.append({
            "model": m,
            "score": round(score, 1),
            "attributes": dict(zip(ATTRS, attrs)),
            "fit_reasons": why,
        })
    ranked.sort(key=lambda r: r["score"], reverse=True)
    return {"recommended": ranked[:3], "all": ranked, "epistemic": "estimate"}


def traits_from_product(p: Any, compliance_heavy: bool = False) -> ProductTraits:
    tags = {x.lower() for x in (p.tags or [])}
    return ProductTraits(
        unit_cost=p.wholesale_price,
        retail_price=p.retail_price,
        delivery_days=p.delivery_days,
        customization_potential=p.customization_potential,
        differentiation_potential=p.differentiation_potential,
        demand=p.purchase_signal,
        competition_quality=p.competition_quality,
        consumable="consumable" in tags,
        seasonal="seasonal" in tags,
        educational_depth="educational" in tags or "hobby" in tags,
        giftable="giftable" in tags or "gift" in tags,
        high_ticket=(p.retail_price or 0) >= 2000,
        b2b_relevant="b2b" in tags,
        compliance_heavy=compliance_heavy,
    )
