"""DB-facing helpers shared by Rocky Flare agents and API routes."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..engines import compliance
from ..models import (BrandConcept, Campaign, CampaignPerformance, CustomGenre, GraphEdge, GraphNode, Persona, PersonaVersion, Product,
                      Task)
from . import field, learning
from . import mutation as M
from .personas import SEED
from .taxonomy import ProductProfile, profile_product

PERSONA_FIELDS = ("name", "role", "division", "personality", "expertise", "creative_tendencies", "research_methods", "decision_philosophy",
                  "communication_style", "strengths", "known_biases", "creative_specialization", "tools", "genre_affinities",
                  "evaluation_lens", "naming_style", "novelty_appetite", "risk_tolerance", "active")


def seed_personas(db: Session) -> int:
    """Insert missing seed personas. Never overwrites a persona a human has edited."""
    n = 0
    for p in SEED:
        if db.get(Persona, p["id"]) is None:
            db.add(Persona(**p))
            db.add(PersonaVersion(persona_id=p["id"], version=1, snapshot=p, changed_by="seed"))
            n += 1
    db.flush()
    return n


def persona_dict(p: Persona) -> dict[str, Any]:
    return {c.key: getattr(p, c.key) for c in Persona.__table__.columns}


def update_persona(db: Session, persona: Persona, changes: dict[str, Any], actor: str) -> Persona:
    for k, v in changes.items():
        if k in PERSONA_FIELDS:
            setattr(persona, k, v)
    persona.version += 1
    snap = {k: v for k, v in persona_dict(persona).items() if k != "updated_at"}
    db.add(PersonaVersion(persona_id=persona.id, version=persona.version, snapshot=snap, changed_by=actor))
    db.flush()
    return persona


def product_dict(p: Product) -> dict[str, Any]:
    rep = p.compliance_report or {}
    if not rep.get("checklist"):
        rep = compliance.assess(p.name, p.description, p.category, p.tags, non_eu_supplier=not (p.supplier and p.supplier.eu_based)).as_dict()
    return {"id": p.id, "name": p.name, "category": p.category, "tags": p.tags or [], "description": p.description, "net_margin": p.net_margin,
            "purchase_signal": p.purchase_signal, "engagement_signal": p.engagement_signal, "score_confidence": p.score_confidence,
            "compliance_status": p.compliance_status if p.compliance_status != "unreviewed" else rep.get("status", "unreviewed"),
            "compliance_restrictions": rep.get("restrictions", []), "compliance_blockers": rep.get("blockers", []),
            "mobility_class": rep.get("mobility_class"), "retail_price": p.retail_price, "competitor_prices": p.competitor_prices or [],
            "is_demo": p.is_demo, "trend_velocity": p.trend_velocity, "platforms_seen": p.platforms_seen or [],
            "opportunity_score": p.opportunity_score}


def profile_for(p: Product) -> ProductProfile:
    return profile_product(p.name, p.category, p.tags, p.description, p.retail_price, p.competitor_prices, p.marketing_potential)


def latest_economics(db: Session, pid: int) -> dict[str, Any]:
    for t in db.scalars(select(Task).where(Task.type == "cfo.economics", Task.status == "succeeded").order_by(Task.id.desc())).all():
        if t.payload.get("product_id") == pid and t.result:
            return t.result
    return {}


def usage_counts(db: Session) -> dict[str, int]:
    return {g.id: g.usage_count for g in db.scalars(select(CustomGenre)).all()}


def record_hybrid(db: Session, hybrid: dict[str, Any], origin: str = "fusion") -> None:
    g = db.get(CustomGenre, hybrid["id"])
    if g is None:
        db.add(CustomGenre(id=hybrid["id"], name=hybrid.get("name", hybrid["id"]), components=hybrid.get("components", hybrid["id"].split("+")),
                           data=hybrid, origin=origin, usage_count=1))
    else:
        g.usage_count += 1
    db.flush()


def learned(db: Session) -> dict[str, Any]:
    return learning.style_dna(db.scalars(select(Campaign)).all(), db.scalars(select(CampaignPerformance)).all(),
                              db.scalars(select(BrandConcept)).all())


def build_context(db: Session, pid: int) -> dict[str, Any]:
    p = db.get(Product, pid)
    if p is None:
        raise LookupError(f"product {pid} not found")
    prof = profile_for(p)
    pd = product_dict(p)
    text = f"{p.name} {p.category} {' '.join(p.tags or [])} {p.description}"
    econ = latest_economics(db, pid)
    dna = learned(db)
    return {"product_row": p, "product": pd, "profile": prof, "segments": field.match_segments(text),
            "innovation": M.innovation_lab(p.name, prof.tags), "economics": econ,
            "break_even_cac": (econ.get("economics") or {}).get("break_even_cac"), "usage": usage_counts(db),
            "learned": dna["genre"], "learned_identity": dna["identity"], "text": text}


def concept_dict(c: BrandConcept) -> dict[str, Any]:
    return {"id": c.id, "name": c.name, "tagline": c.tagline, "story": c.story, "usp": c.usp, "audience": c.audience,
            "palette": (c.direction or {}).get("color_palette", []), "primary_genre": c.primary_genre, "secondary_genre": c.secondary_genre,
            "evaluation": c.evaluation or {}, "originality": c.originality or {}, "hybrid": c.hybrid or {}, "direction": c.direction or {},
            "positioning": c.positioning, "product_id": c.product_id, "status": c.status, "version": c.version}


def save_concept(db: Session, concept: dict[str, Any], product_id: int | None, author: str, session_id: int | None = None,
                 parent: BrandConcept | None = None, source: str = "engine") -> BrandConcept:
    row = BrandConcept(
        product_id=product_id, author_persona=author, session_id=session_id, name=concept["name"], tagline=concept.get("tagline", ""),
        primary_genre=concept.get("primary_genre", ""), secondary_genre=concept.get("secondary_genre", ""), hybrid=concept.get("hybrid", {}),
        direction=concept.get("direction", {}), audience=concept.get("audience", ""), usp=concept.get("usp", ""), story=concept.get("story", ""),
        positioning=concept.get("positioning", "mid"), evaluation=concept.get("evaluation", {}), originality=concept.get("originality", {}),
        status=concept.get("status", "draft"), source=source, parent_id=parent.id if parent else None,
        version=(parent.version + 1) if parent else 1)
    db.add(row)
    db.flush()
    row.lineage_id = parent.lineage_id if parent else row.id
    if concept.get("hybrid", {}).get("id"):
        record_hybrid(db, {**concept["hybrid"], "components": [concept.get("primary_genre"), concept.get("secondary_genre")]})
    db.flush()
    return row


def save_graph(db: Session, graph: str, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
    db.query(GraphNode).filter(GraphNode.graph == graph).delete()
    db.query(GraphEdge).filter(GraphEdge.graph == graph).delete()
    for n in nodes:
        db.add(GraphNode(graph=graph, key=n["key"], kind=n.get("kind", "node"), label=n.get("label", n["key"])[:255], data=n.get("data", {})))
    for e in edges:
        db.add(GraphEdge(graph=graph, source=e["source"], target=e["target"], relation=e["relation"], data={"note": e.get("note", "")}))
    db.flush()


def load_graph(db: Session, graph: str) -> dict[str, Any]:
    nodes = db.scalars(select(GraphNode).where(GraphNode.graph == graph)).all()
    edges = db.scalars(select(GraphEdge).where(GraphEdge.graph == graph)).all()
    return {"graph": graph, "nodes": [{"key": n.key, "kind": n.kind, "label": n.label, "data": n.data} for n in nodes],
            "edges": [{"source": e.source, "target": e.target, "relation": e.relation, "note": (e.data or {}).get("note", "")} for e in edges]}
