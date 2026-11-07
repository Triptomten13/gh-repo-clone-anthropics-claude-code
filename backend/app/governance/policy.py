"""DAEMON ORCHESTRATION CORE — Policy Decision Point (decide) and Policy Enforcement Point (enforce).

Policies are enforced HERE, in backend code, before an operation runs — never by asking a model to behave. Nothing an
agent writes can change a decision: inputs are identities, the requested action, classifications, amounts and
approval records, all taken from the database and the request, not from model output.

Categories (approval levels):
  1 AUTONOMOUS         allowed (e.g. reading authorised information, drafting)
  2 SUPERVISED         allowed, recorded and surfaced (internal reversible operations)
  3 APPROVAL_REQUIRED  blocked until a valid human approval exists (external publishing, deletions, sends)
  4 RESTRICTED         approval by someone OTHER than the requester and the person it is for (four eyes);
                       financial transactions, governance changes by humans
  5 PROHIBITED         never executable through the platform (e.g. an agent changing policy, audit history,
                       its own permissions or budget, or deploying unreviewed changes)
Mandatory floors: built-in minimum categories that configurable rules may RAISE but never LOWER — so a rule can
never remove a mandatory approval checkpoint. A valid approval is: approved, by a different person, not expired, not
revoked, not used before (single use), for the same action and — when given — the same arguments (payload hash).
Silence is never approval: pending approvals stay pending and expire.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from enum import IntEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Approval, ApprovalStatus, PolicyRule
from ..security.permissions import ACTION_LEVELS


class Category(IntEnum):
    AUTONOMOUS = 1
    SUPERVISED = 2
    APPROVAL_REQUIRED = 3
    RESTRICTED = 4
    PROHIBITED = 5


CLASSIFICATIONS = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", "HIGHLY_SENSITIVE"]
APPROVAL_TTL_H = float(os.getenv("APPROVAL_TTL_HOURS", "72"))

# governance actions an AGENT may never perform, whatever any rule says (spec §13)
AGENT_PROHIBITED = ["policy.*", "tools.grant", "tools.revoke", "budget.*", "approval.*", "audit.*", "permissions.*", "users.*",
                    "security.*", "deploy.*", "gates.*", "credentials.*", "providers.approve"]
# never through the platform, for anyone
PROHIBITED = ["audit.modify", "audit.delete", "permissions.self_grant", "budget.self_increase", "deploy.unreviewed",
              "policy.disable_mandatory"]
# built-in floors for actions that are not in ACTION_LEVELS
FLOORS = {"tool:*.DELETE": Category.APPROVAL_REQUIRED, "tool:*.EXECUTE.external": Category.APPROVAL_REQUIRED,
          "tool:*.ADMINISTER": Category.RESTRICTED, "policy.*": Category.RESTRICTED, "tools.grant": Category.RESTRICTED,
          "tools.revoke": Category.SUPERVISED, "budget.*": Category.RESTRICTED, "gates.*": Category.RESTRICTED,
          "knowledge.reclassify": Category.SUPERVISED, "knowledge.declassify": Category.RESTRICTED,
          "knowledge.delete": Category.APPROVAL_REQUIRED, "audit.prune": Category.RESTRICTED,
          "providers.approve": Category.RESTRICTED,  # making a provider routable is a governance change
          # Model Hunter / Account Vault: downloading a discovered model and connecting an external account need a person
          "models.acquire": Category.APPROVAL_REQUIRED, "accounts.provision": Category.APPROVAL_REQUIRED,
          "accounts.paid": Category.RESTRICTED}


class PolicyDenied(Exception):
    def __init__(self, decision: Decision):
        super().__init__("; ".join(decision.reasons))
        self.decision = decision


class ApprovalRequired(PolicyDenied):
    pass


@dataclass
class Request:
    action: str
    agent_id: str | None = None          # the agent asking (None = a human acting directly)
    user_email: str | None = None        # the human the work is for / who acts
    user_role: str | None = None
    workflow: str | None = None
    classification: str = "INTERNAL"     # highest classification of the data involved
    external: bool = False               # leaves the deployment boundary (send, publish, external API)
    amount_sek: float | None = None
    environment: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    approval_id: int | None = None
    payload: dict[str, Any] | None = None


@dataclass
class Decision:
    allowed: bool
    category: int
    category_name: str
    reasons: list[str]
    rules: list[str] = field(default_factory=list)       # "key@version" of every rule applied
    policy_version: str = ""
    approval_id: int | None = None
    obligations: list[str] = field(default_factory=list)  # e.g. "notify", "four_eyes"

    def public(self) -> dict[str, Any]:
        return asdict(self)


def payload_hash(payload: dict[str, Any] | None) -> str:
    return hashlib.sha256(json.dumps(payload or {}, sort_keys=True, default=str).encode()).hexdigest() if payload else ""


def _match(pattern: str, action: str) -> bool:
    return fnmatch.fnmatchcase(action, pattern)


def _floor(req: Request) -> tuple[Category, str]:
    a = req.action
    if a in ACTION_LEVELS:
        lvl = int(ACTION_LEVELS[a])
        cat = Category.AUTONOMOUS if lvl <= 1 else Category.SUPERVISED if lvl <= 3 else Category.APPROVAL_REQUIRED if lvl == 4 else Category.RESTRICTED
        return cat, f"built-in: {a} is permission level {lvl}"
    probe = a + (".external" if req.external and a.endswith(".EXECUTE") else "")
    best = None
    for pat, cat in FLOORS.items():
        if _match(pat, probe) and (best is None or cat > best[0]):
            best = (cat, f"built-in floor {pat}")
    if best:
        return best
    if a.startswith("tool:"):
        return Category.AUTONOMOUS, "built-in: read/create tool operations are autonomous once granted"
    return Category.RESTRICTED, f"built-in: unknown action '{a}' is treated as restricted"


def active_rules(db: Session) -> list[PolicyRule]:
    return list(db.scalars(select(PolicyRule).where(PolicyRule.enabled.is_(True), PolicyRule.superseded_at.is_(None))
                           .order_by(PolicyRule.priority, PolicyRule.id)))


def policy_version(rules: list[PolicyRule]) -> str:
    return hashlib.sha256("|".join(f"{r.key}@{r.version}" for r in sorted(rules, key=lambda r: r.key)).encode()).hexdigest()[:16]


def _conditions_hold(c: dict[str, Any], req: Request) -> bool:
    def within(name: str, value: Any) -> bool:
        allowed = c.get(name)
        return not allowed or value in allowed
    if not (within("agents", req.agent_id) and within("roles", req.user_role) and within("workflows", req.workflow)
            and within("environments", req.environment) and within("users", req.user_email)):
        return False
    if "actor" in c and c["actor"] != ("agent" if req.agent_id else "human"):
        return False
    if "min_classification" in c and CLASSIFICATIONS.index(req.classification) < CLASSIFICATIONS.index(c["min_classification"]):
        return False
    if "min_amount_sek" in c and (req.amount_sek or 0) < c["min_amount_sek"]:
        return False
    if "external" in c and bool(c["external"]) != req.external:
        return False
    return True


def decide(db: Session, req: Request) -> Decision:
    reasons: list[str] = []
    applied: list[str] = []
    rules = active_rules(db)
    version = policy_version(rules)
    # 1. absolute prohibitions
    if any(_match(p, req.action) for p in PROHIBITED):
        return Decision(False, 5, "PROHIBITED", [f"'{req.action}' is never executable through the platform"], [], version)
    if req.agent_id and any(_match(p, req.action) for p in AGENT_PROHIBITED):
        return Decision(False, 5, "PROHIBITED", [f"agents may not perform governance actions ('{req.action}')"], [], version)
    # 2. mandatory floor
    floor, why = _floor(req)
    cat = floor
    reasons.append(why)
    # 3. configurable rules (may raise; may lower only down to the floor)
    for r in rules:
        if _match(r.action, req.action) and _conditions_hold(r.conditions or {}, req):
            new = Category(r.category)
            if new < floor:
                reasons.append(f"rule {r.key}@{r.version} would lower below the mandatory floor {floor.name} — ignored")
                continue
            cat = new
            applied.append(f"{r.key}@{r.version}")
            reasons.append(f"rule {r.key}@{r.version}: {new.name}" + (f" ({r.reason})" if r.reason else ""))
    # 4. data classification
    ci = CLASSIFICATIONS.index(req.classification) if req.classification in CLASSIFICATIONS else 1
    if req.external and ci >= CLASSIFICATIONS.index("HIGHLY_SENSITIVE"):
        cat = Category.PROHIBITED
        reasons.append("HIGHLY_SENSITIVE data may not leave the deployment")
    elif req.external and ci >= CLASSIFICATIONS.index("CONFIDENTIAL") and cat < Category.APPROVAL_REQUIRED:
        cat = Category.APPROVAL_REQUIRED
        reasons.append(f"{req.classification} data leaving the deployment needs approval")
    if cat == Category.PROHIBITED:
        return Decision(False, 5, "PROHIBITED", reasons, applied, version)
    if cat <= Category.SUPERVISED:
        return Decision(True, int(cat), cat.name, reasons, applied, version, obligations=["notify"] if cat == Category.SUPERVISED else [])
    # 5. approval
    ok, why = approval_valid(db, req, cat)
    reasons.append(why)
    return Decision(ok, int(cat), cat.name, reasons, applied, version, approval_id=req.approval_id if ok else None,
                    obligations=["four_eyes"] if cat == Category.RESTRICTED else [])


def _aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=UTC) if dt is not None and dt.tzinfo is None else dt


def approval_valid(db: Session, req: Request, cat: Category, *, lock: bool = False) -> tuple[bool, str]:
    if req.approval_id is None:
        return False, f"{cat.name}: no approval supplied"
    q = select(Approval).where(Approval.id == req.approval_id)
    a = db.execute(q.with_for_update() if lock else q).scalar_one_or_none()
    if a is None:
        return False, f"approval #{req.approval_id} does not exist"
    if a.action != req.action:
        return False, f"approval #{a.id} is for '{a.action}', not '{req.action}'"
    if a.status != ApprovalStatus.approved.value:
        return False, f"approval #{a.id} is {a.status}"
    if a.revoked_at is not None:
        return False, f"approval #{a.id} was revoked by {a.revoked_by}"
    if a.consumed_at is not None:
        return False, f"approval #{a.id} was already used at {a.consumed_at:%Y-%m-%d %H:%M} (single use)"
    if a.expires_at is not None and _aware(a.expires_at) <= datetime.now(UTC):
        return False, f"approval #{a.id} expired at {a.expires_at:%Y-%m-%d %H:%M}"
    if a.payload_hash and req.payload is not None and a.payload_hash != payload_hash(req.payload):
        return False, f"approval #{a.id} authorised different arguments"
    if a.decided_by and (a.requested_by == f"user:{a.decided_by}" or a.decided_by == a.on_behalf_of):
        return False, f"approval #{a.id} was decided by the requester — not independent"
    if cat == Category.RESTRICTED and req.user_email and a.decided_by == req.user_email:
        return False, f"approval #{a.id}: RESTRICTED actions need a second person"
    return True, f"approval #{a.id} by {a.decided_by} is valid"


def enforce(db: Session, req: Request, *, consume: bool = True, request_approval_title: str | None = None) -> Decision:
    """PEP: decide, record, and raise unless allowed. A valid approval is consumed (single use) under a row lock, so
    two concurrent executions cannot both use it. Optionally files the approval request when one is needed."""
    from . import core as gov

    d = decide(db, req)
    if d.allowed and d.category >= Category.APPROVAL_REQUIRED and consume:
        # single use, atomically: exactly one concurrent caller can flip consumed_at from NULL
        from sqlalchemy import update

        res = db.execute(update(Approval).where(Approval.id == req.approval_id, Approval.consumed_at.is_(None), Approval.revoked_at.is_(None))
                         .values(consumed_at=datetime.now(UTC)))
        if res.rowcount != 1:
            d = Decision(False, d.category, d.category_name, [*d.reasons, f"approval #{req.approval_id} was already used or revoked"],
                         d.rules, d.policy_version)
        else:
            obj = db.get(Approval, req.approval_id)
            if obj is not None:
                db.refresh(obj)  # only this row: never discard the caller's other pending changes
    from . import observability

    observability.event("policy", req.action, {"allowed": d.allowed, "category": d.category_name, "rules": d.rules, "policy_version": d.policy_version,
                                               "approval_id": d.approval_id or req.approval_id, "reasons": d.reasons[-3:]})
    actor = req.user_email or (f"agent:{req.agent_id}" if req.agent_id else "system")
    if d.category >= Category.SUPERVISED or not d.allowed:
        gov.audit(db, actor, "policy.decision", req.action, allowed=d.allowed, category=d.category_name, agent=req.agent_id,
                  workflow=req.workflow, classification=req.classification, rules=d.rules, policy_version=d.policy_version,
                  approval=d.approval_id, reasons=d.reasons[-3:])
    if d.allowed:
        return d
    if d.category in (Category.APPROVAL_REQUIRED, Category.RESTRICTED):
        if request_approval_title and req.approval_id is None:
            a = request_approval(db, req, request_approval_title, Category(d.category))
            d.approval_id = a.id
            d.reasons.append(f"approval #{a.id} requested")
        raise ApprovalRequired(d)
    raise PolicyDenied(d)


def request_approval(db: Session, req: Request, title: str, cat: Category, description: str = "") -> Approval:
    from . import core as gov

    a = gov.request_approval(db, req.action, title, f"agent:{req.agent_id}" if req.agent_id else f"user:{req.user_email}",
                             description, req.payload or {}, req.amount_sek)
    a.category, a.on_behalf_of = int(cat), req.user_email or ""
    a.payload_hash = payload_hash(req.payload)
    a.expires_at = a.expires_at or datetime.now(UTC) + timedelta(hours=APPROVAL_TTL_H)
    db.flush()
    return a
