"""DAEMON CONTROL PLANE API — audit & provenance, identity (roles/permissions); further sections are added per phase.

Every endpoint checks a PERMISSION (security/rbac.py), not just a role, and every state change is audited."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..governance import audit_chain
from ..governance import core as gov
from ..models import Approval, PolicyRule, ToolGrant, ToolInvocation, User
from ..security.rbac import PERMISSIONS, ROLES, require_permission
from ..security.auth import current_user


def _cols(o: Any) -> dict[str, Any]:
    return {c.key: getattr(o, c.key) for c in o.__table__.columns}

router = APIRouter(prefix="/api")


# ------------------------------------------------------------------ audit & provenance
@router.get("/audit/records")
def audit_records(since: datetime | None = None, until: datetime | None = None, actor: str | None = None, action: str | None = None,
                  target: str | None = None, limit: int = Query(200, ge=1, le=5000), db: Session = Depends(get_db),
                  _: User = Depends(require_permission("audit.read"))):
    rows = audit_chain.query(db, since=since, until=until, actor=actor, action=action, target=target, limit=limit)
    return [audit_chain._record(r) for r in rows]


@router.get("/audit/verify")
def audit_verify(db: Session = Depends(get_db), user: User = Depends(require_permission("audit.verify"))):
    out = audit_chain.verify(db)
    gov.audit(db, user.email, "audit.verify", "audit_log", ok=out["ok"], checked=out["checked"], reason=out.get("reason"))
    db.commit()
    return out


@router.get("/audit/export")
def audit_export(fmt: Literal["json", "csv", "zip"] = "zip", since: datetime | None = None, until: datetime | None = None,
                 actor: str | None = None, action: str | None = None, target: str | None = None, db: Session = Depends(get_db),
                 user: User = Depends(require_permission("audit.export"))):
    filters = {"since": since, "until": until, "actor": actor, "action": action, "target": target}
    gov.audit(db, user.email, "audit.export", "audit_log", format=fmt, **{k: str(v) for k, v in filters.items() if v})
    db.commit()  # the export itself is part of the trail it exports
    data, mime = audit_chain.export(db, fmt, filters, user.email)
    name = f"demonkoncernen-audit-{datetime.now():%Y%m%d-%H%M%S}.{fmt}"
    return Response(data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}"'})


class PruneIn(BaseModel):
    before: datetime
    approval_id: int | None = None


@router.post("/audit/prune")
def audit_prune(p: PruneIn, db: Session = Depends(get_db), user: User = Depends(require_permission("audit.retention"))):
    """Destroying evidence is RESTRICTED: a second person approves this exact cut-off, and the minimum retention age
    always applies."""
    before = p.before if p.before.tzinfo else p.before.replace(tzinfo=UTC)
    try:
        audit_chain.check_retention(before)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    blocked = _governed(db, user, "audit.prune", {"before": before.isoformat()}, p.approval_id,
                        f"Prune audit records created before {before.isoformat()}")
    if blocked:
        return blocked
    try:
        out = audit_chain.prune(db, before, user.email)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    db.commit()
    return out


# ------------------------------------------------------------------ identity & access
@router.get("/rbac/roles")
def rbac_roles(_: User = Depends(require_permission("policy.read"))):
    return {"permissions": PERMISSIONS, "roles": {r: sorted(p) for r, p in ROLES.items()},
            "note": "roles never inherit implicitly; builders cannot approve, approvers cannot change policy, auditors change nothing"}


# ------------------------------------------------------------------ governance changes need a second person
def _governed(db: Session, user: User, action: str, payload: dict, approval_id: int | None, title: str):
    """Policy, grant and budget changes are RESTRICTED: filed as an approval request the first time; applied only when
    called again with an approval decided by SOMEONE ELSE for exactly this payload. Returns None when allowed."""
    from fastapi.responses import JSONResponse

    from ..governance.policy import ApprovalRequired, PolicyDenied, Request, enforce

    try:
        enforce(db, Request(action=action, user_email=user.email, user_role=user.role, approval_id=approval_id, payload=payload),
                request_approval_title=title)
        return None
    except ApprovalRequired as e:
        db.commit()
        return JSONResponse({"status": "pending_approval", "approval_id": e.decision.approval_id, "category": e.decision.category_name,
                             "reasons": e.decision.reasons}, status_code=202)
    except PolicyDenied as e:
        db.commit()
        raise HTTPException(403, {"category": e.decision.category_name, "reasons": e.decision.reasons}) from None


# ------------------------------------------------------------------ policies
class RuleIn(BaseModel):
    key: str = Field(min_length=3, max_length=96, pattern=r"^[a-z0-9_.:-]+$")
    action: str = Field(min_length=1, max_length=128)
    category: int = Field(ge=1, le=5)
    conditions: dict[str, Any] = {}
    priority: int = Field(100, ge=0, le=10_000)
    reason: str = Field("", max_length=2000)
    approval_id: int | None = None


@router.get("/policies")
def policies(db: Session = Depends(get_db), _: User = Depends(require_permission("policy.read"))):
    from ..governance import policy as P

    rules = P.active_rules(db)
    return {"version": P.policy_version(rules), "rules": [_cols(r) for r in rules],
            "categories": {c.value: c.name for c in P.Category}, "classifications": P.CLASSIFICATIONS,
            "mandatory": {"floors": {k: v.name for k, v in P.FLOORS.items()}, "prohibited": P.PROHIBITED, "agent_prohibited": P.AGENT_PROHIBITED,
                          "note": "rules may raise a category, never lower it below a mandatory floor"}}


@router.get("/policies/history")
def policy_history(key: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_permission("policy.read"))):
    q = select(PolicyRule).order_by(PolicyRule.key, PolicyRule.version)
    if key:
        q = q.where(PolicyRule.key == key)
    return [_cols(r) for r in db.scalars(q)]


@router.post("/policies")
def policy_upsert(r: RuleIn, db: Session = Depends(get_db), user: User = Depends(require_permission("policy.write"))):
    from ..governance import policy as P

    if "*" not in r.action:
        floor, _ = P._floor(P.Request(action=r.action))
        if r.category < floor:
            raise HTTPException(422, f"cannot lower {r.action} below its mandatory floor {floor.name}")
    payload = r.model_dump(exclude={"approval_id"})
    pending = _governed(db, user, "policy.write", payload, r.approval_id, f"Policy change: {r.key} → {P.Category(r.category).name}")
    if pending is not None:
        return pending
    now = datetime.now(UTC)
    prev = db.scalars(select(PolicyRule).where(PolicyRule.key == r.key, PolicyRule.superseded_at.is_(None))).first()
    version = (db.scalar(select(func.max(PolicyRule.version)).where(PolicyRule.key == r.key)) or 0) + 1
    if prev:
        prev.superseded_at = now
    row = PolicyRule(key=r.key, version=version, action=r.action, category=r.category, conditions=r.conditions, priority=r.priority,
                     reason=r.reason, created_by=user.email)
    db.add(row)
    db.flush()
    gov.audit(db, user.email, "policy.write", f"policy:{r.key}@{version}", rule_action=r.action, category=r.category,
              conditions=r.conditions, priority=r.priority, reason=r.reason, approval=r.approval_id, previous_version=prev.version if prev else None)
    db.commit()
    return {"status": "applied", "rule": _cols(row), "policy_version": P.policy_version(P.active_rules(db))}


class RollbackIn(BaseModel):
    to_version: int
    approval_id: int | None = None


@router.post("/policies/{key}/rollback")
def policy_rollback(key: str, b: RollbackIn, db: Session = Depends(get_db), user: User = Depends(require_permission("policy.write"))):
    old = db.scalars(select(PolicyRule).where(PolicyRule.key == key, PolicyRule.version == b.to_version)).first()
    if old is None:
        raise HTTPException(404, f"{key}@{b.to_version} not found")
    return policy_upsert(RuleIn(key=key, action=old.action, category=old.category, conditions=old.conditions or {}, priority=old.priority,
                                reason=f"rollback to v{b.to_version}: {old.reason}"[:2000], approval_id=b.approval_id), db, user)


@router.post("/policies/{key}/disable")
def policy_disable(key: str, approval_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(require_permission("policy.write"))):
    row = db.scalars(select(PolicyRule).where(PolicyRule.key == key, PolicyRule.superseded_at.is_(None))).first()
    if row is None:
        raise HTTPException(404)
    pending = _governed(db, user, "policy.write", {"disable": key}, approval_id, f"Disable policy {key}")
    if pending is not None:
        return pending
    row.enabled = False
    gov.audit(db, user.email, "policy.disable", f"policy:{key}@{row.version}", approval=approval_id)
    db.commit()
    return {"status": "disabled", "key": key}


# ------------------------------------------------------------------ approvals (lifecycle)
class DelegateIn(BaseModel):
    to: str = Field(min_length=3, max_length=255)


@router.get("/approvals/approvers")
def approval_approvers(db: Session = Depends(get_db), user: User = Depends(require_permission("approval.decide"))):
    """People a pending approval can be delegated to: active users who may decide approvals (never the caller)."""
    from ..security.rbac import has

    return [{"email": u.email, "role": u.role} for u in db.scalars(select(User).order_by(User.email))
            if u.email != user.email and not u.disabled and has(u, "approval.decide")]


@router.post("/approvals/{aid}/revoke")
def approval_revoke(aid: int, reason: str = "", db: Session = Depends(get_db), user: User = Depends(require_permission("approval.decide"))):
    a = db.get(Approval, aid)
    if not a:
        raise HTTPException(404)
    try:
        gov.revoke_approval(db, a, user.email, reason)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    db.commit()
    return _cols(a)


@router.post("/approvals/{aid}/delegate")
def approval_delegate(aid: int, d: DelegateIn, db: Session = Depends(get_db), user: User = Depends(require_permission("approval.decide"))):
    a = db.get(Approval, aid)
    if not a:
        raise HTTPException(404)
    target = db.scalars(select(User).where(User.email == d.to.lower())).first()
    from ..security.rbac import has

    if target is None or not has(target, "approval.decide"):
        raise HTTPException(422, "delegate must be an existing user with approval.decide")
    try:
        gov.delegate_approval(db, a, user.email, target.email)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    db.commit()
    return _cols(a)


# ------------------------------------------------------------------ tool security gateway
@router.get("/tools")
def tools_list(db: Session = Depends(get_db), _: User = Depends(require_permission("tools.read"))):
    from ..governance import tool_gateway as G

    G.ensure_default_grants(db)
    db.commit()
    return {"tools": [t.public() for t in G.TOOLS.values()], "operations": G.OPERATIONS,
            "note": "deny by default: an agent can use a tool only through an explicit grant, and never beyond the role of the user it works for"}


@router.get("/tools/grants")
def tools_grants(db: Session = Depends(get_db), _: User = Depends(require_permission("tools.read"))):
    return [_cols(g) for g in db.scalars(select(ToolGrant).order_by(ToolGrant.subject_kind, ToolGrant.subject_id, ToolGrant.tool))]


class GrantIn(BaseModel):
    subject_kind: Literal["agent", "workflow", "role"]
    subject_id: str = Field(min_length=1, max_length=96)
    tool: str
    operations: list[Literal["READ", "CREATE", "UPDATE", "DELETE", "EXECUTE", "ADMINISTER"]] = Field(min_length=1)
    environments: list[str] = []
    max_calls_per_day: int | None = Field(None, ge=1, le=1_000_000)
    credential_scope: str = Field("", max_length=96)
    expires_at: datetime | None = None
    reason: str = Field(min_length=3, max_length=2000)
    approval_id: int | None = None


@router.post("/tools/grants")
def tools_grant(g: GrantIn, db: Session = Depends(get_db), user: User = Depends(require_permission("tools.grant"))):
    from ..governance import tool_gateway as G

    t = G.TOOLS.get(g.tool)
    if t is None:
        raise HTTPException(404, f"unknown tool {g.tool}")
    if set(g.operations) - {t.operation}:
        raise HTTPException(422, f"{g.tool} supports only {t.operation}")
    payload = g.model_dump(exclude={"approval_id"}, mode="json")
    pending = _governed(db, user, "tools.grant", payload, g.approval_id, f"Grant {g.tool} {g.operations} to {g.subject_kind} {g.subject_id}")
    if pending is not None:
        return pending
    row = ToolGrant(**{k: v for k, v in g.model_dump(exclude={"approval_id"}).items()}, created_by=user.email)
    db.add(row)
    db.flush()
    gov.audit(db, user.email, "tools.grant", f"grant:{row.id}", grant=payload, approval=g.approval_id)
    db.commit()
    return {"status": "applied", "grant": _cols(row)}


@router.delete("/tools/grants/{gid}")
def tools_revoke(gid: int, db: Session = Depends(get_db), user: User = Depends(require_permission("tools.grant"))):
    g = db.get(ToolGrant, gid)
    if g is None:
        raise HTTPException(404)
    g.enabled = False  # kept for history; revoking access never needs a second approval
    gov.audit(db, user.email, "tools.revoke", f"grant:{gid}", subject=f"{g.subject_kind}:{g.subject_id}", tool=g.tool)
    db.commit()
    return {"status": "revoked", "grant": gid}


@router.get("/tools/invocations")
def tools_invocations(tool: str | None = None, agent: str | None = None, status: str | None = None, limit: int = Query(200, le=2000),
                      db: Session = Depends(get_db), _: User = Depends(require_permission("tools.read"))):
    q = select(ToolInvocation).order_by(ToolInvocation.id.desc()).limit(limit)
    for col, v in (("tool", tool), ("agent_id", agent), ("status", status)):
        if v:
            q = q.where(getattr(ToolInvocation, col) == v)
    return [_cols(i) for i in db.scalars(q)]


class InvokeIn(BaseModel):
    args: dict[str, Any] = {}
    approval_id: int | None = None


def gateway_response(db: Session, fn) -> Any:
    from fastapi.responses import JSONResponse

    from ..governance.tool_gateway import GatewayDenied

    try:
        out = fn()
        db.commit()
        return out
    except GatewayDenied as e:
        db.commit()  # the denial itself is evidence: invocation row + audit event are kept
        code = {"invalid": 422, "pending_approval": 202, "not_configured": 409, "budget_exhausted": 429, "error": 502}.get(e.status, 403)
        if "unknown tool" in str(e):
            code = 404
        return JSONResponse({"status": e.status, "detail": str(e), "approval_id": e.approval_id, "decision": e.decision,
                             "invocation_id": getattr(e, "invocation_id", None)}, status_code=code)


@router.post("/tools/{tool}/invoke")
def tools_invoke(tool: str, b: InvokeIn, db: Session = Depends(get_db), user: User = Depends(require_permission("tools.invoke"))):
    from ..governance import tool_gateway as G

    G.ensure_default_grants(db)
    return gateway_response(db, lambda: G.invoke(db, tool, b.args, user=user, approval_id=b.approval_id))


# ------------------------------------------------------------------ knowledge vault: classification and access
class AccessIn(BaseModel):
    classification: Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", "HIGHLY_SENSITIVE"] | None = None
    collection: str | None = Field(None, max_length=96)
    access: dict[str, list[str]] | None = None
    approval_id: int | None = None


@router.patch("/vault/documents/{did}/access")
def vault_document_access(did: int, b: AccessIn, db: Session = Depends(get_db), user: User = Depends(require_permission("knowledge.admin"))):
    """Narrowing access applies at once; WIDENING it (lower classification, more readers) is RESTRICTED — a second
    person approves exactly this change. Cached answers quoting the document are purged either way."""
    from ..daemon import semantic_cache
    from ..knowledge import vault
    from ..models import Collection, Document

    d = db.get(Document, did)
    if d is None:
        raise HTTPException(404, "document not found")
    cols = {c.name: c for c in db.scalars(select(Collection))}
    old_cls, old_acc = vault.effective(d.classification, d.access, cols.get(d.collection))
    new_doc_cls = b.classification or d.classification
    new_doc_acc = b.access if b.access is not None else (d.access or {})
    new_cls, new_acc = vault.effective(new_doc_cls, new_doc_acc, cols.get(b.collection or d.collection))
    payload = {"document": did, "classification": new_doc_cls, "collection": b.collection or d.collection, "access": new_doc_acc}
    if vault.widens(old_cls, old_acc, new_cls, new_acc):
        pending = _governed(db, user, "knowledge.declassify", payload, b.approval_id, f"Widen access to document {did} ({old_cls} → {new_cls})")
        if pending is not None:
            return pending
    d.classification, d.access, d.collection = new_doc_cls, new_doc_acc, b.collection or d.collection
    purged = semantic_cache.purge_document(db, did)
    gov.audit(db, user.email, "knowledge.access", f"document:{did}", before={"classification": old_cls, "access": old_acc},
              after={"classification": new_cls, "access": new_acc}, collection=d.collection, cache_purged=purged, approval=b.approval_id)
    db.commit()
    return {"status": "applied", "document": did, "classification": new_cls, "access": new_acc, "collection": d.collection, "cache_purged": purged}


class CollectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=96, pattern=r"^[a-z0-9_.-]+$")
    description: str = ""
    classification: Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", "HIGHLY_SENSITIVE"] = "INTERNAL"
    access: dict[str, list[str]] = {}
    approval_id: int | None = None


@router.get("/vault/collections")
def vault_collections(db: Session = Depends(get_db), _: User = Depends(require_permission("knowledge.read"))):
    from ..models import Collection, Document

    counts = dict(db.execute(select(Document.collection, func.count(Document.id)).group_by(Document.collection)).all())
    return [{**_cols(c), "documents": counts.get(c.name, 0)} for c in db.scalars(select(Collection).order_by(Collection.name))] + \
        ([{"name": "general", "classification": "INTERNAL", "access": {}, "documents": counts.get("general", 0), "implicit": True}]
         if db.get(Collection, "general") is None else [])


@router.post("/vault/collections")
def vault_collection_upsert(c: CollectionIn, db: Session = Depends(get_db), user: User = Depends(require_permission("knowledge.admin"))):
    from ..daemon import semantic_cache
    from ..knowledge import vault
    from ..models import Collection, Document

    row = db.get(Collection, c.name)
    payload = c.model_dump(exclude={"approval_id"})
    if row is not None and vault.widens(row.classification, row.access, c.classification, c.access):
        pending = _governed(db, user, "knowledge.declassify", payload, c.approval_id, f"Widen access to collection {c.name}")
        if pending is not None:
            return pending
    if row is None:
        row = Collection(name=c.name, owner=user.email)
        db.add(row)
    row.description, row.classification, row.access = c.description, c.classification, c.access
    purged = sum(semantic_cache.purge_document(db, did) for (did,) in db.execute(select(Document.id).where(Document.collection == c.name)))
    gov.audit(db, user.email, "knowledge.collection", f"collection:{c.name}", classification=c.classification, access=c.access,
              cache_purged=purged, approval=c.approval_id)
    db.commit()
    return {"status": "applied", "collection": _cols(row)}


# ------------------------------------------------------------------ observability: runs + replay
def _started_by(db: Session, rid: int, email: str) -> bool:
    """The run, or one of its ancestors (a visitor's G-sus run → its delegated tasks), was started by `email`."""
    from ..models import Run

    seen = 0
    while rid and seen < 20:
        r = db.get(Run, rid)
        if r is None:
            return False
        if r.user_email == email:
            return True
        rid, seen = r.parent_id, seen + 1
    return False


@router.get("/runs")
def runs_list(kind: str | None = None, status: str | None = None, agent: str | None = None, limit: int = Query(100, le=1000),
              db: Session = Depends(get_db), user: User = Depends(require_permission("runs.read"))):
    from ..models import Run

    q = select(Run).order_by(Run.id.desc()).limit(limit)
    if user.role == "demo":  # public demo: a visitor sees only executions they started
        q = q.where(Run.user_email == user.email)
    for col, v in (("kind", kind), ("status", status), ("agent_id", agent)):
        if v:
            q = q.where(getattr(Run, col) == v)
    return [_cols(r) for r in db.scalars(q)]


@router.get("/runs/{rid}/replay")
def runs_replay(rid: int, db: Session = Depends(get_db), user: User = Depends(require_permission("runs.read"))):
    from ..governance import observability

    if user.role == "demo" and not _started_by(db, rid, user.email):
        raise HTTPException(404, "run not found")
    try:
        out = observability.replay(db, rid)
    except LookupError:
        raise HTTPException(404, "run not found") from None
    gov.audit(db, user.email, "runs.replay", f"run:{rid}")
    db.commit()
    return out


# ------------------------------------------------------------------ resource & cost: hard budgets
class BudgetIn(BaseModel):
    scope_kind: Literal["user", "agent", "workflow", "global"]
    scope_id: str = Field("*", max_length=96)
    metric: Literal["usd", "tokens", "model_calls", "tool_calls"]
    period: Literal["day", "month"] = "day"
    limit: float = Field(gt=0)
    approval_id: int | None = None


@router.get("/budgets")
def budgets_list(db: Session = Depends(get_db), _: User = Depends(require_permission("policy.read"))):
    from ..governance import usage
    from ..models import BudgetRule

    out = []
    for r in db.scalars(select(BudgetRule).order_by(BudgetRule.id)):
        used = usage.used(db, f"budget:{r.id}:{r.scope_id}") if r.period == "day" else None
        out.append({**_cols(r), "used_today": used})
    return out


@router.post("/budgets")
def budgets_create(b: BudgetIn, db: Session = Depends(get_db), user: User = Depends(require_permission("system.configure"))):
    from ..models import BudgetRule

    payload = b.model_dump(exclude={"approval_id"})
    pending = _governed(db, user, "budget.change", payload, b.approval_id, f"Budget: {b.scope_kind} {b.scope_id} {b.metric} ≤ {b.limit:g}/{b.period}")
    if pending is not None:
        return pending
    row = BudgetRule(**payload, created_by=user.email)
    db.add(row)
    db.flush()
    gov.audit(db, user.email, "budget.change", f"budget:{row.id}", budget=payload, approval=b.approval_id)
    db.commit()
    return {"status": "applied", "budget": _cols(row)}


@router.delete("/budgets/{bid}")
def budgets_disable(bid: int, approval_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(require_permission("system.configure"))):
    """Removing a limit loosens control, so it is governed like creating one."""
    from ..models import BudgetRule

    r = db.get(BudgetRule, bid)
    if r is None:
        raise HTTPException(404)
    pending = _governed(db, user, "budget.change", {"disable": bid}, approval_id, f"Remove budget #{bid}")
    if pending is not None:
        return pending
    r.enabled = False
    gov.audit(db, user.email, "budget.disable", f"budget:{bid}", approval=approval_id)
    db.commit()
    return {"status": "disabled", "budget": bid}


# ------------------------------------------------------------------ deployment manager: profiles + egress
class DeploymentIn(BaseModel):
    profile: Literal["LOCAL_DEVELOPMENT", "SELF_HOSTED", "PRIVATE_NETWORK", "CUSTOMER_VPC", "ON_PREMISE", "AIR_GAPPED"]
    egress_allowlist: list[str] = []
    allow_private_networks: bool = True
    approval_id: int | None = None


OFFLINE_FEATURES = {
    "works offline / air-gapped": ["local models (chat, eco, deep reasoning, embeddings)", "Knowledge Vault ingest, search, ask", "agents and workflows",
                                   "policy, approvals, tool gateway (internal tools)", "audit, export, verification", "runs and replay",
                                   "evaluation suites and release gates", "Control Center, telemetry"],
    "needs outbound network": ["external AI providers", "internet research and monitors", "web.fetch, email.send tools",
                               "model downloads (use verified import packages instead)", "commerce connectors"],
}


@router.get("/deployment")
def deployment(db: Session = Depends(get_db), _: User = Depends(require_permission("policy.read"))):
    from ..daemon import state
    from ..governance import egress

    st = state.load(db)
    return {"deployment": st.get("deployment") or {"profile": "SELF_HOSTED", "egress_allowlist": [], "allow_private_networks": True},
            "offline_mode": st["offline_mode"], "profiles": egress.PROFILES, "egress": egress.report(), "features": OFFLINE_FEATURES}


@router.post("/deployment")
def deployment_set(d: DeploymentIn, db: Session = Depends(get_db), user: User = Depends(require_permission("system.configure"))):
    """Tightening (→ AIR_GAPPED, fewer allow-list entries) applies at once; loosening is RESTRICTED (second person)."""
    from ..daemon import state
    from ..governance import egress

    st = state.load(db)
    cur = st.get("deployment") or {"profile": "SELF_HOSTED", "egress_allowlist": [], "allow_private_networks": True}
    loosens = (cur["profile"] == "AIR_GAPPED" and d.profile != "AIR_GAPPED") or bool(set(d.egress_allowlist) - set(cur.get("egress_allowlist", []))) \
        or (d.allow_private_networks and not cur.get("allow_private_networks", True))
    payload = d.model_dump(exclude={"approval_id"})
    if loosens:
        pending = _governed(db, user, "deploy.loosen_egress", payload, d.approval_id, f"Loosen deployment egress → {d.profile}")
        if pending is not None:
            return pending
    changes: dict[str, Any] = {"deployment": payload}
    if d.profile == "AIR_GAPPED":
        changes["offline_mode"] = True  # never a silent fall back to cloud services
    state.update(db, **changes)
    egress.invalidate()
    gov.audit(db, user.email, "deploy.profile", "deployment", before=cur, after=payload, approval=d.approval_id)
    db.commit()
    return {"status": "applied", "deployment": payload, "offline_mode": state.load(db)["offline_mode"]}


@router.get("/deployment/egress/verify")
def deployment_verify(db: Session = Depends(get_db), user: User = Depends(require_permission("audit.verify"))):
    from ..governance import egress

    out = {"probe": egress.probe(), "report": egress.report()}
    gov.audit(db, user.email, "deploy.egress_verify", "deployment", blocked=out["probe"]["blocked"], enforcing=out["report"]["enforcing"])
    db.commit()
    return out


# ------------------------------------------------------------------ evaluation lab: release gates
class GateIn(BaseModel):
    target_kind: Literal["prompt", "model", "workflow", "agent", "tool", "retrieval", "policy"]
    suite: str = Field(min_length=3, max_length=64)
    min_score: float = Field(ge=0, le=1)
    mandatory: bool = True
    approval_id: int | None = None


class GateCheckIn(BaseModel):
    target_kind: Literal["prompt", "model", "workflow", "agent", "tool", "retrieval", "policy"]
    target_ref: str = Field(min_length=1, max_length=160)


@router.get("/gates")
def gates_list(db: Session = Depends(get_db), _: User = Depends(require_permission("policy.read"))):
    from ..governance import gates
    from ..models import GateRun, ReleaseGate

    gates.ensure_defaults(db)
    db.commit()
    return {"gates": [_cols(g) for g in db.scalars(select(ReleaseGate).order_by(ReleaseGate.target_kind, ReleaseGate.id))],
            "runs": [_cols(r) for r in db.scalars(select(GateRun).order_by(GateRun.id.desc()).limit(50))],
            "suites": sorted(gates.suites()) + ["benchmark_accuracy"]}


@router.post("/gates")
def gates_upsert(g: GateIn, db: Session = Depends(get_db), user: User = Depends(require_permission("gates.write"))):
    from ..models import ReleaseGate

    payload = g.model_dump(exclude={"approval_id"})
    pending = _governed(db, user, "gates.change", payload, g.approval_id, f"Release gate {g.target_kind}/{g.suite} ≥ {g.min_score}")
    if pending is not None:
        return pending
    row = db.scalars(select(ReleaseGate).where(ReleaseGate.target_kind == g.target_kind, ReleaseGate.suite == g.suite)).first()
    if row is None:
        row = ReleaseGate(target_kind=g.target_kind, suite=g.suite, created_by=user.email, min_score=g.min_score)
        db.add(row)
    row.min_score, row.mandatory, row.enabled = g.min_score, g.mandatory, True
    db.flush()
    gov.audit(db, user.email, "gates.change", f"gate:{row.id}", gate=payload, approval=g.approval_id)
    db.commit()
    return {"status": "applied", "gate": _cols(row)}


@router.post("/gates/check")
def gates_check(c: GateCheckIn, db: Session = Depends(get_db), user: User = Depends(require_permission("eval.run"))):
    from ..governance import gates

    try:
        run = gates.check(db, c.target_kind, c.target_ref, user.email)
    except gates.GateFailed as e:
        db.commit()
        return {"passed": False, "gate_run": _cols(e.run)}
    db.commit()
    return {"passed": True, "gate_run": _cols(run)}


# ------------------------------------------------------------------ apply an approved governance change
# A governed change is filed as an approval the first time it is requested; it is applied by calling the same endpoint
# again with that approval. The interface had no way to do the second step, so approved changes could never be applied.
# This endpoint repeats the stored request through the ORIGINAL route, so every check runs again: the caller's own
# permission, the policy decision, approval bound to the exact payload, decided by someone else, not expired, revoked or used.
_APPLY: dict[str, str] = {"policy.write": "policy.write", "audit.prune": "audit.retention", "tools.grant": "tools.grant",
                          "knowledge.declassify": "knowledge.admin", "budget.change": "system.configure",
                          "deploy.loosen_egress": "system.configure", "gates.change": "gates.write",
                          "personnel.permission_level": "agent.develop"}


@router.post("/approvals/{aid}/apply")
def approval_apply(aid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    from ..security.rbac import has

    a = db.get(Approval, aid)
    if a is None:
        raise HTTPException(404)
    perm = _APPLY.get(a.action)
    if perm is None:
        raise HTTPException(422, f"{a.action} is applied by the agent or tool call that requested it, not from here")
    if not has(user, perm):
        raise HTTPException(403, f"applying {a.action} needs the {perm} permission")
    if a.status != "approved":
        raise HTTPException(409, f"approval #{aid} is {a.status}, not approved")
    p = dict(a.payload or {})
    if a.action == "policy.write":
        return policy_disable(p["disable"], aid, db, user) if "disable" in p else policy_upsert(RuleIn(**p, approval_id=aid), db, user)
    if a.action == "audit.prune":
        return audit_prune(PruneIn(before=p["before"], approval_id=aid), db, user)
    if a.action == "tools.grant":
        return tools_grant(GrantIn(**p, approval_id=aid), db, user)
    if a.action == "knowledge.declassify":
        if "document" in p:
            return vault_document_access(p["document"], AccessIn(classification=p.get("classification"), collection=p.get("collection"),
                                                                 access=p.get("access"), approval_id=aid), db, user)
        return vault_collection_upsert(CollectionIn(**p, approval_id=aid), db, user)
    if a.action == "budget.change":
        return budgets_disable(p["disable"], aid, db, user) if "disable" in p else budgets_create(BudgetIn(**p, approval_id=aid), db, user)
    if a.action == "deploy.loosen_egress":
        return deployment_set(DeploymentIn(**p, approval_id=aid), db, user)
    if a.action == "personnel.permission_level":
        from ..personnel import creator

        try:
            agent = creator.apply_elevation(db, aid, actor=user.email, role=user.role)
        except creator.CreatorError as e:
            db.rollback()
            raise HTTPException(e.status, str(e)) from e
        db.commit()
        return {"status": "applied", "agent": agent.id, "permission_level": agent.permission_level, "lifecycle": agent.lifecycle}
    return gates_upsert(GateIn(**p, approval_id=aid), db, user)
