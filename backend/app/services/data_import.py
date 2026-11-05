"""Manual / licensed dataset import (CSV or JSON) and the clearly-labelled demo dataset.

Import is how data from platforms without an API (or licensed exports, e.g. a
Google Trends CSV or a supplier catalogue) enters the system legitimately.
"""
from __future__ import annotations

import csv
import io
import json
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..models import LedgerEntry, Product, Supplier, TrendObservation

PRODUCT_FIELDS = {c for c in Product.__table__.columns.keys()} - {"id", "created_at", "updated_at", "opportunity_score",
                                                                 "score_breakdown", "score_confidence", "compliance_status",
                                                                 "compliance_report", "gross_margin", "net_margin"}
LIST_FIELDS = {"competitor_prices", "tags", "image_refs", "platforms_seen"}


def _coerce(field: str, v: Any) -> Any:
    if v in ("", None):
        return None if field not in LIST_FIELDS else []
    col = Product.__table__.columns.get(field)
    if field in LIST_FIELDS:
        if isinstance(v, list):
            return v
        parts = [x.strip() for x in str(v).replace(";", "|").split("|") if x.strip()]
        return [float(x) for x in parts] if field == "competitor_prices" else parts
    if col is not None:
        t = col.type.python_type
        if t is float:
            return float(v)
        if t is int:
            return int(float(v))
        if t is bool:
            return str(v).lower() in ("1", "true", "yes")
    return v


def parse_rows(content: str, fmt: str) -> list[dict[str, Any]]:
    if fmt == "json":
        data = json.loads(content)
        return data if isinstance(data, list) else data.get("items", [])
    return list(csv.DictReader(io.StringIO(content)))


def import_products(db: Session, rows: list[dict[str, Any]], is_demo: bool = False) -> list[Product]:
    out = []
    for r in rows:
        if not r.get("name"):
            continue
        kw = {k: _coerce(k, v) for k, v in r.items() if k in PRODUCT_FIELDS}
        kw = {k: v for k, v in kw.items() if v is not None}
        p = Product(**kw, is_demo=is_demo)
        db.add(p)
        out.append(p)
    db.flush()
    return out


def import_observations(db: Session, rows: list[dict[str, Any]], is_demo: bool = False) -> int:
    n = 0
    for r in rows:
        at = r.get("observed_at") or r.get("date")
        dt = datetime.fromisoformat(str(at))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        db.add(TrendObservation(keyword=r["keyword"], platform=r.get("platform", "import"), metric=r.get("metric", "value"),
                                value=float(r["value"]), region=r.get("region", "SE"), observed_at=dt,
                                source_ref=r.get("source_ref", "manual_import"), is_demo=is_demo))
        n += 1
    db.flush()
    return n


def import_ledger(db: Session, rows: list[dict[str, Any]], is_demo: bool = False) -> int:
    n = 0
    for r in rows:
        dt = datetime.fromisoformat(str(r["occurred_at"]))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        db.add(LedgerEntry(kind=r["kind"], amount=float(r["amount"]), occurred_at=dt, channel=r.get("channel", "direct"),
                           product_id=int(r["product_id"]) if r.get("product_id") else None,
                           store_id=int(r["store_id"]) if r.get("store_id") else None,
                           currency=r.get("currency", "SEK"), reference=r.get("reference", ""), is_demo=is_demo))
        n += 1
    db.flush()
    return n


# ---------------------------------------------------------------- DEMO DATA (synthetic, labelled)
def load_demo(db: Session, seed: int = 7) -> dict[str, int]:
    """Synthetic sample data so the command center can be explored before any
    connector is configured. Every row has is_demo=True and is badged DEMO in the UI.
    It is NOT market data. Remove with DELETE /api/demo."""
    rng = random.Random(seed)
    now = datetime.now(timezone.utc)
    sup_cn = Supplier(name="Demo Supplier Shenzhen", platform="alibaba", country="CN", rating=4.6, years_active=6, moq=100,
                      avg_delivery_days=12, response_rate=0.92, dispute_rate=0.01, offers_private_label=True,
                      offers_custom_packaging=True, has_product_documentation=True, is_demo=True)
    sup_eu = Supplier(name="Demo Supplier Poland", platform="direct", country="PL", eu_based=True, rating=4.4, years_active=9, moq=50,
                      avg_delivery_days=3, response_rate=0.85, dispute_rate=0.005, offers_custom_packaging=True,
                      has_product_documentation=True, is_demo=True)
    db.add_all([sup_cn, sup_eu])
    db.flush()
    products = [
        dict(name="Ceramic pour-over coffee set", category="kitchen", tags=["coffee", "giftable", "hobby", "consumable"],
             description="Pour-over dripper, server and filters.", wholesale_price=62, shipping_cost=28, delivery_days=12, retail_price=449,
             competitor_prices=[399, 449, 529, 599], purchase_signal=62, engagement_signal=70, search_interest=58, competitor_count=40,
             competition_quality=55, sentiment=0.4, review_complaint_rate=0.18, return_risk=0.05, marketing_potential=75,
             customization_potential=60, differentiation_potential=65, scalability=60, supplier_id=sup_cn.id),
        dict(name="Linen sleep mask with personalised embroidery", category="textiles", tags=["sleep", "giftable", "personalised"],
             description="Natural linen sleep mask, custom initials.", wholesale_price=24, shipping_cost=9, delivery_days=4, retail_price=249,
             competitor_prices=[149, 199, 249], purchase_signal=48, engagement_signal=55, search_interest=52, competitor_count=25,
             competition_quality=40, sentiment=0.5, review_complaint_rate=0.12, return_risk=0.04, marketing_potential=70,
             customization_potential=90, differentiation_potential=70, scalability=65, supplier_id=sup_eu.id),
        dict(name="Magnetic LED reading lamp", category="electronics", tags=["lighting", "reading"],
             description="Rechargeable clip-on LED lamp with battery.", wholesale_price=55, shipping_cost=25, delivery_days=14, retail_price=299,
             competitor_prices=[199, 249, 299, 349], engagement_signal=88, competitor_count=300, competition_quality=70,
             sentiment=0.1, review_complaint_rate=0.3, return_risk=0.12, marketing_potential=80, customization_potential=20,
             differentiation_potential=35, scalability=70, supplier_id=sup_cn.id),
        dict(name="Sourdough starter kit", category="kitchen", tags=["sourdough", "baking", "hobby", "educational", "giftable"],
             description="Jar, scraper, banneton, dried starter and guide.", wholesale_price=85, shipping_cost=30, delivery_days=10,
             retail_price=499, competitor_prices=[349, 449, 499], purchase_signal=55, engagement_signal=60, search_interest=63,
             competitor_count=15, competition_quality=35, sentiment=0.6, review_complaint_rate=0.2, return_risk=0.03,
             marketing_potential=80, customization_potential=55, differentiation_potential=75, scalability=55, supplier_id=sup_cn.id),
    ]
    field_ops = [  # Field Operations sample catalogue (synthetic)
        dict(name="Roll-top stem bag for e-scooter", category="mobility", tags=["commuter", "winter", "giftable"],
             description="Waterproof roll-top bag with reflective piping that straps to the scooter stem.", wholesale_price=88, shipping_cost=28,
             delivery_days=11, retail_price=449, competitor_prices=[299, 399, 449, 499], engagement_signal=72, search_interest=48,
             competitor_count=70, competition_quality=45, marketing_potential=78, customization_potential=60, differentiation_potential=65,
             scalability=70, return_risk=0.05, supplier_id=sup_cn.id),
        dict(name="Winter commuter pannier with reflective panels", category="mobility", tags=["e-bike", "winter", "commuter"],
             description="Pannier bag for e-bike racks with reflective panels and roll-top closure.", wholesale_price=160, shipping_cost=45,
             delivery_days=4, retail_price=899, competitor_prices=[699, 899, 1099], purchase_signal=51, search_interest=57,
             competitor_count=35, competition_quality=60, marketing_potential=70, customization_potential=50, differentiation_potential=60,
             scalability=65, return_risk=0.04, supplier_id=sup_eu.id),
        dict(name="Hand-crank emergency radio with solar charging", category="survival", tags=["emergency", "preparedness"],
             description="Emergency radio with hand crank, solar panel, LED light and power bank.", wholesale_price=140, shipping_cost=35,
             delivery_days=12, retail_price=599, competitor_prices=[449, 599, 749], purchase_signal=58, search_interest=62,
             competitor_count=50, competition_quality=55, marketing_potential=65, customization_potential=30, differentiation_potential=45,
             scalability=60, return_risk=0.06, supplier_id=sup_cn.id),
        dict(name="Bushcraft ferro rod fire starter set", category="outdoor", tags=["bushcraft", "consumable", "giftable"],
             description="Ferro rod, striker and tinder tin for fire-starting.", wholesale_price=35, shipping_cost=15, delivery_days=10,
             retail_price=249, competitor_prices=[149, 199, 249], purchase_signal=49, engagement_signal=66, competitor_count=120,
             competition_quality=50, marketing_potential=80, customization_potential=70, differentiation_potential=55, scalability=65,
             return_risk=0.02, supplier_id=sup_cn.id),
        dict(name="Modular EDC organiser pouch", category="edc", tags=["edc", "modular"],
             description="Organiser pouch with webbing grid for everyday carry tools, cables and a flashlight.", wholesale_price=55,
             shipping_cost=20, delivery_days=11, retail_price=349, competitor_prices=[249, 349, 449], engagement_signal=81, search_interest=44,
             competitor_count=200, competition_quality=65, marketing_potential=85, customization_potential=80, differentiation_potential=70,
             scalability=75, return_risk=0.03, supplier_id=sup_cn.id),
    ]
    products += field_ops
    created = import_products(db, products, is_demo=True)
    obs = 0
    curves = {"sourdough": (0.10, ["youtube", "reddit", "etsy"]), "coffee": (0.02, ["youtube", "etsy"]),
              "sleep": (0.06, ["reddit", "etsy"]), "lighting": (-0.05, ["youtube"])}
    for kw, (g, plats) in curves.items():
        for plat in plats:
            base = rng.uniform(80, 400)
            for w in range(16):
                v = base * math.exp(g * w) * rng.uniform(0.9, 1.1)
                db.add(TrendObservation(keyword=kw, platform=plat, metric="demo_index", value=round(v, 1),
                                        observed_at=now - timedelta(weeks=15 - w), source_ref="demo", is_demo=True))
                obs += 1
    ledger = 0
    p1 = created[0]
    for d in range(45):
        day = now - timedelta(days=44 - d)
        orders = max(0, int(rng.gauss(3 + d * 0.08, 1.2)))
        rev = orders * 449
        for kind, amt in (("revenue", rev), ("cogs", orders * 90), ("fees", rev * 0.03 + orders * 1.8),
                          ("ad_spend", orders * 95 + rng.uniform(20, 60)), ("refund", rev * 0.04)):
            if amt > 0:
                db.add(LedgerEntry(product_id=p1.id, channel="tiktok_ads" if kind != "revenue" or d % 2 else "organic",
                                   kind=kind, amount=round(amt, 2), occurred_at=day, is_demo=True))
                ledger += 1
    db.flush()
    return {"products": len(created), "suppliers": 2, "observations": obs, "ledger_entries": ledger}


def clear_demo(db: Session) -> dict[str, int]:
    from ..models import Opportunity, Trend

    counts = {}
    demo_ids = [p.id for p in db.query(Product).filter(Product.is_demo.is_(True)).all()]
    from ..models import (BrandConcept, Campaign, CampaignPerformance, CollaborationSession, CollaborationTurn, CompatibilityRecord,
                          CreativeAsset, GraphEdge, GraphNode)

    concept_ids = [c.id for c in db.query(BrandConcept).filter(BrandConcept.product_id.in_(demo_ids)).all()]
    camp_ids = [c.id for c in db.query(Campaign).filter(Campaign.product_id.in_(demo_ids)).all()]
    sess_ids = [x.id for x in db.query(CollaborationSession).filter(CollaborationSession.product_id.in_(demo_ids)).all()]
    db.query(CreativeAsset).filter(CreativeAsset.concept_id.in_(concept_ids) | CreativeAsset.product_id.in_(demo_ids)).delete(synchronize_session=False)
    db.query(CampaignPerformance).filter(CampaignPerformance.campaign_id.in_(camp_ids)).delete(synchronize_session=False)
    counts["campaigns"] = db.query(Campaign).filter(Campaign.id.in_(camp_ids)).delete(synchronize_session=False)
    counts["concepts"] = db.query(BrandConcept).filter(BrandConcept.id.in_(concept_ids)).delete(synchronize_session=False)
    db.query(CollaborationTurn).filter(CollaborationTurn.session_id.in_(sess_ids)).delete(synchronize_session=False)
    counts["sessions"] = db.query(CollaborationSession).filter(CollaborationSession.id.in_(sess_ids)).delete(synchronize_session=False)
    db.query(CompatibilityRecord).filter(CompatibilityRecord.product_id.in_(demo_ids)).delete(synchronize_session=False)
    for pid in demo_ids:
        for g in (f"mutation:{pid}", f"sideways:{pid}"):
            db.query(GraphNode).filter(GraphNode.graph == g).delete(synchronize_session=False)
            db.query(GraphEdge).filter(GraphEdge.graph == g).delete(synchronize_session=False)
    counts["opportunities"] = db.query(Opportunity).filter(Opportunity.product_id.in_(demo_ids)).delete(synchronize_session=False)
    counts["ledger_entries"] = db.query(LedgerEntry).filter(LedgerEntry.is_demo.is_(True)).delete(synchronize_session=False)
    counts["products"] = db.query(Product).filter(Product.is_demo.is_(True)).delete(synchronize_session=False)
    counts["suppliers"] = db.query(Supplier).filter(Supplier.is_demo.is_(True)).delete(synchronize_session=False)
    counts["observations"] = db.query(TrendObservation).filter(TrendObservation.is_demo.is_(True)).delete(synchronize_session=False)
    counts["trends"] = db.query(Trend).filter(Trend.is_demo.is_(True)).delete(synchronize_session=False)
    db.flush()
    return counts
