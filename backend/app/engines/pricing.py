"""Pricing scenarios (spec section 11).

Honest-pricing rules enforced in code:
* A promotional "was" price must be the lowest price charged in the previous 30
  days (EU Omnibus Directive / Swedish Price Information Act). Without verified
  price history no reference price is produced.
* No scenario is applied to a live store here; live changes go through approvals.
"""
from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime, timedelta, UTC

from .economics import CostInputs, compute

PSYCH_ENDINGS_SEK = (9, 49, 99)


def psychological_round(price: float, currency: str = "SEK") -> float:
    """Round up to a conventional price point (e.g. 249, 299 SEK; 24.90 EUR)."""
    if currency.upper() in {"SEK", "NOK", "DKK"}:
        if price < 100:
            return float(math.ceil(price / 10) * 10 - 1)
        base = math.floor(price / 100) * 100
        for end in PSYCH_ENDINGS_SEK:
            if base + end >= price:
                return float(base + end)
        return float(base + 149) if base + 149 >= price else float(base + 199)
    return math.ceil(price) - 0.10 if price > 1 else round(price, 2)


def price_for_target_margin(c: CostInputs, target_contribution_pct: float, currency: str = "SEK") -> float:
    """Smallest retail price (incl. VAT) whose contribution margin >= target. Bisection."""
    lo, hi = max(0.01, c.unit_cost), max(10.0, c.unit_cost * 50 + 1000)
    if compute(replace(c, retail_price_incl_vat=hi)).contribution_margin_pct < target_contribution_pct:
        raise ValueError("target margin unreachable with these costs")
    for _ in range(60):
        mid = (lo + hi) / 2
        if compute(replace(c, retail_price_incl_vat=mid)).contribution_margin_pct >= target_contribution_pct:
            hi = mid
        else:
            lo = mid
    return psychological_round(hi, currency)


def lowest_price_last_30_days(history: list[tuple[datetime, float]], now: datetime | None = None) -> float | None:
    now = now or datetime.now(UTC)
    window = [p for t, p in history if now - timedelta(days=30) <= t <= now]
    return min(window) if window else None


def scenarios(
    c: CostInputs,
    competitor_prices: list[float] | None = None,
    currency: str = "SEK",
    price_history: list[tuple[datetime, float]] | None = None,
    bundle_units: int = 3,
    bundle_discount: float = 0.15,
) -> dict:
    comp = sorted(p for p in (competitor_prices or []) if p > 0)
    median = comp[len(comp) // 2] if comp else None
    out: dict[str, dict] = {}

    def add(name: str, price: float, rationale: str, cost: CostInputs = c, extra: dict | None = None) -> None:
        econ = compute(replace(cost, retail_price_incl_vat=price))
        out[name] = {
            "price": price,
            "contribution_margin": econ.contribution_margin,
            "contribution_margin_pct": econ.contribution_margin_pct,
            "break_even_cac": econ.break_even_cac,
            "viable": econ.contribution_margin > 0,
            "rationale": rationale,
            **(extra or {}),
        }

    floor = price_for_target_margin(c, 0.25, currency)
    add("margin_floor", floor, "Lowest price that still meets the 25% contribution target after expected returns and fees")
    standard = max(floor, psychological_round(median, currency)) if median else floor
    add("standard", standard, "Market price (competitor median), never below the margin floor" if median
        else "No competitor data: margin floor used as standard")

    if median:
        competitive = psychological_round(median * 0.95, currency)
        add("competitive", competitive, f"5% under competitor median ({median:.0f})")
        premium = psychological_round(max(median * 1.25, standard * 1.2), currency)
    else:
        premium = psychological_round(standard * 1.35, currency)
    add("premium", premium, "Premium positioning; requires real differentiation (materials, design, service)")

    bundle_cost = replace(
        c,
        unit_cost=c.unit_cost * bundle_units,
        inbound_shipping=c.inbound_shipping * (1 + 0.5 * (bundle_units - 1)),
        packaging=c.packaging * 1.5,
    )
    bundle_price = psychological_round(standard * bundle_units * (1 - bundle_discount), currency)
    add(f"bundle_x{bundle_units}", bundle_price, f"{bundle_units}-unit bundle at {int(bundle_discount*100)}% off", bundle_cost)

    sub_price = psychological_round(standard * 0.88, currency)
    sub_cost = replace(c, cac=c.cac / 3)  # acquisition amortised over expected >=3 renewals (assumption)
    add("subscription", sub_price, "Recurring delivery at 12% off; CAC amortised over 3 cycles (assumption)", sub_cost,
        {"epistemic": "assumption"})

    lowest = lowest_price_last_30_days(price_history or [])
    if lowest is None:
        out["promotional"] = {
            "price": None,
            "viable": False,
            "rationale": "No verified 30-day price history: a reference ('was') price cannot be shown lawfully.",
        }
    else:
        promo = psychological_round(lowest * 0.85, currency)
        add("promotional", promo, f"15% off the lowest price of the last 30 days ({lowest:.0f})",
            extra={"reference_price": lowest})
    return {"currency": currency, "competitor_median": median, "scenarios": out}
