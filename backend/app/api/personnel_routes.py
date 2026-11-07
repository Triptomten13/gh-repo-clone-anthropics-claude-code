"""Personnel register, The Bestiary, specializations, departments and the Custom Agent Creator.

Permissions: any signed-in user reads the register and the Bestiary; `work.run` asks for designs, previews and
validation (model calls are budgeted and traced); `agent.develop` creates, edits, onboards, tests and changes the
lifecycle of agents and adds Bestiary entries, specializations and departments. Raising an agent's permission level is
a RESTRICTED approval applied from Approvals; tool access is granted only through `/api/tools/grants`. Every
state-changing call is audited.
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import SessionLocal, get_db
from ..governance import core as gov
from ..models import Agent, AgentRelationship, Department, Species, Specialization, User
from ..personnel import creator as C
from ..personnel import personnel_data as P
from ..personnel import registry as R
from ..security.auth import current_user
from ..security.rbac import has, require_permission

router = APIRouter(prefix="/api", tags=["personnel"])


def _cols(o: Any, skip: tuple[str, ...] = ()) -> dict[str, Any]:
    return {c.name: getattr(o, c.name) for c in o.__table__.columns if c.name not in skip}


def _err(e: C.CreatorError) -> HTTPException:
    return HTTPException(e.status, {"message": str(e), "errors": e.errors})


def _agent(db: Session, aid: str) -> Agent:
    a = db.get(Agent, aid)
    if a is None:
        raise HTTPException(404, f"no agent {aid}")
    return a


# ================================================================================================ personnel
@router.get("/personnel")
def personnel_list(q: str = "", department: str = "", specialization: str = "", species: str = "", status: str = "",
                   sort: Literal["name", "rank", "performance", "activity"] = "name", include_archived: bool = False,
                   db: Session = Depends(get_db), _: User = Depends(current_user)):
    return {"agents": R.list_cards(db, q=q, department=department, specialization=specialization, species=species,
                                   status=status, sort=sort, include_archived=include_archived),
            "facets": R.facets(db), "note": "One register for every agent. Filters narrow it; nothing groups agents by race."}


@router.get("/personnel/meta")
def personnel_meta(db: Session = Depends(get_db), _: User = Depends(current_user)):
    from ..governance.tool_gateway import TOOLS

    return {"ranks": P.RANKS, "traits": P.TRAITS, "communication_styles": P.COMM_STYLES, "skill_levels": P.SKILL_LEVELS,
            "skill_basis": P.SKILL_BASIS, "lifecycle": P.LIFECYCLE, "sources": P.SOURCES, "languages": P.LANGUAGES,
            "relationship_types": P.RELATIONSHIP_TYPES, "duplicate_choices": list(C.DUPLICATE_CHOICES),
            "max_request_level": C.MAX_REQUEST_LEVEL, "default_level": C.DEFAULT_LEVEL, "trace_warning": P.TRACE_WARNING,
            "tools": [{"name": t.name, "operation": t.operation, "description": t.description} for t in TOOLS.values()],
            "departments": [{"key": d.key, "name": d.name} for d in db.scalars(select(Department).order_by(Department.name))],
            "specializations": [{"key": s.key, "name": s.name, "user_created": s.user_created}
                                for s in db.scalars(select(Specialization).order_by(Specialization.name))],
            "fields": list(C.FIELDS)}


@router.get("/personnel/hierarchy")
def personnel_hierarchy(db: Session = Depends(get_db), _: User = Depends(current_user)):
    lk = R.Lookups(db)
    rows = list(db.scalars(select(Agent).where(Agent.lifecycle != "ARCHIVED")))
    kids: dict[str | None, list[Agent]] = {}
    ids = {a.id for a in rows}
    for a in rows:
        kids.setdefault(a.supervisor_id if a.supervisor_id in ids else None, []).append(a)

    def node(a: Agent, depth: int = 0) -> dict[str, Any]:
        c = R.card(a, lk)
        return {"id": a.id, "display": c["display"], "title": c["title"], "rank": a.rank, "lifecycle": a.lifecycle,
                "species": c["species"], "department": c["department"],
                "children": [node(k, depth + 1) for k in sorted(kids.get(a.id, []), key=lambda x: x.persona_name)] if depth < 12 else []}

    roots = sorted(kids.get(None, []), key=lambda a: (a.id != "gsus", a.persona_name))
    return {"roots": [node(a) for a in roots], "note": "Every agent reports — directly or through its supervisor — to G-SUS."}


@router.get("/personnel/{aid}")
def personnel_profile(aid: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return R.profile(db, _agent(db, aid))


# ================================================================================================ creator
class IdeaIn(BaseModel):
    idea: str = Field("", max_length=2000)
    prefill: dict[str, Any] = {}
    alternatives: int = Field(1, ge=1, le=3)
    use_model: bool = True
    source: Literal["GSUS_CHAT", "BESTIARY", "PERSONNEL", "API", "ADMIN"] = "API"


class SpecIn(BaseModel):
    spec: dict[str, Any]
    exclude_id: str | None = None


class FieldIn(BaseModel):
    field: str
    spec: dict[str, Any] = {}
    idea: str = Field("", max_length=2000)
    use_model: bool = True


class CreateIn(BaseModel):
    spec: dict[str, Any]
    source: Literal["GSUS_CHAT", "BESTIARY", "PERSONNEL", "API", "ADMIN"] = "API"
    confirmed: bool = True
    duplicate_choice: Literal["use_existing", "extend", "complement", "new"] | None = None
    extend_id: str | None = None
    draft_id: str | None = None
    use_model: bool = True
    gsus_run_id: int | None = None


class DraftIn(BaseModel):
    spec: dict[str, Any]
    source: Literal["GSUS_CHAT", "BESTIARY", "PERSONNEL", "API", "ADMIN"] = "API"
    draft_id: str | None = None


@router.post("/personnel/design")
def creator_design(body: IdeaIn, db: Session = Depends(get_db), _: User = Depends(require_permission("work.run"))):
    out = C.design(db, body.idea, prefill=body.prefill, alternatives=body.alternatives, use_model=body.use_model, source=body.source)
    db.commit()
    return out


@router.post("/personnel/generate")
def creator_generate(body: FieldIn, db: Session = Depends(get_db), _: User = Depends(require_permission("work.run"))):
    try:
        out = C.generate_field(db, body.field, body.spec, body.idea, use_model=body.use_model)
    except C.CreatorError as e:
        raise _err(e) from e
    db.commit()
    return out


@router.post("/personnel/preview")
def creator_preview(body: SpecIn, db: Session = Depends(get_db), _: User = Depends(require_permission("work.run"))):
    return C.preview(db, body.spec, body.exclude_id) | {"duplicates": C.duplicates(db, body.spec, body.exclude_id)}


@router.post("/personnel/validate")
def creator_validate(body: SpecIn, db: Session = Depends(get_db), _: User = Depends(require_permission("work.run"))):
    return C.validate(db, body.spec, body.exclude_id) | {"duplicates": C.duplicates(db, body.spec, body.exclude_id)}


@router.post("/personnel/drafts")
def creator_draft(body: DraftIn, db: Session = Depends(get_db), user: User = Depends(require_permission("agent.develop"))):
    try:
        a = C.save_draft(db, body.spec, source=body.source, actor=user.email, draft_id=body.draft_id)
    except C.CreatorError as e:
        raise _err(e) from e
    db.commit()
    return {"agent": R.card(a, R.Lookups(db)), "spec": (a.onboarding or {}).get("draft_spec")}


def _onboard_later(aid: str, actor: str, use_model: bool) -> None:
    db = SessionLocal()
    try:
        a = db.get(Agent, aid)
        if a is not None and a.lifecycle == "READY":
            C.onboard(db, a, actor=actor, use_model=use_model)
            db.commit()
    finally:
        db.close()


@router.post("/personnel/agents")
def creator_create(body: CreateIn, bg: BackgroundTasks, db: Session = Depends(get_db),
                   user: User = Depends(require_permission("agent.develop"))):
    """THE creation endpoint for every entry point (GSUS_CHAT, BESTIARY, PERSONNEL, API, ADMIN)."""
    from ..ai.llm import get_provider

    slow = body.use_model and getattr(get_provider(), "name", "none") != "none"  # model probes run after the response
    try:
        out = C.create(db, body.spec, source=body.source, actor=user.email, confirmed=body.confirmed,
                       duplicate_choice=body.duplicate_choice, extend_id=body.extend_id, draft_id=body.draft_id,
                       onboard_now=not slow, use_model=body.use_model, gsus_run_id=body.gsus_run_id)
    except C.CreatorError as e:
        db.rollback()
        raise _err(e) from e
    db.commit()
    if slow and out.get("outcome") == "created":
        bg.add_task(_onboard_later, out["agent"]["id"], user.email, True)
    return out


@router.get("/personnel/agents/{aid}/status")
def creator_status(aid: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    a = _agent(db, aid)
    ob = a.onboarding or {}
    appr = None
    if ob.get("elevation_approval_id"):
        from ..models import Approval

        ap = db.get(Approval, ob["elevation_approval_id"])
        appr = {"id": ap.id, "status": ap.status, "consumed": ap.consumed_at is not None} if ap else None
    return {"id": a.id, "lifecycle": a.lifecycle, "status": a.status, "permission_level": a.permission_level, "version": a.version,
            "pipeline": ob.get("pipeline", []), "tests": ob.get("tests"), "checklist": ob.get("checklist"),
            "evaluation_tasks": ob.get("evaluation_tasks", []), "elevation": appr, "source": a.source}


@router.post("/personnel/agents/{aid}/onboarding")
def creator_onboard(aid: str, use_model: bool = True, db: Session = Depends(get_db),
                    user: User = Depends(require_permission("agent.develop"))):
    a = _agent(db, aid)
    if not a.custom or a.lifecycle not in ("READY", "FAILED"):
        raise HTTPException(409, f"onboarding runs for custom agents that are READY or FAILED (this one is {a.lifecycle})")
    out = C.onboard(db, a, actor=user.email, use_model=use_model)
    db.commit()
    return out


@router.post("/personnel/agents/{aid}/test")
def creator_test(aid: str, use_model: bool = True, db: Session = Depends(get_db),
                 user: User = Depends(require_permission("agent.develop"))):
    """Run Test: record capability-check results without changing the lifecycle (no automatic Expert status)."""
    a = _agent(db, aid)
    tests = C.run_tests(db, a, use_model=use_model)
    ob = dict(a.onboarding or {})
    ob["test_runs"] = [*(ob.get("test_runs") or [])[-9:], {k: tests[k] for k in ("ran_at", "passed", "failed", "skipped", "model")}]
    ob["tests"] = tests
    a.onboarding = ob
    gov.audit(db, user.email, "personnel.test", f"agent:{aid}", passed=tests["passed"], failed=tests["failed"], skipped=tests["skipped"])
    db.commit()
    return tests


class PatchIn(BaseModel):
    changes: dict[str, Any]
    note: str = Field("", max_length=250)


@router.patch("/personnel/agents/{aid}")
def creator_update(aid: str, body: PatchIn, db: Session = Depends(get_db), user: User = Depends(require_permission("agent.develop"))):
    try:
        a = C.update(db, _agent(db, aid), body.changes, actor=user.email, note=body.note)
    except C.CreatorError as e:
        db.rollback()
        raise _err(e) from e
    db.commit()
    return R.profile(db, a)


class LifecycleIn(BaseModel):
    action: Literal["pause", "resume", "disable", "archive", "submit"]
    reason: str = Field("", max_length=300)


@router.post("/personnel/agents/{aid}/lifecycle")
def creator_lifecycle(aid: str, body: LifecycleIn, db: Session = Depends(get_db),
                      user: User = Depends(require_permission("agent.develop"))):
    try:
        a = C.set_lifecycle(db, _agent(db, aid), body.action, actor=user.email, reason=body.reason)
    except C.CreatorError as e:
        db.rollback()
        raise _err(e) from e
    db.commit()
    return {"id": a.id, "lifecycle": a.lifecycle, "status": a.status, "version": a.version}


@router.post("/personnel/agents/{aid}/evaluate")
def creator_evaluate(aid: str, bg: BackgroundTasks, db: Session = Depends(get_db),
                     user: User = Depends(require_permission("agent.develop"))):
    try:
        ids = C.evaluate(db, _agent(db, aid), actor=user.email)
    except C.CreatorError as e:
        raise _err(e) from e
    db.commit()
    from ..agents.catalog import build_orchestrator

    bg.add_task(build_orchestrator().drain, 50)
    return {"tasks": ids, "note": "Real orchestrated tasks: budgets, tracing and audit apply; results appear in the profile."}


class MissionIn(BaseModel):
    objective: str = Field(min_length=3, max_length=4000)
    use_archive: bool = False


@router.post("/personnel/agents/{aid}/missions")
def assign_mission(aid: str, body: MissionIn, bg: BackgroundTasks, db: Session = Depends(get_db),
                   user: User = Depends(require_permission("work.run"))):
    """Assign a mission. Custom agents take free-text missions; code agents take structured tasks (via G-SUS)."""
    from ..agents.catalog import build_orchestrator
    from ..agents.orchestrator import GovernanceError
    from ..personnel import runtime

    a = _agent(db, aid)
    if not a.custom:
        raise HTTPException(409, {"message": f"{a.persona_name or a.name} is a code agent with structured task types; give the "
                                             "mission to G-SUS, who plans and delegates to it.", "redirect": "/chamber"})
    if a.lifecycle != "ACTIVE":
        raise HTTPException(409, f"{a.persona_name} is {a.lifecycle}; only ACTIVE agents take missions")
    orch = build_orchestrator()
    runtime.register(orch, a)
    try:
        t = orch.submit(db, runtime.task_type(a.id), {"objective": body.objective, "use_archive": body.use_archive},
                        requested_by=f"user:{user.email}", agent_id=a.id, force=True)
    except GovernanceError as e:
        raise HTTPException(409, str(e)) from e
    gov.audit(db, user.email, "personnel.mission", f"agent:{aid}", task=t.id)
    db.commit()
    bg.add_task(orch.drain, 20)
    return {"task_id": t.id, "status": t.status}


class RelationshipIn(BaseModel):
    source_agent_id: str
    target_agent_id: str
    relationship_type: Literal["collaborates", "mentors", "rivalry", "friendship", "challenges"]
    description: str = Field("", max_length=500)


@router.post("/personnel/relationships")
def relationship_add(body: RelationshipIn, db: Session = Depends(get_db), user: User = Depends(require_permission("agent.develop"))):
    _agent(db, body.source_agent_id), _agent(db, body.target_agent_id)
    if body.source_agent_id == body.target_agent_id:
        raise HTTPException(422, "an agent cannot have a relationship with itself")
    r = AgentRelationship(**body.model_dump())
    db.add(r)
    db.flush()
    gov.audit(db, user.email, "personnel.relationship", f"relationship:{r.id}", **body.model_dump())
    db.commit()
    return _cols(r) | {"note": "Relationships are character colour — they never grant or deny anything."}


@router.delete("/personnel/relationships/{rid}")
def relationship_delete(rid: int, db: Session = Depends(get_db), user: User = Depends(require_permission("agent.develop"))):
    r = db.get(AgentRelationship, rid)
    if r is None:
        raise HTTPException(404)
    db.delete(r)
    gov.audit(db, user.email, "personnel.relationship.delete", f"relationship:{rid}")
    db.commit()
    return {"deleted": rid}


# ================================================================================================ bestiary
SPECIES_FIELDS = ("name", "category", "kind", "alt_names", "subtypes", "origin", "folklore", "fiction", "canon", "traits",
                  "abilities", "strengths", "weaknesses", "symbolism", "relations", "specializations", "example_roles",
                  "sources", "caution")


def _species_summary(s: Species, counts: dict[str, int]) -> dict[str, Any]:
    return {"key": s.key, "name": s.name, "category": s.category, "kind": s.kind, "origin": s.origin, "alt_names": s.alt_names or [],
            "summary": C._first_sentence(s.folklore or s.fiction or s.canon, 200), "user_created": s.user_created,
            "has": {"folklore": bool(s.folklore), "fiction": bool(s.fiction), "canon": bool(s.canon)},
            "agents": counts.get(s.key, 0)}


@router.get("/bestiary")
def bestiary_list(q: str = "", category: str = "", origin: str = "", kind: str = "", db: Session = Depends(get_db),
                  _: User = Depends(current_user)):
    from ..personnel import bestiary_data as B

    rows = list(db.scalars(select(Species).order_by(Species.name)))
    counts = dict(db.execute(select(Agent.species_key, func.count(Agent.id)).where(Agent.lifecycle != "ARCHIVED")
                             .group_by(Agent.species_key)).all())
    origins = sorted({s.origin for s in rows if s.origin})
    ql = q.lower().strip()

    def hit(s: Species) -> bool:
        if category and s.category != category or origin and s.origin != origin or kind and s.kind != kind:
            return False
        return not ql or ql in s.name.lower() or any(ql in a.lower() for a in s.alt_names or []) or ql in s.key
    return {"species": [_species_summary(s, counts) for s in rows if hit(s)], "total": len(rows),
            "categories": [{"key": k, "name": n, "count": sum(1 for s in rows if s.category == k)} for k, n in B.CATEGORIES],
            "origins": origins,
            "labels": {"folklore": "Folklore — summary of traditional belief", "fiction": "Fiction — modern literature, art, games",
                       "canon": "Demonkoncernen canon — this system's own fiction", "caution": "Cultural care / contested claims"},
            "note": "The Bestiary gives inspiration and cultural context, never limits: any species can do any job."}


@router.get("/bestiary/{key}")
def bestiary_article(key: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    s = db.get(Species, key)
    if s is None:
        raise HTTPException(404, f"no being '{key}' in The Bestiary")
    lk = R.Lookups(db)
    agents = [R.card(a, lk) for a in db.scalars(select(Agent).where(Agent.species_key == key, Agent.lifecycle != "ARCHIVED")
                                               .order_by(Agent.persona_name))]
    related = []
    for r in s.relations or []:
        o = db.get(Species, r.get("key", ""))
        if o is not None:
            related.append({"key": o.key, "name": o.name, "type": r.get("type", "related")})
    children = [{"key": o.key, "name": o.name} for o in db.scalars(select(Species).where(Species.key.in_(s.subtypes or [])))]
    specs = [{"key": k, "name": (lk.specs[k].name if k in lk.specs else k)} for k in s.specializations or []]
    return _cols(s) | {"agents": agents, "related": related, "subtype_articles": children, "possible_specializations": specs,
                       "create_link": f"/personnel/create?species={s.key}&source=BESTIARY"}


class SpeciesIn(BaseModel):
    key: str = Field("", max_length=64, pattern=r"^[a-z0-9_]*$")
    name: str = Field(min_length=2, max_length=96)
    category: str = Field("custom", max_length=32)
    kind: Literal["being", "category"] = "being"
    alt_names: list[str] = []
    subtypes: list[str] = []
    origin: str = Field("User-created", max_length=160)
    folklore: str = Field("", max_length=4000)
    fiction: str = Field("", max_length=4000)
    canon: str = Field("", max_length=4000)
    traits: list[str] = []
    abilities: list[str] = []
    strengths: list[str] = []
    weaknesses: list[str] = []
    symbolism: str = Field("", max_length=1000)
    relations: list[dict[str, str]] = []
    specializations: list[str] = []
    example_roles: list[str] = []
    sources: list[dict[str, str]] = []
    caution: str = Field("", max_length=1000)


@router.post("/bestiary")
def bestiary_create(body: SpeciesIn, db: Session = Depends(get_db), user: User = Depends(require_permission("agent.develop"))):
    """Add a being without code changes. Entries added here are marked user-created; folklore claims need sources."""
    from datetime import UTC, datetime

    key = body.key or C._slug(body.name)
    if db.get(Species, key) is not None:
        raise HTTPException(409, f"'{key}' already exists — edit it instead")
    if body.folklore and not body.sources:
        raise HTTPException(422, "A folklore summary needs at least one source (or put the text under canon/fiction).")
    s = Species(key=key, **body.model_dump(exclude={"key"}), user_created=True, created_by=user.email, updated_at=datetime.now(UTC))
    if not s.caution:
        s.caution = "User-created entry: added in this installation."
    db.add(s)
    gov.audit(db, user.email, "bestiary.create", f"species:{key}", category=s.category)
    db.commit()
    return _cols(s)


@router.patch("/bestiary/{key}")
def bestiary_update(key: str, changes: dict[str, Any], db: Session = Depends(get_db),
                    user: User = Depends(require_permission("agent.develop"))):
    from datetime import UTC, datetime

    s = db.get(Species, key)
    if s is None:
        raise HTTPException(404)
    bad = set(changes) - set(SPECIES_FIELDS)
    if bad:
        raise HTTPException(422, "not editable: " + ", ".join(sorted(bad)))
    merged = SpeciesIn(**({k: getattr(s, k) for k in SPECIES_FIELDS if getattr(s, k) is not None} | changes | {"key": key}))
    if merged.folklore and not merged.sources:
        raise HTTPException(422, "A folklore summary needs at least one source.")
    for k in changes:
        setattr(s, k, getattr(merged, k))
    s.updated_at = datetime.now(UTC)
    gov.audit(db, user.email, "bestiary.update", f"species:{key}", fields=sorted(changes))
    db.commit()
    return _cols(s)


# ================================================================================================ specializations
@router.get("/specializations")
def specializations_list(db: Session = Depends(get_db), _: User = Depends(current_user)):
    agents = list(db.scalars(select(Agent).where(Agent.lifecycle != "ARCHIVED")))
    lk = R.Lookups(db)
    species = list(db.scalars(select(Species)))
    depts = lk.depts
    out = []
    for sp in db.scalars(select(Specialization).order_by(Specialization.name)):
        holders = [a for a in agents if sp.key in (a.specializations or [])]
        out.append(_cols(sp) | {"agents": [{"id": a.id, "display": R.card(a, lk)["display"]} for a in holders[:8]],
                                "agent_count": len(holders),
                                "species_suggesting": [{"key": s.key, "name": s.name} for s in species if sp.key in (s.specializations or [])][:8],
                                "department_names": [depts[d].name for d in sp.departments or [] if d in depts]})
    return {"specializations": out, "note": "Specializations are never locked to a race."}


class SpecializationIn(BaseModel):
    name: str = Field(min_length=2, max_length=96)
    description: str = Field("", max_length=2000)
    competencies: list[str] = []
    tools: list[str] = []
    departments: list[str] = []
    example_tasks: list[str] = []
    keywords: list[str] = []


@router.post("/specializations")
def specialization_create(body: SpecializationIn, db: Session = Depends(get_db), user: User = Depends(require_permission("agent.develop"))):
    from ..governance.tool_gateway import TOOLS

    key = C._slug(body.name)
    if db.get(Specialization, key) is not None:
        raise HTTPException(409, f"'{key}' exists")
    bad = [t for t in body.tools if t not in TOOLS]
    if bad:
        raise HTTPException(422, "not Tool Gateway tools: " + ", ".join(bad))
    s = Specialization(key=key, **body.model_dump(), user_created=True)
    db.add(s)
    gov.audit(db, user.email, "specialization.create", f"specialization:{key}")
    db.commit()
    return _cols(s)


# ================================================================================================ departments
@router.get("/departments")
def departments_list(db: Session = Depends(get_db), _: User = Depends(current_user)):
    lk = R.Lookups(db)
    agents = list(db.scalars(select(Agent).where(Agent.lifecycle != "ARCHIVED")))
    out = []
    for d in db.scalars(select(Department).order_by(Department.name)):
        members = [a for a in agents if a.department_key == d.key]
        species = sorted({lk.species[a.species_key].name for a in members if a.species_key in lk.species})
        out.append(_cols(d) | {"manager": lk.names.get(d.manager_id) if d.manager_id else None, "count": len(members),
                               "species_mix": species, "members": [R.card(a, lk)["display"] for a in members][:40]})
    return {"departments": out, "note": "Departments are functional — organised by what agents do, never by race."}


class DepartmentIn(BaseModel):
    key: str = Field("", max_length=64, pattern=r"^[a-z0-9_]*$")
    name: str = Field(min_length=2, max_length=96)
    description: str = Field("", max_length=2000)
    manager_id: str | None = None


@router.post("/departments")
def department_create(body: DepartmentIn, db: Session = Depends(get_db), user: User = Depends(require_permission("agent.develop"))):
    key = body.key or C._slug(body.name)
    if db.get(Department, key) is not None:
        raise HTTPException(409, f"'{key}' exists")
    if body.manager_id and db.get(Agent, body.manager_id) is None:
        raise HTTPException(422, "unknown manager")
    d = Department(key=key, name=body.name, description=body.description, manager_id=body.manager_id, divisions=[])
    db.add(d)
    gov.audit(db, user.email, "department.create", f"department:{key}")
    db.commit()
    return _cols(d)


@router.patch("/departments/{key}")
def department_update(key: str, body: DepartmentIn, db: Session = Depends(get_db), user: User = Depends(require_permission("agent.develop"))):
    d = db.get(Department, key)
    if d is None:
        raise HTTPException(404)
    if body.manager_id and db.get(Agent, body.manager_id) is None:
        raise HTTPException(422, "unknown manager")
    d.name, d.description, d.manager_id = body.name, body.description, body.manager_id
    gov.audit(db, user.email, "department.update", f"department:{key}")
    db.commit()
    return _cols(d)


def can_create(user: User) -> bool:
    return has(user, "agent.develop")
