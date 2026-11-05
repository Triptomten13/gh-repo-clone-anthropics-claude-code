"""REST API for the command center."""
from __future__ import annotations

from datetime import datetime, timedelta, UTC
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..agents.catalog import build_orchestrator
from ..agents.orchestrator import GovernanceError
from ..ai.llm import get_provider
from ..db import get_db
from ..engines import business_models, compliance, economics, finance, pricing, scoring
from ..governance import core as gov
from ..integrations import registry as connectors
from ..models import (Agent, AgentMessage, Approval, AuditLog, Experiment, LedgerEntry, Lesson, Opportunity, Product,
                      Store, Supplier, Task, Trend, User)
from ..security.auth import current_user, hash_password, issue_token, require_role, verify_password
from ..services import data_import, scheduler

router = APIRouter(prefix="/api")
orch = build_orchestrator()


def row(o: Any, exclude: set[str] | None = None) -> dict[str, Any]:
    ex = exclude or set()
    return {c.key: getattr(o, c.key) for c in o.__table__.columns if c.key not in ex}


# =================================================================== auth
class Credentials(BaseModel):
    email: str
    password: str = Field(min_length=10)


@router.get("/auth/status")
def auth_status(db: Session = Depends(get_db)):
    from ..config import get_settings

    s = get_settings()
    return {"setup_required": db.scalar(select(func.count(User.id))) == 0, "company_name": s.company_name, "platform_name": s.platform_name}


@router.post("/auth/setup")
def setup(c: Credentials, db: Session = Depends(get_db)):
    if db.scalar(select(func.count(User.id))):
        raise HTTPException(409, "already set up")
    u = User(email=c.email.lower(), password_hash=hash_password(c.password), role="admin")
    db.add(u)
    db.flush()
    gov.audit(db, c.email, "auth.setup", f"user:{u.id}")
    db.commit()
    return {"token": issue_token(u), "user": {"email": u.email, "role": u.role}}


@router.post("/auth/login")
def login(c: Credentials, request: Request, db: Session = Depends(get_db)):
    from ..config import get_settings
    from ..security.ratelimit import login_failures

    s = get_settings()
    ip = request.client.host if request.client else "unknown"
    keys = (f"acct:{c.email.lower()}", f"ip:{ip}")
    if any(login_failures.count(k, s.login_window_s) >= s.login_max_attempts * (4 if k.startswith("ip:") else 1) for k in keys):
        gov.audit(db, c.email, "auth.login_locked", ip=ip)
        db.commit()
        raise HTTPException(429, "too many failed attempts — try again later", headers={"Retry-After": str(s.login_window_s)})
    u = db.scalars(select(User).where(User.email == c.email.lower())).first()
    if not u or not verify_password(c.password, u.password_hash):
        for k in keys:
            login_failures.hit(k, 10_000, s.login_window_s)
        gov.audit(db, c.email, "auth.login_failed", ip=ip)
        db.commit()
        raise HTTPException(401, "invalid credentials")
    login_failures.reset(keys[0])
    gov.audit(db, u.email, "auth.login", ip=ip)
    db.commit()
    return {"token": issue_token(u), "user": {"email": u.email, "role": u.role}}


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return {"email": user.email, "role": user.role}


class NewUser(Credentials):
    role: str = Field(default="operator", pattern="^(admin|operator|viewer)$")


@router.post("/auth/users")
def create_user(n: NewUser, db: Session = Depends(get_db), admin: User = Depends(require_role("admin"))):
    if db.scalars(select(User).where(User.email == n.email.lower())).first():
        raise HTTPException(409, "exists")
    u = User(email=n.email.lower(), password_hash=hash_password(n.password), role=n.role)
    db.add(u)
    gov.audit(db, admin.email, "user.create", n.email, role=n.role)
    db.commit()
    return {"email": u.email, "role": u.role}


operator = require_role("admin", "operator")
admin_only = require_role("admin")


# =================================================================== overview
@router.get("/overview")
def overview(db: Session = Depends(get_db), _: User = Depends(current_user)):
    entries = db.scalars(select(LedgerEntry)).all()
    fin = finance.summarize(entries)
    top = db.scalars(select(Product).where(Product.opportunity_score.is_not(None)).order_by(Product.opportunity_score.desc()).limit(5)).all()
    trends_ = db.scalars(select(Trend).where(Trend.stage.in_(("emerging", "exploding"))).order_by(Trend.velocity_score.desc()).limit(6)).all()
    since = datetime.now(UTC) - timedelta(days=1)
    alerts = db.scalars(select(AgentMessage).where(AgentMessage.kind.in_(("error", "blocked")), AgentMessage.created_at >= since)
                        .order_by(AgentMessage.id.desc()).limit(10)).all()
    count = lambda q: db.scalar(select(func.count()).select_from(q.subquery()))  # noqa: E731
    return {
        "finance": {k: fin[k] for k in ("revenue", "gross_profit", "net_profit", "contribution_margin", "ad_spend", "roas", "entries", "contains_demo_data")},
        "counts": {
            "products": count(select(Product.id)),
            "under_investigation": count(select(Product.id).where(Product.status == "investigating")),
            "active_businesses": count(select(Store.id).where(Store.status == "live")),
            "active_experiments": count(select(Experiment.id).where(Experiment.status == "running")),
            "pending_approvals": count(select(Approval.id).where(Approval.status == "pending")),
            "queued_tasks": count(select(Task.id).where(Task.status.in_(("queued", "running")))),
        },
        "top_products": [{"id": p.id, "name": p.name, "score": p.opportunity_score, "confidence": p.score_confidence,
                          "compliance": p.compliance_status, "is_demo": p.is_demo} for p in top],
        "emerging_trends": [row(t) for t in trends_],
        "alerts": [{"agent": a.agent_id, "kind": a.kind, "summary": a.summary[:240], "at": a.created_at} for a in alerts],
        "kill_switch": gov.get_state(db, "kill_switch"),
        "llm_provider": get_provider().name,
    }


# =================================================================== agents & tasks
@router.get("/agents")
def list_agents(db: Session = Depends(get_db), _: User = Depends(current_user)):
    rows = db.scalars(select(Agent).order_by(Agent.division, Agent.id)).all()
    out = []
    for a in rows:
        d = row(a)
        d["task_types"] = list(orch.agents[a.id].task_types) if a.id in orch.agents else []
        d["running"] = db.scalar(select(func.count(Task.id)).where(Task.agent_id == a.id, Task.status == "running"))
        d["queued"] = db.scalar(select(func.count(Task.id)).where(Task.agent_id == a.id, Task.status == "queued"))
        out.append(d)
    return out


class AgentPatch(BaseModel):
    status: str | None = Field(default=None, pattern="^(active|suspended)$")
    permission_level: int | None = Field(default=None, ge=0, le=5)
    daily_token_budget: int | None = Field(default=None, ge=0)


@router.patch("/agents/{agent_id}")
def patch_agent(agent_id: str, p: AgentPatch, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    a = db.get(Agent, agent_id)
    if not a:
        raise HTTPException(404)
    changes = p.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(a, k, v)
    gov.audit(db, user.email, "agent.update", f"agent:{agent_id}", **changes)
    db.commit()
    return row(a)


class TaskIn(BaseModel):
    type: str
    payload: dict[str, Any] = {}
    priority: int = 50
    force: bool = False
    run: bool = True


@router.post("/tasks")
def submit_task(t: TaskIn, bg: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(operator)):
    try:
        task = orch.submit(db, t.type, t.payload, requested_by=f"user:{user.email}", priority=t.priority, force=t.force)
    except GovernanceError as e:
        raise HTTPException(409, str(e)) from e
    gov.audit(db, user.email, "task.submit", f"task:{task.id}", type=t.type)
    db.commit()
    if t.run:
        bg.add_task(orch.drain, 200)
    return row(task)


@router.post("/tasks/drain")
def drain(bg: BackgroundTasks, _: User = Depends(operator)):
    bg.add_task(orch.drain, 200)
    return {"scheduled": True}


@router.get("/tasks")
def list_tasks(status: str | None = None, agent_id: str | None = None, limit: int = Query(100, le=500),
               db: Session = Depends(get_db), _: User = Depends(current_user)):
    q = select(Task).order_by(Task.id.desc()).limit(limit)
    if status:
        q = q.where(Task.status == status)
    if agent_id:
        q = q.where(Task.agent_id == agent_id)
    return [row(t, {"result"}) for t in db.scalars(q).all()]


@router.get("/tasks/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    t = db.get(Task, task_id)
    if not t:
        raise HTTPException(404)
    children = db.scalars(select(Task.id).where(Task.parent_id == task_id)).all()
    return {**row(t), "children": children}


@router.get("/task-types")
def task_types(_: User = Depends(current_user)):
    return orch.routes


@router.get("/messages")
def messages(limit: int = Query(100, le=500), agent_id: str | None = None, db: Session = Depends(get_db), _: User = Depends(current_user)):
    q = select(AgentMessage).order_by(AgentMessage.id.desc()).limit(limit)
    if agent_id:
        q = q.where(AgentMessage.agent_id == agent_id)
    return [row(m) for m in db.scalars(q).all()]


# =================================================================== products
class ProductIn(BaseModel):
    name: str
    category: str = ""
    description: str = ""
    source_platform: str = "manual"
    source_url: str = ""
    supplier_id: int | None = None
    currency: str = "SEK"
    wholesale_price: float | None = None
    shipping_cost: float | None = None
    delivery_days: float | None = None
    retail_price: float | None = None
    competitor_prices: list[float] = []
    purchase_signal: float | None = Field(default=None, ge=0, le=100)
    engagement_signal: float | None = Field(default=None, ge=0, le=100)
    search_interest: float | None = Field(default=None, ge=0, le=100)
    trend_velocity: float | None = Field(default=None, ge=0, le=100)
    competitor_count: int | None = None
    competition_quality: float | None = Field(default=None, ge=0, le=100)
    sentiment: float | None = Field(default=None, ge=-1, le=1)
    review_complaint_rate: float | None = Field(default=None, ge=0, le=1)
    return_risk: float | None = Field(default=None, ge=0, le=1)
    marketing_potential: float | None = Field(default=None, ge=0, le=100)
    customization_potential: float | None = Field(default=None, ge=0, le=100)
    differentiation_potential: float | None = Field(default=None, ge=0, le=100)
    scalability: float | None = Field(default=None, ge=0, le=100)
    tags: list[str] = []


@router.get("/products")
def list_products(q: str | None = None, category: str | None = None, status: str | None = None, min_score: float | None = None,
                  sort: str = "opportunity_score", db: Session = Depends(get_db), _: User = Depends(current_user)):
    stmt = select(Product)
    if q:
        stmt = stmt.where(Product.name.ilike(f"%{q}%") | Product.description.ilike(f"%{q}%"))
    if category:
        stmt = stmt.where(Product.category == category)
    if status:
        stmt = stmt.where(Product.status == status)
    if min_score is not None:
        stmt = stmt.where(Product.opportunity_score >= min_score)
    col = getattr(Product, sort, Product.opportunity_score)
    stmt = stmt.order_by(col.desc().nullslast(), Product.id.desc())
    return [row(p, {"compliance_report", "score_breakdown"}) for p in db.scalars(stmt).all()]


@router.post("/products")
def create_product(p: ProductIn, db: Session = Depends(get_db), user: User = Depends(operator)):
    prod = Product(**p.model_dump())
    db.add(prod)
    db.flush()
    gov.audit(db, user.email, "product.create", f"product:{prod.id}")
    db.commit()
    return row(prod)


@router.get("/products/{pid}")
def get_product(pid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    p = db.get(Product, pid)
    if not p:
        raise HTTPException(404)
    opps = db.scalars(select(Opportunity).where(Opportunity.product_id == pid).order_by(Opportunity.id.desc())).all()
    tasks = [t for t in db.scalars(select(Task).order_by(Task.id.desc()).limit(500)).all() if t.payload.get("product_id") == pid]
    return {**row(p), "supplier": row(p.supplier) if p.supplier else None, "opportunities": [row(o) for o in opps],
            "tasks": [row(t) for t in tasks[:20]]}


@router.patch("/products/{pid}")
def patch_product(pid: int, body: dict[str, Any], db: Session = Depends(get_db), user: User = Depends(operator)):
    p = db.get(Product, pid)
    if not p:
        raise HTTPException(404)
    allowed = set(ProductIn.model_fields) | {"status"}
    for k, v in body.items():
        if k in allowed:
            setattr(p, k, v)
    gov.audit(db, user.email, "product.update", f"product:{pid}", fields=sorted(set(body) & allowed))
    db.commit()
    return row(p)


@router.post("/products/{pid}/evaluate")
def evaluate_product(pid: int, bg: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(operator)):
    if not db.get(Product, pid):
        raise HTTPException(404)
    t = orch.submit(db, "ceo.evaluate_product", {"product_id": pid, "refresh": datetime.now(UTC).isoformat()},
                    requested_by=f"user:{user.email}", priority=5, force=True)
    db.commit()
    bg.add_task(orch.drain, 50)
    return row(t)


class ComplianceDecision(BaseModel):
    approve: bool
    note: str = Field(min_length=3)
    checklist_confirmed: bool = False


@router.post("/products/{pid}/compliance-decision")
def compliance_decision(pid: int, d: ComplianceDecision, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    p = db.get(Product, pid)
    if not p:
        raise HTTPException(404)
    if d.approve and not d.checklist_confirmed:
        raise HTTPException(400, "confirm that every checklist item has been verified")
    p.compliance_status = "approved" if d.approve else "blocked"
    p.compliance_report = {**(p.compliance_report or {}), "human_decision": {"by": user.email, "note": d.note,
                                                                              "at": datetime.now(UTC).isoformat()}}
    gov.audit(db, user.email, "compliance.human_decision", f"product:{pid}", approve=d.approve, note=d.note)
    db.commit()
    return {"compliance_status": p.compliance_status}


class ScoreAdjustment(BaseModel):
    delta: float = Field(ge=-30, le=30)
    reason: str = Field(min_length=3)


@router.post("/products/{pid}/adjustments")
def add_adjustment(pid: int, a: ScoreAdjustment, db: Session = Depends(get_db), user: User = Depends(operator)):
    p = db.get(Product, pid)
    if not p:
        raise HTTPException(404)
    p.score_adjustments = [*(p.score_adjustments or []), {"delta": a.delta, "reason": a.reason, "by": user.email}]
    gov.audit(db, user.email, "score.adjust", f"product:{pid}", delta=a.delta, reason=a.reason)
    db.commit()
    return {"adjustments": p.score_adjustments}


class ImportIn(BaseModel):
    format: str = Field(default="csv", pattern="^(csv|json)$")
    content: str


@router.post("/import/products")
def import_products(i: ImportIn, db: Session = Depends(get_db), user: User = Depends(operator)):
    created = data_import.import_products(db, data_import.parse_rows(i.content, i.format))
    gov.audit(db, user.email, "import.products", count=len(created))
    db.commit()
    return {"created": len(created), "ids": [p.id for p in created]}


@router.post("/import/observations")
def import_observations(i: ImportIn, db: Session = Depends(get_db), user: User = Depends(operator)):
    n = data_import.import_observations(db, data_import.parse_rows(i.content, i.format))
    gov.audit(db, user.email, "import.observations", count=n)
    db.commit()
    return {"created": n}


@router.post("/import/ledger")
def import_ledger(i: ImportIn, db: Session = Depends(get_db), user: User = Depends(operator)):
    n = data_import.import_ledger(db, data_import.parse_rows(i.content, i.format))
    gov.audit(db, user.email, "import.ledger", count=n)
    db.commit()
    return {"created": n}


# =================================================================== trends, opportunities, suppliers
@router.get("/trends")
def list_trends(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [row(t) for t in db.scalars(select(Trend).order_by(Trend.velocity_score.desc())).all()]


@router.get("/opportunities")
def list_opps(db: Session = Depends(get_db), _: User = Depends(current_user)):
    out = []
    for o in db.scalars(select(Opportunity).order_by(Opportunity.id.desc()).limit(200)).all():
        d = row(o)
        d["product_name"] = o.product.name if o.product else None
        out.append(d)
    return out


class SupplierIn(BaseModel):
    name: str
    platform: str = ""
    country: str = ""
    eu_based: bool = False
    rating: float | None = Field(default=None, ge=0, le=5)
    years_active: float | None = None
    moq: int | None = None
    avg_delivery_days: float | None = None
    response_rate: float | None = Field(default=None, ge=0, le=1)
    dispute_rate: float | None = Field(default=None, ge=0, le=1)
    offers_private_label: bool = False
    offers_custom_packaging: bool = False
    has_product_documentation: bool = False
    notes: str = ""


@router.get("/suppliers")
def list_suppliers(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [row(s) for s in db.scalars(select(Supplier).order_by(Supplier.id.desc())).all()]


@router.post("/suppliers")
def create_supplier(s: SupplierIn, db: Session = Depends(get_db), user: User = Depends(operator)):
    sup = Supplier(**s.model_dump())
    sup.reliability_score, _ = scoring.supplier_reliability_score(sup)
    db.add(sup)
    db.flush()
    gov.audit(db, user.email, "supplier.create", f"supplier:{sup.id}")
    db.commit()
    return row(sup)


# =================================================================== calculators (pure engines)
class EconomicsIn(BaseModel):
    retail_price_incl_vat: float = Field(gt=0)
    unit_cost: float = Field(ge=0)
    inbound_shipping: float = 0
    packaging: float = 0
    fulfillment: float = 0
    import_duty_rate: float = 0
    customs_handling: float = 0
    vat_rate: float = 0.25
    payment_fee_pct: float = 0.029
    payment_fee_fixed: float = 1.8
    marketplace_fee_pct: float = 0
    return_rate: float = Field(default=0.05, ge=0, le=1)
    return_cost_per_return: float = 0
    unsellable_return_fraction: float = Field(default=0.3, ge=0, le=1)
    cac: float = 0
    competitor_prices: list[float] = []
    currency: str = "SEK"


@router.post("/tools/economics")
def tool_economics(e: EconomicsIn, _: User = Depends(current_user)):
    d = e.model_dump()
    comp, cur = d.pop("competitor_prices"), d.pop("currency")
    c = economics.CostInputs(**d)
    try:
        sc = pricing.scenarios(c, comp, cur)
    except ValueError as err:
        sc = {"error": str(err)}
    return {"economics": economics.compute(c).as_dict(), "pricing": sc}


@router.post("/tools/compliance")
def tool_compliance(body: dict[str, Any], _: User = Depends(current_user)):
    return compliance.assess(body.get("name", ""), body.get("description", ""), body.get("category", ""), body.get("tags", []),
                             body.get("marketing_copy", ""), body.get("non_eu_supplier", True), body.get("affiliate", False)).as_dict()


@router.post("/tools/business-models")
def tool_bm(body: dict[str, Any], _: User = Depends(current_user)):
    fields = business_models.ProductTraits.__dataclass_fields__
    return business_models.evaluate(business_models.ProductTraits(**{k: v for k, v in body.items() if k in fields}))


@router.get("/tools/scoring-weights")
def weights(_: User = Depends(current_user)):
    return scoring.WEIGHTS


# =================================================================== finance
@router.get("/finance/summary")
def fin_summary(days: int | None = None, db: Session = Depends(get_db), _: User = Depends(current_user)):
    q = select(LedgerEntry)
    if days:
        q = q.where(LedgerEntry.occurred_at >= datetime.now(UTC) - timedelta(days=days))
    entries = db.scalars(q).all()
    return {**finance.summarize(entries), "daily": finance.daily_series(entries)}


@router.get("/finance/forecast")
def fin_forecast(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return finance.forecast(finance.daily_series(db.scalars(select(LedgerEntry)).all()))


class LedgerIn(BaseModel):
    kind: str = Field(pattern="^(revenue|cogs|shipping|fees|ad_spend|refund|chargeback|opex|tax)$")
    amount: float = Field(ge=0)
    occurred_at: datetime
    product_id: int | None = None
    store_id: int | None = None
    channel: str = "direct"
    reference: str = ""


@router.post("/finance/ledger")
def add_ledger(e: LedgerIn, db: Session = Depends(get_db), user: User = Depends(operator)):
    le = LedgerEntry(**e.model_dump())
    db.add(le)
    db.flush()
    gov.audit(db, user.email, "ledger.add", f"ledger:{le.id}", kind=e.kind, amount=e.amount)
    db.commit()
    return row(le)


# =================================================================== approvals
@router.get("/approvals")
def list_approvals(status: str | None = None, db: Session = Depends(get_db), _: User = Depends(current_user)):
    q = select(Approval).order_by(Approval.id.desc())
    if status:
        q = q.where(Approval.status == status)
    return [row(a) for a in db.scalars(q).all()]


class Decision(BaseModel):
    approve: bool
    note: str = ""


@router.post("/approvals/{aid}/decide")
def decide(aid: int, d: Decision, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    a = db.get(Approval, aid)
    if not a:
        raise HTTPException(404)
    try:
        gov.decide_approval(db, a, d.approve, user.email, d.note)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    db.commit()
    return row(a)


# =================================================================== experiments
class ExperimentIn(BaseModel):
    name: str
    hypothesis: str
    opportunity_id: int | None = None
    variant_a: str = ""
    variant_b: str = ""
    success_metrics: dict[str, Any] = {"min_roas": 2.0, "min_contribution_margin": 0, "min_orders": 20, "kill_roas": 1.0}
    predicted: dict[str, Any] = {}
    budget_sek: float = Field(default=0, ge=0)


@router.get("/experiments")
def list_experiments(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [row(e) for e in db.scalars(select(Experiment).order_by(Experiment.id.desc())).all()]


@router.post("/experiments")
def create_experiment(e: ExperimentIn, db: Session = Depends(get_db), user: User = Depends(operator)):
    exp = Experiment(**e.model_dump())
    db.add(exp)
    db.flush()
    if exp.budget_sek > 0:
        exp.status = "pending_approval"
        gov.request_approval(db, "experiment.run_paid", f"Run experiment '{exp.name}'", f"user:{user.email}",
                             exp.hypothesis, {"experiment_id": exp.id}, exp.budget_sek)
    gov.audit(db, user.email, "experiment.create", f"experiment:{exp.id}")
    db.commit()
    return row(exp)


@router.post("/experiments/{eid}/start")
def start_experiment(eid: int, db: Session = Depends(get_db), user: User = Depends(operator)):
    e = db.get(Experiment, eid)
    if not e:
        raise HTTPException(404)
    if e.budget_sek > 0:
        ok = db.scalars(select(Approval).where(Approval.action == "experiment.run_paid", Approval.status == "approved")).all()
        if not any(a.payload.get("experiment_id") == eid for a in ok):
            raise HTTPException(403, "paid experiment requires an approved LEVEL 5 approval")
    e.status = "running"
    gov.audit(db, user.email, "experiment.start", f"experiment:{eid}")
    db.commit()
    return row(e)


@router.post("/experiments/{eid}/results")
def record_results(eid: int, actual: dict[str, Any], bg: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(operator)):
    e = db.get(Experiment, eid)
    if not e:
        raise HTTPException(404)
    e.actual = actual
    t = orch.submit(db, "experiment.evaluate", {"experiment_id": eid, "rev": datetime.now(UTC).isoformat()},
                    requested_by=f"user:{user.email}", priority=5)
    db.commit()
    bg.add_task(orch.drain, 10)
    return {"experiment": row(e), "task_id": t.id}


# =================================================================== system
@router.get("/system/status")
def system_status(db: Session = Depends(get_db), _: User = Depends(current_user)):
    from ..config import get_settings

    s = get_settings()
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    spent = db.scalar(select(func.coalesce(func.sum(Task.cost_usd), 0.0)).where(Task.created_at >= start))
    return {
        "company_name": s.company_name,
        "platform_name": s.platform_name,
        "kill_switch": gov.get_state(db, "kill_switch"),
        "llm_provider": get_provider().name,
        "models": {"deep": s.model_deep, "standard": s.model_standard, "fast": s.model_fast},
        "cost_today_usd": round(spent or 0, 4),
        "daily_cost_limit_usd": s.daily_cost_limit_usd,
        "max_task_depth": s.max_task_depth,
        "scheduler_enabled": s.scheduler_enabled,
        "scheduler_state": gov.get_state(db, "scheduler"),
        "database": s.database_url.split(":")[0],
    }


class KillSwitch(BaseModel):
    engaged: bool
    reason: str = ""


@router.post("/system/kill-switch")
def kill_switch(k: KillSwitch, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    gov.set_kill_switch(db, k.engaged, user.email, k.reason)
    if k.engaged:
        for t in db.scalars(select(Task).where(Task.status == "queued")).all():
            t.status, t.error = "cancelled", "kill switch"
    db.commit()
    return gov.get_state(db, "kill_switch")


@router.get("/audit")
def audit_log(limit: int = Query(200, le=1000), db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [row(a) for a in db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)).all()]


@router.get("/integrations")
def integrations(_: User = Depends(current_user)):
    return connectors.all_status()


@router.get("/watchlist")
def get_watchlist(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return gov.get_state(db, "watchlist", {"keywords": []})


class Watchlist(BaseModel):
    keywords: list[str]


@router.put("/watchlist")
def put_watchlist(w: Watchlist, db: Session = Depends(get_db), user: User = Depends(operator)):
    kws = sorted({k.strip().lower() for k in w.keywords if k.strip()})[:200]
    gov.set_state(db, "watchlist", {"keywords": kws})
    gov.audit(db, user.email, "watchlist.update", count=len(kws))
    db.commit()
    return {"keywords": kws}


@router.post("/scheduler/tick")
def scheduler_tick(bg: BackgroundTasks, _: User = Depends(operator)):
    bg.add_task(scheduler.tick)
    return {"scheduled": True}


@router.get("/lessons")
def lessons(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [row(x) for x in db.scalars(select(Lesson).order_by(Lesson.id.desc())).all()]


@router.post("/demo")
def load_demo(db: Session = Depends(get_db), user: User = Depends(admin_only)):
    if db.scalar(select(func.count(Product.id)).where(Product.is_demo.is_(True))):
        raise HTTPException(409, "demo data already loaded")
    res = data_import.load_demo(db)
    gov.audit(db, user.email, "demo.load", **res)
    db.commit()
    return res


@router.delete("/demo")
def clear_demo(db: Session = Depends(get_db), user: User = Depends(admin_only)):
    res = data_import.clear_demo(db)
    gov.audit(db, user.email, "demo.clear", **res)
    db.commit()
    return res
