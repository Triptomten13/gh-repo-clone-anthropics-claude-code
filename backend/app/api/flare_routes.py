"""REST API for Rocky Flare (creative intelligence) and Field Operations."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents.catalog import build_orchestrator
from ..agents.orchestrator import GovernanceError
from ..db import get_db
from ..flare import assets as A
from ..flare import campaigns as C
from ..flare import commercial as CM
from ..flare import field, learning, personalization, portfolio, sideways
from ..flare import genres as G
from ..flare import mutation as M
from ..flare import originality as O
from ..flare import personas as PS
from ..flare import service as S
from ..flare.taxonomy import GENRES, PRESET_HYBRIDS
from ..governance import core as gov
from ..models import (Agent, Approval, Brand, BrandConcept, Campaign, CampaignPerformance, CollaborationSession, CollaborationTurn,
                      CompatibilityRecord, CreativeAsset, CustomGenre, LedgerEntry, Persona, PersonaMemory, PersonaVersion, Product, Supplier,
                      Task, TrendObservation, User)
from ..security.auth import current_user, require_role
from .routes import row

router = APIRouter(prefix="/api")
orch = build_orchestrator()
operator = require_role("admin", "operator")
admin_only = require_role("admin")


def _404(obj: Any, what: str) -> Any:
    if obj is None:
        raise HTTPException(404, f"{what} not found")
    return obj


# =================================================================== run (submit + execute)
class RunIn(BaseModel):
    type: str
    payload: dict[str, Any] = {}


@router.post("/flare/run")
def run(r: RunIn, db: Session = Depends(get_db), user: User = Depends(operator)):
    """Submit an agent task and execute the queue now (synchronously). Returns the finished task,
    or a queued one if another worker is already draining (poll GET /api/tasks/{id})."""
    if not (r.type.startswith("flare.") or r.type.startswith("field.")):
        raise HTTPException(400, "only flare.* tasks via this endpoint; use /api/tasks for others")
    try:
        t = orch.submit(db, r.type, r.payload, requested_by=f"user:{user.email}", priority=5, force=True)
    except GovernanceError as e:
        raise HTTPException(409, str(e)) from e
    gov.audit(db, user.email, "task.submit", f"task:{t.id}", type=r.type)
    db.commit()
    orch.drain(400)
    db.expire_all()
    return row(db.get(Task, t.id))


# =================================================================== personas
def _persona_out(db: Session, p: Persona) -> dict[str, Any]:
    a = db.get(Agent, p.agent_id)
    mem = db.scalars(select(PersonaMemory).where(PersonaMemory.persona_id == p.id)).all()
    cal = learning.persona_calibration(mem).get(p.id, {"points": 0, "correlation": None})
    n = (a.tasks_succeeded + a.tasks_failed + a.tasks_blocked) if a else 0
    return {**S.persona_dict(p), "metrics": {
        "tasks": n, "success_rate": round(a.tasks_succeeded / n, 3) if a and n else None, "tokens_total": a.tokens_total if a else 0,
        "cost_usd": round(a.cost_total_usd, 4) if a else 0, "agent_status": a.status if a else None, "permission_level": a.permission_level if a else None,
        "competition_wins": sum(1 for m in mem if m.kind == "win"), "calibration": cal,
        "evaluations": db.query(CollaborationTurn).filter(CollaborationTurn.persona_id == p.id).count()}}


@router.get("/flare/personas")
def list_personas(division: str | None = None, db: Session = Depends(get_db), _: User = Depends(current_user)):
    q = select(Persona).order_by(Persona.division, Persona.name)
    if division:
        q = q.where(Persona.division == division)
    return [_persona_out(db, p) for p in db.scalars(q).all()]


@router.get("/flare/personas/{pid}")
def get_persona(pid: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    p = _404(db.get(Persona, pid), "persona")
    versions = db.scalars(select(PersonaVersion).where(PersonaVersion.persona_id == pid).order_by(PersonaVersion.version.desc())).all()
    memory = db.scalars(select(PersonaMemory).where(PersonaMemory.persona_id == pid).order_by(PersonaMemory.id.desc()).limit(50)).all()
    return {**_persona_out(db, p), "versions": [row(v) for v in versions], "memory": [row(m) for m in memory],
            "criteria": list(PS.CRITERIA), "lens_presets": PS.LENSES}


class PersonaPatch(BaseModel):
    personality: str | None = None
    role: str | None = None
    expertise: list[str] | None = None
    creative_tendencies: list[str] | None = None
    research_methods: list[str] | None = None
    decision_philosophy: str | None = None
    communication_style: str | None = Field(default=None, pattern="^(systematic|cynical|curious|skeptical|imaginative|practical|terse|warm|technical|scholarly|decisive)$")
    strengths: list[str] | None = None
    known_biases: list[str] | None = None
    creative_specialization: str | None = None
    genre_affinities: dict[str, float] | None = None
    evaluation_lens: dict[str, float] | None = None
    naming_style: str | None = Field(default=None, pattern="^(minimal|mythic|latin|single|nordic)$")
    novelty_appetite: float | None = Field(default=None, ge=0, le=1)
    risk_tolerance: float | None = Field(default=None, ge=0, le=1)
    active: bool | None = None


@router.patch("/flare/personas/{pid}")
def patch_persona(pid: str, body: PersonaPatch, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    p = _404(db.get(Persona, pid), "persona")
    changes = body.model_dump(exclude_none=True)
    if "genre_affinities" in changes:
        bad = [g for g in changes["genre_affinities"] if g not in GENRES]
        if bad:
            raise HTTPException(422, f"unknown genres: {bad}")
        changes["genre_affinities"] = {g: max(0.0, min(1.0, float(w))) for g, w in changes["genre_affinities"].items()}
    if "evaluation_lens" in changes:
        bad = [k for k in changes["evaluation_lens"] if k not in PS.CRITERIA]
        if bad:
            raise HTTPException(422, f"unknown criteria: {bad}")
        if sum(max(0.0, float(v)) for v in changes["evaluation_lens"].values()) <= 0:
            raise HTTPException(422, "lens needs at least one positive weight")
    S.update_persona(db, p, changes, user.email)
    gov.audit(db, user.email, "persona.update", f"persona:{pid}", fields=sorted(changes))
    db.commit()
    return _persona_out(db, p)


@router.post("/flare/personas/{pid}/reset")
def reset_persona(pid: str, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    p = _404(db.get(Persona, pid), "persona")
    seed = PS.SEED_BY_ID.get(pid)
    if not seed:
        raise HTTPException(404, "no seed for this persona")
    S.update_persona(db, p, {k: v for k, v in seed.items() if k in S.PERSONA_FIELDS}, user.email)
    gov.audit(db, user.email, "persona.reset", f"persona:{pid}")
    db.commit()
    return _persona_out(db, p)


# =================================================================== genres
@router.get("/flare/genres")
def list_genres(db: Session = Depends(get_db), _: User = Depends(current_user)):
    usage = S.usage_counts(db)
    custom = db.scalars(select(CustomGenre).order_by(CustomGenre.usage_count.desc())).all()
    return {"genres": [{"id": g.id, "name": g.name, "family": g.family, "pillar": g.pillar, "description": g.description, "palette": list(g.palette),
                        "typography": {"display": g.display_type, "text": g.text_type}, "materials": list(g.materials), "sensitivity": list(g.sensitivity),
                        "video_fit": g.video_fit, "recognition": g.recognition, "production_cost": g.production_cost,
                        "used_in_hybrids": sum(n for k, n in usage.items() if g.id in k.split("+"))} for g in GENRES.values()],
            "presets": [h.model_dump() for h in G.preset_hybrids()], "discovered": [row(c) for c in custom]}


class FuseIn(BaseModel):
    components: list[str] = Field(min_length=2, max_length=4)
    name: str | None = None


@router.post("/flare/genres/fuse")
def fuse(f: FuseIn, db: Session = Depends(get_db), user: User = Depends(operator)):
    bad = [c for c in f.components if c not in GENRES]
    if bad:
        raise HTTPException(422, f"unknown genres: {bad}")
    gs = [GENRES[c] for c in f.components]
    h = G.fuse(gs[0], gs[1], extras=gs[2:], usage=S.usage_counts(db), name=f.name)
    S.record_hybrid(db, h.model_dump(), origin="user")
    tm = O.trademark_prescreen(h.name)
    db.commit()
    return {**h.model_dump(), "trademark": tm, "originality_flags": O.check_name(h.name) + O.sensitivity_flags(h.name, f.components)}


@router.get("/flare/products/{pid}/genres")
def product_genres(pid: int, n: int = Query(6, ge=5, le=12), db: Session = Depends(get_db), _: User = Depends(current_user)):
    try:
        c = S.build_context(db, pid)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    return {"profile": {"tags": c["profile"].tags, "tier": c["profile"].tier, "category_typical": list(c["profile"].category_typical)},
            "matches": [m.model_dump() for m in G.match_genres(c["profile"], c["learned"], top=12)],
            "directions": [d.model_dump() for d in G.creative_directions(c["profile"], n=n, learned=c["learned"], usage=c["usage"])],
            "segments": c["segments"], "pillars": field.classify_pillars(c["text"])}


# =================================================================== concepts
@router.get("/flare/concepts")
def list_concepts(product_id: int | None = None, status: str | None = None, session_id: int | None = None, latest_only: bool = True,
                  db: Session = Depends(get_db), _: User = Depends(current_user)):
    q = select(BrandConcept).order_by(BrandConcept.id.desc())
    if product_id:
        q = q.where(BrandConcept.product_id == product_id)
    if status:
        q = q.where(BrandConcept.status == status)
    if session_id:
        q = q.where(BrandConcept.session_id == session_id)
    rows = db.scalars(q).all()
    if latest_only:
        seen, out = set(), []
        for c in rows:
            if c.lineage_id not in seen:
                seen.add(c.lineage_id)
                out.append(c)
        rows = out
    return [{**row(c), "product_name": (db.get(Product, c.product_id).name if c.product_id else None)} for c in rows[:300]]


@router.get("/flare/concepts/{cid}")
def get_concept(cid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    c = _404(db.get(BrandConcept, cid), "concept")
    versions = db.scalars(select(BrandConcept).where(BrandConcept.lineage_id == c.lineage_id).order_by(BrandConcept.version)).all()
    assets = db.scalars(select(CreativeAsset).where(CreativeAsset.concept_id.in_([v.id for v in versions])).order_by(CreativeAsset.id.desc())).all()
    turns = db.scalars(select(CollaborationTurn).order_by(CollaborationTurn.id)).all()
    reviews = [row(t) for t in turns if (t.scores or {}).get("concept_id") == cid]
    reuse = learning.creative_reuse([c.primary_genre, c.secondary_genre], c.brand_id, db.scalars(select(CreativeAsset)).all(),
                                    db.scalars(select(Campaign)).all())
    return {**row(c), "versions": [{"id": v.id, "version": v.version, "name": v.name, "status": v.status,
                                     "originality": (v.originality or {}).get("score")} for v in versions],
            "assets": [row(a) for a in assets], "reviews": reviews, "reuse_suggestions": reuse}


class ConceptIn(BaseModel):
    product_id: int | None = None
    name: str
    tagline: str = ""
    primary_genre: str
    secondary_genre: str
    audience: str = ""
    usp: str = ""
    story: str = ""
    palette: list[str] = []


@router.post("/flare/concepts")
def create_concept(body: ConceptIn, db: Session = Depends(get_db), user: User = Depends(operator)):
    if body.primary_genre not in GENRES or body.secondary_genre not in GENRES:
        raise HTTPException(422, "unknown genre")
    gp, gs = GENRES[body.primary_genre], GENRES[body.secondary_genre]
    h = G.fuse(gp, gs, name=body.name)
    d = body.model_dump()
    d["hybrid"] = {"id": h.id, "name": body.name}
    d["direction"] = {"primary_genre": gp.name, "secondary_genre": gs.name, "color_palette": body.palette or h.palette, "typography": h.typography,
                      "visual_direction": h.graphic_language, "materials_textures": h.materials, "photography_style": h.photography_direction,
                      "packaging_style": h.packaging_direction, "website_language": gp.web, "social_identity": gp.social,
                      "advertising_direction": h.marketing_identity}
    d["palette"] = d["direction"]["color_palette"]
    p = db.get(Product, body.product_id) if body.product_id else None
    tags = list(S.profile_for(p).tags) if p else []
    rep = O.score_concept(d, tags, net_margin=p.net_margin if p else None)
    d["originality"] = rep.model_dump()
    d["status"] = "needs_revision" if rep.requires_revision else "draft"
    c = S.save_concept(db, d, body.product_id, f"user:{user.email}", source="human")
    gov.audit(db, user.email, "concept.create", f"concept:{c.id}")
    db.commit()
    return row(c)


class OriginalityIn(BaseModel):
    concept: dict[str, Any]
    category_tags: list[str] = []


@router.post("/flare/originality")
def originality(body: OriginalityIn, _: User = Depends(current_user)):
    return O.score_concept(body.concept, body.category_tags).model_dump()


class CompareIn(BaseModel):
    ids: list[int] = Field(min_length=2, max_length=6)


@router.post("/flare/concepts/compare")
def compare(body: CompareIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    out = []
    for i in body.ids:
        c = _404(db.get(BrandConcept, i), f"concept {i}")
        ps = c.panel_scores or {}
        out.append({"id": c.id, "name": c.name, "version": c.version, "author": c.author_persona, "status": c.status,
                    "genres": [GENRES[c.primary_genre].name if c.primary_genre in GENRES else c.primary_genre,
                               GENRES[c.secondary_genre].name if c.secondary_genre in GENRES else c.secondary_genre],
                    "palette": (c.direction or {}).get("color_palette", []), "positioning": c.positioning, "evaluation": c.evaluation,
                    "originality": (c.originality or {}).get("score"), "originality_components": (c.originality or {}).get("components", {}),
                    "flags": [f["code"] for f in (c.originality or {}).get("flags", [])],
                    "panel_mean": round(sum(ps.values()) / len(ps), 1) if ps else None, "panel_scores": ps})
    return out


class StatusIn(BaseModel):
    status: str = Field(pattern="^(shortlisted|approved|rejected|draft)$")
    note: str = ""


@router.post("/flare/concepts/{cid}/status")
def concept_status(cid: int, body: StatusIn, db: Session = Depends(get_db), user: User = Depends(operator)):
    c = _404(db.get(BrandConcept, cid), "concept")
    if body.status == "approved":
        if user.role != "admin":
            raise HTTPException(403, "only an admin can approve a brand concept")
        if (c.originality or {}).get("requires_revision", True):
            raise HTTPException(409, "concept fails the anti-generic gate — revise it first")
    c.status = body.status
    gov.audit(db, user.email, f"concept.{body.status}", f"concept:{cid}", note=body.note)
    db.commit()
    return row(c)


# =================================================================== assets
@router.get("/flare/assets")
def list_assets(concept_id: int | None = None, kind: str | None = None, q: str | None = None, latest_only: bool = True,
                db: Session = Depends(get_db), _: User = Depends(current_user)):
    stmt = select(CreativeAsset).order_by(CreativeAsset.id.desc())
    if concept_id:
        stmt = stmt.where(CreativeAsset.concept_id == concept_id)
    if kind:
        stmt = stmt.where(CreativeAsset.kind == kind)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(CreativeAsset.title.ilike(like) | CreativeAsset.prompt.ilike(like) | CreativeAsset.kind.ilike(like))
    rows = db.scalars(stmt.limit(500)).all()
    if latest_only:
        seen, out = set(), []
        for a in rows:
            if a.lineage_id not in seen:
                seen.add(a.lineage_id)
                out.append(a)
        rows = out
    return [row(a) for a in rows]


@router.get("/flare/assets/{aid}/versions")
def asset_versions(aid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    a = _404(db.get(CreativeAsset, aid), "asset")
    return [row(x) for x in db.scalars(select(CreativeAsset).where(CreativeAsset.lineage_id == a.lineage_id).order_by(CreativeAsset.version)).all()]


class AssetStatus(BaseModel):
    status: str = Field(pattern="^(approved|rejected|draft)$")


@router.post("/flare/assets/{aid}/status")
def asset_status(aid: int, body: AssetStatus, db: Session = Depends(get_db), user: User = Depends(operator)):
    a = _404(db.get(CreativeAsset, aid), "asset")
    a.status = body.status
    gov.audit(db, user.email, f"asset.{body.status}", f"asset:{aid}")
    db.commit()
    return row(a)


@router.get("/flare/providers")
def providers(_: User = Depends(current_user)):
    return A.provider_status()


# =================================================================== brands / portfolio
def _brand_metrics(db: Session) -> list[dict[str, Any]]:
    brands = db.scalars(select(Brand)).all()
    prods = db.scalars(select(Product)).all()
    ledger = db.scalars(select(LedgerEntry)).all()
    camps = db.scalars(select(Campaign)).all()
    perf = db.scalars(select(CampaignPerformance)).all()
    obs = db.scalars(select(TrendObservation)).all()
    out = []
    for b in brands:
        sups = {p.supplier_id for p in prods if p.brand_id == b.id and p.supplier_id}
        out.append({**portfolio.metrics(b, prods, ledger, camps, perf, obs, sups), "genre_dna": b.genre_dna, "trademark_status": b.trademark_status,
                    "audience": b.audience, "positioning": b.positioning, "segments": b.segments, "categories": b.categories})
    return out


@router.get("/flare/brands")
def list_brands(db: Session = Depends(get_db), _: User = Depends(current_user)):
    m = _brand_metrics(db)
    return {"brands": m, "extensions": portfolio.extension_opportunities(m, db.scalars(select(Brand)).all(), db.scalars(select(Product)).all())}


class BrandIn(BaseModel):
    concept_id: int
    force: bool = False
    reason: str = ""


@router.post("/flare/brands")
def create_brand(body: BrandIn, db: Session = Depends(get_db), user: User = Depends(operator)):
    c = _404(db.get(BrandConcept, body.concept_id), "concept")
    if c.status != "approved":
        raise HTTPException(409, "only approved concepts can become brands")
    p = db.get(Product, c.product_id) if c.product_id else None
    text = f"{p.name} {p.category} {' '.join(p.tags or [])}" if p else c.name
    segs = {s["id"] for s in field.match_segments(text)}
    cats = {p.category} if p and p.category else set()
    overlaps = portfolio.overlap_check({"genres": {c.primary_genre, c.secondary_genre}, "segments": segs, "categories": cats},
                                       db.scalars(select(Brand)).all())
    if overlaps and not (body.force and len(body.reason) >= 10):
        raise HTTPException(409, {"message": "overlaps an existing brand", "overlaps": overlaps,
                                  "hint": "add the product to that brand, or pass force=true with a reason (≥10 chars)"})
    b = Brand(name=c.name, concept_id=c.id, genre_dna={"genres": [c.primary_genre, c.secondary_genre], "hybrid": c.hybrid, "direction": c.direction},
              audience=c.audience, segments=sorted(segs), categories=sorted(cats), positioning=c.positioning,
              trademark_note="; ".join(h["note"] for h in (c.originality or {}).get("trademark", {}).get("hits", [])))
    db.add(b)
    db.flush()
    c.brand_id = b.id
    if p and p.brand_id is None:
        p.brand_id = b.id
    gov.audit(db, user.email, "brand.create", f"brand:{b.id}", concept=c.id, forced=body.force, reason=body.reason)
    db.commit()
    return row(b)


class BrandPatch(BaseModel):
    trademark_status: str | None = Field(default=None, pattern="^(pending|clear|conflict)$")
    trademark_note: str | None = None
    website: str | None = None
    marketing_strategy: str | None = None
    social_strategy: str | None = None
    status: str | None = Field(default=None, pattern="^(concept|retired)$")


@router.patch("/flare/brands/{bid}")
def patch_brand(bid: int, body: BrandPatch, db: Session = Depends(get_db), user: User = Depends(operator)):
    b = _404(db.get(Brand, bid), "brand")
    ch = body.model_dump(exclude_none=True)
    if "trademark_status" in ch and user.role != "admin":
        raise HTTPException(403, "only an admin records trademark search results")
    if ch.get("trademark_status") == "clear" and len(ch.get("trademark_note") or b.trademark_note or "") < 10:
        raise HTTPException(400, "record the search evidence (registry, query, date) in trademark_note")
    for k, v in ch.items():
        setattr(b, k, v)
    gov.audit(db, user.email, "brand.update", f"brand:{bid}", **ch)
    db.commit()
    return row(b)


@router.post("/flare/brands/{bid}/products/{pid}")
def assign_product(bid: int, pid: int, db: Session = Depends(get_db), user: User = Depends(operator)):
    b = _404(db.get(Brand, bid), "brand")
    p = _404(db.get(Product, pid), "product")
    p.brand_id = b.id
    if p.category and p.category not in (b.categories or []):
        b.categories = [*(b.categories or []), p.category]
    gov.audit(db, user.email, "brand.assign_product", f"brand:{bid}", product=pid)
    db.commit()
    return {"brand_id": bid, "product_id": pid}


@router.post("/flare/brands/{bid}/request-launch")
def request_brand_launch(bid: int, db: Session = Depends(get_db), user: User = Depends(operator)):
    b = _404(db.get(Brand, bid), "brand")
    if b.trademark_status != "clear":
        raise HTTPException(409, "trademark search must be recorded as clear by an admin first")
    a = gov.request_approval(db, "brand.launch", f"Launch brand '{b.name}'", f"user:{user.email}", b.positioning, {"brand_id": b.id})
    db.commit()
    return row(a)


@router.post("/flare/brands/{bid}/activate")
def activate_brand(bid: int, db: Session = Depends(get_db), user: User = Depends(operator)):
    b = _404(db.get(Brand, bid), "brand")
    ok = [a for a in db.scalars(select(Approval).where(Approval.action == "brand.launch", Approval.status == "approved")).all()
          if a.payload.get("brand_id") == bid]
    if not ok:
        raise HTTPException(403, "brand launch requires an approved LEVEL 4 approval")
    b.status = "live"
    gov.audit(db, user.email, "brand.activate", f"brand:{bid}")
    db.commit()
    return row(b)


# =================================================================== campaigns & learning
@router.get("/flare/campaigns")
def list_campaigns(product_id: int | None = None, db: Session = Depends(get_db), _: User = Depends(current_user)):
    q = select(Campaign).order_by(Campaign.id.desc())
    if product_id:
        q = q.where(Campaign.product_id == product_id)
    return [row(c) for c in db.scalars(q).all()]


class PerfIn(BaseModel):
    period_start: datetime
    impressions: int = Field(ge=0, default=0)
    clicks: int = Field(ge=0, default=0)
    engagements: int = Field(ge=0, default=0)
    spend: float = Field(ge=0, default=0)
    orders: int = Field(ge=0, default=0)
    revenue: float = Field(ge=0, default=0)
    contribution: float | None = None
    source: str = "manual"


@router.post("/flare/campaigns/{cid}/performance")
def add_performance(cid: int, rows_in: list[PerfIn], db: Session = Depends(get_db), user: User = Depends(operator)):
    _404(db.get(Campaign, cid), "campaign")
    for r in rows_in:
        db.add(CampaignPerformance(campaign_id=cid, **r.model_dump()))
    gov.audit(db, user.email, "campaign.performance", f"campaign:{cid}", rows=len(rows_in))
    db.commit()
    t = orch.submit(db, "flare.campaign_analysis", {"rev": datetime.now(timezone.utc).isoformat()}, requested_by=f"user:{user.email}", priority=5)
    db.commit()
    orch.drain(20)
    return {"recorded": len(rows_in), "analysis_task": t.id}


@router.post("/flare/campaigns/{cid}/request-launch")
def request_campaign_launch(cid: int, db: Session = Depends(get_db), user: User = Depends(operator)):
    c = _404(db.get(Campaign, cid), "campaign")
    if c.flags:
        raise HTTPException(409, f"campaign has open quality flags: {c.flags}")
    a = gov.request_approval(db, "campaign.launch", f"Launch campaign '{c.name}'", f"user:{user.email}",
                             f"{c.hook}\n{c.message}", {"campaign_id": c.id}, c.budget_recommendation_sek)
    c.status = "pending_approval"
    db.commit()
    return row(a)


@router.get("/flare/campaigns/analysis")
def campaign_analysis(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return {**C.analyse(db.scalars(select(Campaign)).all(), db.scalars(select(CampaignPerformance)).all()), "identities": C.IDENTITIES}


@router.get("/flare/style-dna")
def style_dna(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return S.learned(db)


@router.get("/flare/genre-evolution")
def genre_evolution(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return learning.genre_evolution(db.scalars(select(CampaignPerformance)).all(), db.scalars(select(Campaign)).all(),
                                    db.scalars(select(TrendObservation).where(TrendObservation.keyword.like("aesthetic:%"))).all())


# =================================================================== collaboration
@router.get("/flare/sessions")
def list_sessions(kind: str | None = None, product_id: int | None = None, db: Session = Depends(get_db), _: User = Depends(current_user)):
    q = select(CollaborationSession).order_by(CollaborationSession.id.desc())
    if kind:
        q = q.where(CollaborationSession.kind == kind)
    if product_id:
        q = q.where(CollaborationSession.product_id == product_id)
    return [{**row(s), "turns": db.query(CollaborationTurn).filter(CollaborationTurn.session_id == s.id).count()} for s in db.scalars(q.limit(200)).all()]


@router.get("/flare/sessions/{sid}")
def get_session(sid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    s = _404(db.get(CollaborationSession, sid), "session")
    turns = db.scalars(select(CollaborationTurn).where(CollaborationTurn.session_id == sid).order_by(CollaborationTurn.id)).all()
    names = {p.id: p.name for p in db.scalars(select(Persona)).all()}
    return {**row(s), "turns": [{**row(t), "persona_name": names.get(t.persona_id, t.persona_id)} for t in turns],
            "concepts": [row(c) for c in db.scalars(select(BrandConcept).where(BrandConcept.id.in_(s.concept_ids or []))).all()]}


# =================================================================== think sideways & commercial
@router.get("/flare/challenges")
def challenges(_: User = Depends(current_user)):
    return {"challenges": sideways.CHALLENGES, "modules": CM.MODULES,
            "questions": ["What else could we do with this product?", "Find five completely unexpected markets for this idea.",
                          "Turn this ordinary product into a premium brand.", "Create a business ecosystem around this niche.",
                          "Find a business model nobody in this market seems to be using.", "Give this product three radically different identities.",
                          "Find ways to monetize the audience rather than the product."]}


@router.get("/flare/graphs/{graph}")
def graph(graph: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return S.load_graph(db, graph)


class PersonalizationIn(BaseModel):
    fields: list[dict[str, Any]]


@router.post("/flare/personalization/validate")
def personalization_validate(body: PersonalizationIn, _: User = Depends(current_user)):
    return personalization.validate_fields(body.fields)


# =================================================================== FIELD OPERATIONS
def _ptext(p: Product) -> str:
    return f"{p.name} {p.category} {' '.join(p.tags or [])} {p.description}"


@router.get("/field/overview")
def field_overview(db: Session = Depends(get_db), _: User = Depends(current_user)):
    prods = db.scalars(select(Product)).all()
    subs = {k: sum(1 for p in prods if field.matches_subsection(_ptext(p), k)) for k in field.SUBSECTIONS}
    pillar_counts = {k: sum(1 for p in prods if k in field.classify_pillars(_ptext(p))) for k in field.PILLARS}
    return {"pillars": {k: {"label": v["label"], "products": pillar_counts[k]} for k, v in field.PILLARS.items()}, "subsections": subs,
            "segments": len(field.SEGMENTS), "ecosystems": list(field.ECOSYSTEMS),
            "brands": db.query(Brand).count(), "concepts": db.query(BrandConcept).count(),
            "councils": db.query(CollaborationSession).filter(CollaborationSession.kind == "council").count()}


@router.get("/field/products")
def field_products(sub: str = "tactical", db: Session = Depends(get_db), _: User = Depends(current_user)):
    if sub not in field.SUBSECTIONS:
        raise HTTPException(404, "unknown subsection")
    out = []
    for p in db.scalars(select(Product)).all():
        if field.matches_subsection(_ptext(p), sub):
            pd = S.product_dict(p)
            out.append({**{k: pd[k] for k in ("id", "name", "category", "compliance_status", "mobility_class", "net_margin", "opportunity_score", "is_demo")},
                        "score_confidence": p.score_confidence, "pillars": list(field.classify_pillars(_ptext(p))),
                        "compatibility_verified": db.query(CompatibilityRecord).filter(CompatibilityRecord.product_id == p.id,
                                                                                       CompatibilityRecord.status == "verified").count()})
    return sorted(out, key=lambda r: r["opportunity_score"] or -1, reverse=True)


@router.get("/field/segments")
def field_segments(_: User = Depends(current_user)):
    return [{"id": k, **v, "epistemic": "hypothesis"} for k, v in field.SEGMENTS.items()]


@router.get("/field/ecosystems")
def field_ecosystems(db: Session = Depends(get_db), _: User = Depends(current_user)):
    prods = db.scalars(select(Product)).all()
    return {"ecosystems": [field.build_ecosystem(t, prods) for t in field.ECOSYSTEMS], "mounting_standards": field.MOUNTING_STANDARDS}


@router.get("/field/suppliers")
def field_suppliers(product_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    p = _404(db.get(Product, product_id), "product")
    return field.sourcing_assessment(_ptext(p), db.scalars(select(Supplier)).all())


@router.get("/field/innovation/{pid}")
def field_innovation(pid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    p = _404(db.get(Product, pid), "product")
    prof = S.profile_for(p)
    nodes, edges = M.mutate(p.name, p.category, p.tags, p.supplier, p.retail_price, prof.tags)
    return {"innovation": M.innovation_lab(p.name, prof.tags), "mutations": [n.model_dump() for n in nodes], "edges": [e.model_dump() for e in edges]}


@router.get("/field/archive")
def field_archive(_: User = Depends(current_user)):
    d = [g for g in GENRES.values() if g.pillar == "D"]
    return {"genres": [{"id": g.id, "name": g.name, "description": g.description, "palette": list(g.palette), "graphic_language": g.graphic_language,
                        "materials": list(g.materials), "vocab": list(g.vocab), "sensitivity": list(g.sensitivity)} for g in d],
            "presets": [h.model_dump() for h in G.preset_hybrids()],
            "rules": ["Treat conspiracy themes as clearly fictional; never present them as fact.",
                      "No real agency names, seals or insignia.", "Sacred names and symbols: understated, respectful, human review.",
                      "Avoid symbols co-opted by extremist movements."],
            "preset_trademark_checks": {p["name"]: O.trademark_prescreen(p["name"]) for p in PRESET_HYBRIDS}}


@router.get("/field/compatibility")
def list_compat(product_id: int | None = None, db: Session = Depends(get_db), _: User = Depends(current_user)):
    q = select(CompatibilityRecord).order_by(CompatibilityRecord.id.desc())
    if product_id:
        q = q.where(CompatibilityRecord.product_id == product_id)
    return [row(c) for c in db.scalars(q).all()]


class CompatIn(BaseModel):
    product_id: int
    target: str = Field(min_length=2)
    target_kind: str = Field(default="vehicle_model", pattern="^(vehicle_model|mount_standard)$")
    status: str = Field(default="unverified", pattern="^(unverified|supplier_claimed|verified|incompatible)$")
    evidence: str = ""


@router.post("/field/compatibility")
def add_compat(body: CompatIn, db: Session = Depends(get_db), user: User = Depends(operator)):
    _404(db.get(Product, body.product_id), "product")
    if body.status in ("verified", "incompatible") and len(body.evidence.strip()) < 15:
        raise HTTPException(400, "verified/incompatible status requires evidence (test description, date, model/year)")
    rec = CompatibilityRecord(**body.model_dump(), verified_by=user.email if body.status == "verified" else "")
    db.add(rec)
    db.flush()
    gov.audit(db, user.email, "compatibility.record", f"product:{body.product_id}", compat_target=body.target, status=body.status)
    db.commit()
    return row(rec)
