"""Brand Portfolio Manager (§8): per-brand metrics, comparisons, extension opportunities
and overlap detection ("don't create a brand for products that belong together").
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, UTC
from typing import Any

OVERLAP_THRESHOLD = 0.55


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def brand_similarity(genres_a: set[str], genres_b: set[str], seg_a: set[str], seg_b: set[str], cat_a: set[str], cat_b: set[str]) -> float:
    return round(0.4 * jaccard(genres_a, genres_b) + 0.35 * jaccard(seg_a, seg_b) + 0.25 * jaccard(cat_a, cat_b), 3)


def overlap_check(candidate: dict[str, set[str]], brands: list[Any]) -> list[dict[str, Any]]:
    out = []
    for b in brands:
        if b.status == "retired":
            continue
        g = set((b.genre_dna or {}).get("genres", []))
        sim = brand_similarity(candidate["genres"], g, candidate["segments"], set(b.segments or []), candidate["categories"], set(b.categories or []))
        if sim >= OVERLAP_THRESHOLD:
            out.append({"brand_id": b.id, "brand": b.name, "similarity": sim,
                        "recommendation": f"Add to '{b.name}' as a product line instead of creating a new brand."})
    return sorted(out, key=lambda x: x["similarity"], reverse=True)


def metrics(brand: Any, products: list[Any], ledger: list[Any], campaigns: list[Any], performance: list[Any], observations: list[Any],
            suppliers: set[int], now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    pids = {p.id for p in products if p.brand_id == brand.id}
    rows = [e for e in ledger if e.brand_id == brand.id or (e.product_id in pids)]

    def total(kind: str, since: datetime | None = None, until: datetime | None = None) -> float:
        s = 0.0
        for e in rows:
            at = e.occurred_at if e.occurred_at.tzinfo else e.occurred_at.replace(tzinfo=UTC)
            if e.kind == kind and (since is None or at >= since) and (until is None or at < until):
                s += e.amount
        return s
    revenue = total("revenue")
    costs = sum(e.amount for e in rows if e.kind != "revenue")
    variable = sum(e.amount for e in rows if e.kind in ("cogs", "shipping", "fees", "ad_spend", "refund", "chargeback"))
    last30, prev30 = total("revenue", now - timedelta(days=30)), total("revenue", now - timedelta(days=60), now - timedelta(days=30))
    cids = {c.id for c in campaigns if c.brand_id == brand.id}
    perf = [r for r in performance if r.campaign_id in cids]
    clicks, orders = sum(r.clicks for r in perf), sum(r.orders for r in perf)
    camp_spend = sum(r.spend for r in perf)
    buyers: dict[str, int] = defaultdict(int)
    for e in rows:
        if e.kind == "revenue" and e.customer_ref:
            buyers[e.customer_ref] += 1
    branded = [o for o in observations if o.keyword.lower() == brand.name.lower()]
    channels = {e.channel for e in rows}
    return {
        "brand_id": brand.id, "name": brand.name, "status": brand.status, "products": len(pids),
        "revenue": round(revenue, 2), "contribution": round(revenue - variable, 2), "net_profit": round(revenue - costs, 2),
        "growth_30d": round((last30 - prev30) / prev30, 3) if prev30 else None,
        "conversion_rate": round(orders / clicks, 4) if clicks else None,
        "marketing_cost": round(total("ad_spend") + camp_spend, 2),
        "retention_repeat_rate": round(sum(1 for n in buyers.values() if n > 1) / len(buyers), 3) if buyers else None,
        "retention_note": None if buyers else "needs pseudonymous customer_ref on ledger revenue entries (first-party, consented)",
        "recognition_branded_search": round(sum(o.value for o in branded) / len(branded), 1) if branded else None,
        "recognition_note": None if branded else f"import branded-search observations with keyword '{brand.name.lower()}'",
        "operational_complexity": len(pids) + len(suppliers) + len(channels),
        "demo_data": any(getattr(e, "is_demo", False) for e in rows),
    }


def extension_opportunities(brand_metrics: list[dict[str, Any]], brands: list[Any], products: list[Any]) -> list[dict[str, Any]]:
    by_id = {b.id: b for b in brands}
    out = []
    for m in brand_metrics:
        b = by_id[m["brand_id"]]
        if (m["contribution"] or 0) <= 0:
            continue
        cats = {p.category for p in products if p.brand_id == b.id and p.category}
        unbranded = [p for p in products if p.brand_id is None and p.category in cats]
        for p in unbranded[:5]:
            out.append({"type": "extend_line", "brand": b.name, "product_id": p.id, "product": p.name,
                        "why": f"'{b.name}' is contribution-positive in '{p.category}'; adding is cheaper than a new brand"})
        if len(cats) >= 3 and m["operational_complexity"] > 12:
            out.append({"type": "consider_spin_off", "brand": b.name, "why": "many categories and high complexity — a focused sub-brand may sharpen identity (validate audience difference first)"})
    return out
