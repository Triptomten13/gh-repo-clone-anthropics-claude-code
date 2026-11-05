"""Unit economics & contribution margin (spec sections 11 and 15).

All money values are in the store currency (default SEK). Retail prices to EU
consumers are VAT-inclusive, so VAT is removed before computing margins.
Every assumption is returned alongside the result so it can be audited.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class CostInputs:
    retail_price_incl_vat: float
    unit_cost: float  # wholesale / COGS per unit
    inbound_shipping: float = 0.0  # supplier -> customer or -> warehouse, per unit
    packaging: float = 0.0
    fulfillment: float = 0.0  # pick/pack per order
    import_duty_rate: float = 0.0  # on (unit_cost + inbound_shipping), non-EU imports
    customs_handling: float = 0.0  # per unit fixed fee (broker/postal handling)
    vat_rate: float = 0.25  # Sweden standard rate
    payment_fee_pct: float = 0.029
    payment_fee_fixed: float = 1.80
    marketplace_fee_pct: float = 0.0
    return_rate: float = 0.05
    return_cost_per_return: float = 0.0  # return shipping + handling borne by seller
    unsellable_return_fraction: float = 0.3  # share of returned goods that must be written off
    cac: float = 0.0  # paid acquisition cost per order


@dataclass
class UnitEconomics:
    net_revenue: float
    vat: float
    landed_cost: float
    variable_costs: float
    gross_profit: float
    gross_margin: float
    expected_return_cost: float
    contribution_before_ads: float
    contribution_margin: float
    contribution_margin_pct: float
    break_even_cac: float
    break_even_roas: float | None
    assumptions: dict

    def as_dict(self) -> dict:
        return asdict(self)


def compute(c: CostInputs) -> UnitEconomics:
    if c.retail_price_incl_vat <= 0:
        raise ValueError("retail price must be positive")
    net = c.retail_price_incl_vat / (1 + c.vat_rate)
    vat = c.retail_price_incl_vat - net
    duty = (c.unit_cost + c.inbound_shipping) * c.import_duty_rate
    landed = c.unit_cost + c.inbound_shipping + duty + c.customs_handling
    fees = c.retail_price_incl_vat * c.payment_fee_pct + c.payment_fee_fixed + net * c.marketplace_fee_pct
    variable = landed + c.packaging + c.fulfillment + fees
    gross = net - landed
    # Returns (EU 14-day withdrawal right): price is refunded, seller pays return handling,
    # payment/fulfilment costs are sunk, and only the sellable share of stock is recovered.
    kept_order = net - variable
    returned_order = -(c.unsellable_return_fraction * landed + c.packaging + c.fulfillment + fees + c.return_cost_per_return)
    r = c.return_rate
    contribution_before_ads = (1 - r) * kept_order + r * returned_order
    expected_returns = kept_order - contribution_before_ads
    contribution = contribution_before_ads - c.cac
    be_cac = max(0.0, contribution_before_ads)
    be_roas = (c.retail_price_incl_vat / be_cac) if be_cac > 0 else None
    return UnitEconomics(
        net_revenue=round(net, 2),
        vat=round(vat, 2),
        landed_cost=round(landed, 2),
        variable_costs=round(variable, 2),
        gross_profit=round(gross, 2),
        gross_margin=round(gross / net, 4),
        expected_return_cost=round(expected_returns, 2),
        contribution_before_ads=round(contribution_before_ads, 2),
        contribution_margin=round(contribution, 2),
        contribution_margin_pct=round(contribution / net, 4),
        break_even_cac=round(be_cac, 2),
        break_even_roas=round(be_roas, 2) if be_roas else None,
        assumptions=asdict(c),
    )


def ad_funnel(cpm: float, ctr: float, cvr: float, aov_incl_vat: float, contribution_before_ads: float) -> dict:
    """Expected paid-ads metrics from planning assumptions (all values are estimates)."""
    if ctr <= 0 or cvr <= 0:
        raise ValueError("ctr and cvr must be positive")
    cpc = cpm / (1000 * ctr)
    cac = cpc / cvr
    roas = aov_incl_vat / cac if cac > 0 else None
    return {
        "epistemic": "estimate",
        "cpm": round(cpm, 2),
        "cpc": round(cpc, 2),
        "ctr": ctr,
        "conversion_rate": cvr,
        "cac": round(cac, 2),
        "roas": round(roas, 2) if roas else None,
        "contribution_per_order_after_ads": round(contribution_before_ads - cac, 2),
        "profitable": contribution_before_ads - cac > 0,
    }
