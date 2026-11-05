"""Financial intelligence (spec section 15): ledger aggregation, forecasts, capital allocation.

Everything is computed from LedgerEntry rows. If there is no data, the result
says so instead of returning invented numbers.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any
from collections.abc import Iterable

COST_KINDS = {"cogs", "shipping", "fees", "ad_spend", "refund", "chargeback", "opex", "tax"}
VARIABLE_KINDS = {"cogs", "shipping", "fees", "ad_spend", "refund", "chargeback"}


def signed(kind: str, amount: float) -> float:
    return amount if kind == "revenue" else -abs(amount)


def summarize(entries: Iterable[Any]) -> dict[str, Any]:
    totals: dict[str, float] = defaultdict(float)
    by_product: dict[Any, float] = defaultdict(float)
    by_store: dict[Any, float] = defaultdict(float)
    by_channel: dict[str, float] = defaultdict(float)
    n = 0
    demo = False
    for e in entries:
        n += 1
        demo = demo or bool(getattr(e, "is_demo", False))
        totals[e.kind] += e.amount
        s = signed(e.kind, e.amount)
        if e.kind != "opex":
            by_product[e.product_id] += s
            by_store[e.store_id] += s
            by_channel[e.channel] += s
    revenue = totals.get("revenue", 0.0)
    cogs = totals.get("cogs", 0.0)
    variable = sum(totals.get(k, 0.0) for k in VARIABLE_KINDS)
    net = revenue - sum(totals.get(k, 0.0) for k in COST_KINDS)
    return {
        "entries": n,
        "contains_demo_data": demo,
        "revenue": round(revenue, 2),
        "gross_profit": round(revenue - cogs, 2),
        "contribution_margin": round(revenue - variable, 2),
        "net_profit": round(net, 2),
        "ad_spend": round(totals.get("ad_spend", 0.0), 2),
        "refunds": round(totals.get("refund", 0.0), 2),
        "chargebacks": round(totals.get("chargeback", 0.0), 2),
        "opex": round(totals.get("opex", 0.0), 2),
        "tax": round(totals.get("tax", 0.0), 2),
        "roas": round(revenue / totals["ad_spend"], 2) if totals.get("ad_spend") else None,
        "profit_by_product": {str(k): round(v, 2) for k, v in by_product.items() if k is not None},
        "profit_by_store": {str(k): round(v, 2) for k, v in by_store.items() if k is not None},
        "profit_by_channel": {k: round(v, 2) for k, v in by_channel.items()},
        "totals_by_kind": {k: round(v, 2) for k, v in totals.items()},
    }


def daily_series(entries: Iterable[Any]) -> list[dict[str, Any]]:
    days: dict[date, dict[str, float]] = defaultdict(lambda: {"revenue": 0.0, "costs": 0.0})
    for e in entries:
        d = e.occurred_at.date()
        if e.kind == "revenue":
            days[d]["revenue"] += e.amount
        else:
            days[d]["costs"] += e.amount
    out = []
    for d in sorted(days):
        r, c = days[d]["revenue"], days[d]["costs"]
        out.append({"date": d.isoformat(), "revenue": round(r, 2), "costs": round(c, 2), "profit": round(r - c, 2)})
    return out


def forecast(series: list[dict[str, Any]], horizons: tuple[int, ...] = (7, 30, 90, 365), min_days: int = 14) -> dict[str, Any]:
    """Linear trend on daily revenue and profit. Requires >= ``min_days`` days of data."""
    if len(series) < min_days:
        return {"available": False, "reason": f"needs at least {min_days} days of ledger data (have {len(series)})"}
    start = date.fromisoformat(series[0]["date"])
    xs = [(date.fromisoformat(p["date"]) - start).days for p in series]

    def fit(key: str) -> tuple[float, float, float]:
        ys = [p[key] for p in series]
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        den = sum((x - mx) ** 2 for x in xs) or 1.0
        b = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / den
        a = my - b * mx
        resid = (sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys, strict=True)) / max(1, n - 2)) ** 0.5
        return a, b, resid

    out: dict[str, Any] = {"available": True, "method": "ordinary least squares on daily totals", "epistemic": "estimate", "horizons": {}}
    last_x = xs[-1]
    for key in ("revenue", "profit"):
        a, b, sd = fit(key)
        for h in horizons:
            total = sum(max(0.0, a + b * (last_x + i)) if key == "revenue" else a + b * (last_x + i) for i in range(1, h + 1))
            band = 1.28 * sd * (h ** 0.5)  # ~80% band assuming independent daily errors
            out["horizons"].setdefault(str(h), {})[key] = {"expected": round(total, 2), "low": round(total - band, 2), "high": round(total + band, 2)}
    return out


def capital_allocation(available_sek: float, product_perf: list[dict[str, Any]], reserve_pct: float = 0.25) -> dict[str, Any]:
    """Rule-based allocation recommendation. Never moves money — produces a recommendation only.

    product_perf items: {"product_id", "name", "contribution_margin", "roas", "trend": "up|flat|down"}
    """
    if available_sek <= 0:
        return {"available": False, "reason": "no capital available"}
    reserve = available_sek * reserve_pct
    deployable = available_sek - reserve
    winners = [p for p in product_perf if (p.get("contribution_margin") or 0) > 0 and (p.get("roas") or 0) >= 2.0]
    losers = [p for p in product_perf if (p.get("contribution_margin") or 0) <= 0]
    if winners:
        split = {"existing_winners": 0.45, "new_experiments": 0.20, "marketing": 0.15, "inventory": 0.10, "product_development": 0.05, "technology": 0.05}
    else:
        split = {"existing_winners": 0.0, "new_experiments": 0.45, "marketing": 0.15, "inventory": 0.05, "product_development": 0.20, "technology": 0.15}
    alloc = {k: round(deployable * v, 2) for k, v in split.items()}
    alloc["cash_reserve"] = round(reserve, 2)
    per_winner = []
    if winners:
        total_cm = sum(p["contribution_margin"] for p in winners)
        for p in winners:
            per_winner.append({"product_id": p.get("product_id"), "name": p.get("name"),
                               "amount": round(alloc["existing_winners"] * p["contribution_margin"] / total_cm, 2)})
    return {
        "available": True,
        "epistemic": "recommendation",
        "allocation": alloc,
        "winner_breakdown": per_winner,
        "discontinue_candidates": [p.get("name") for p in losers],
        "requires_approval": True,
        "note": "Recommendation only. Moving funds or committing spend requires LEVEL 5 human approval.",
    }
