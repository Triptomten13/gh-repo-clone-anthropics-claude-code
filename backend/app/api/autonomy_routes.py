"""Model Hunter, Model Championship, Devil's Advocate and Account Vault.

Permissions: `models.manage` searches, requests acquisitions and starts championships; downloading a discovered model
needs an approved approval (four eyes) and an admin to start it; `runs.read` reads; `work.run` asks the Devil's Advocate;
`system.configure` proposes and revokes accounts; connecting a secret is admin-only (like every stored credential).
Secrets never appear in any response.
"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal, get_db
from ..models import Championship, Critique, ModelCandidate, ServiceAccount, User
from ..security.auth import require_role
from ..security.rbac import require_permission

router = APIRouter(prefix="/api", tags=["autonomy"])
_running = threading.Lock()


def _cols(o: Any, skip: tuple[str, ...] = ()) -> dict[str, Any]:
    return {c.name: getattr(o, c.name) for c in o.__table__.columns if c.name not in skip}


# ------------------------------------------------------------------ Model Hunter
@router.get("/hunter")
def hunter_board(db: Session = Depends(get_db), _: User = Depends(require_permission("runs.read"))):
    from ..autonomy import hunter
    from ..daemon import hardware

    b = hunter.board(db)
    snap = hardware.snapshot()
    return {**{k: v for k, v in b.items() if k != "candidates"}, "candidates": [_cols(c) for c in b["candidates"]],
            "hardware": {"ram_gb": round(snap["ram_total_bytes"] / 1e9, 1), "ram_free_gb": round((snap["ram_available_bytes"] or 0) / 1e9, 1),
                         "disk_free_gb": round(snap["disk_free_bytes"] / 1e9, 1), "accelerator": snap.get("accelerator"),
                         "cpu": (snap.get("cpu") or {}).get("model"), "cores": (snap.get("cpu") or {}).get("usable_cores")}}


class DiscoverIn(BaseModel):
    task: str = "general"
    limit: int = Field(12, ge=1, le=40)


@router.post("/hunter/discover")
def hunter_discover(b: DiscoverIn, db: Session = Depends(get_db), user: User = Depends(require_permission("models.manage"))):
    from ..autonomy import hunter

    try:
        return hunter.discover(db, b.task, limit=b.limit, actor=user.email)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e
    except Exception as e:  # noqa: BLE001 — network or Hub errors are reported, never replaced by invented results
        raise HTTPException(502, f"Hugging Face could not be searched: {type(e).__name__}") from e


@router.post("/hunter/candidates/{cid}/request")
def hunter_request(cid: int, db: Session = Depends(get_db), user: User = Depends(require_permission("models.manage"))):
    from ..autonomy import hunter

    try:
        c = hunter.request_acquisition(db, cid, actor=user.email, user_email=user.email)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    return _cols(c)


def _acquire_bg(cid: int, actor: str) -> None:
    from ..autonomy import hunter

    s = SessionLocal()
    try:
        hunter.acquire(s, cid, actor=actor)
    finally:
        s.close()


@router.post("/hunter/candidates/{cid}/acquire", status_code=202)
def hunter_acquire(cid: int, db: Session = Depends(get_db), user: User = Depends(require_role("admin"))):
    c = db.get(ModelCandidate, cid)
    if c is None:
        raise HTTPException(404)
    from ..models import Approval

    if c.status == "pending_approval":
        ap = db.get(Approval, c.approval_id) if c.approval_id else None
        if not (ap and ap.status == "approved" and ap.revoked_at is None):
            raise HTTPException(409, f"approval #{c.approval_id} is not approved yet — another approver decides")
    elif c.status != "approved":
        raise HTTPException(409, f"candidate is {c.status}")
    threading.Thread(target=_acquire_bg, args=(cid, user.email), daemon=True).start()
    return {"status": "acquiring", "candidate": cid}


# ------------------------------------------------------------------ Model Championship
@router.get("/championships")
def championships(db: Session = Depends(get_db), _: User = Depends(require_permission("runs.read"))):
    from ..autonomy import championship

    rows = db.scalars(select(Championship).order_by(Championship.id.desc()).limit(20)).all()
    return {"contenders": [{"key": m.key, "name": m.display_name, "size_gb": round((m.size_bytes or 0) / 1e9, 2)} for m in championship.contenders(db)],
            "hardware": championship.fingerprint(), "suites": championship.suites(), "running": _running.locked(),
            "championships": [_cols(c, ("results", "standings")) for c in rows]}


@router.get("/championships/{chid}")
def championship_detail(chid: int, db: Session = Depends(get_db), _: User = Depends(require_permission("runs.read"))):
    c = db.get(Championship, chid)
    if c is None:
        raise HTTPException(404)
    return _cols(c)


class ChampIn(BaseModel):
    models: list[str] | None = None
    max_seconds: int = Field(2700, ge=60, le=14400)


def _champ_bg(models: list[str] | None, max_seconds: int, actor: str) -> None:
    from ..autonomy import championship

    s = SessionLocal()
    try:
        championship.run(s, actor=actor, models=models, max_seconds=max_seconds)
    finally:
        s.close()
        _running.release()


@router.post("/championships", status_code=202)
def championship_start(b: ChampIn, db: Session = Depends(get_db), user: User = Depends(require_permission("models.manage"))):
    from ..autonomy import championship

    if not championship.contenders(db):
        raise HTTPException(409, "no installed chat model to compete — install models in DAEMON CORE → Models")
    if not _running.acquire(blocking=False):
        raise HTTPException(409, "a championship is already running — local models share this machine's CPU")
    threading.Thread(target=_champ_bg, args=(b.models, b.max_seconds, user.email), daemon=True).start()
    return {"status": "running"}


# ------------------------------------------------------------------ Devil's Advocate
@router.get("/advocate")
def advocate_board(db: Session = Depends(get_db), _: User = Depends(require_permission("runs.read"))):
    from ..autonomy import advocate

    rows = db.scalars(select(Critique).order_by(Critique.id.desc()).limit(50)).all()
    return {"critiques": [_cols(c) for c in rows], "agreement": advocate.agreement(db), "calibration": advocate.calibrate(),
            "modes": advocate.MODES, "protocol": [q for q, _, _ in advocate.PROTOCOL]}


class ReviewIn(BaseModel):
    decision: dict[str, Any]
    mode: str = "DEVILS_ADVOCATE"
    use_model: bool = False


@router.post("/advocate/review")
def advocate_review(b: ReviewIn, db: Session = Depends(get_db), user: User = Depends(require_permission("work.run"))):
    from ..autonomy import advocate

    if not b.decision.get("kind"):
        raise HTTPException(422, "the decision record needs a 'kind'")
    try:
        c = advocate.review(db, {**b.decision, "proposer": b.decision.get("proposer") or f"user:{user.email}"}, mode=b.mode,
                            use_model=b.use_model, actor=user.email)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    db.commit()
    return _cols(c)


class RespondIn(BaseModel):
    response: str = Field(min_length=3, max_length=4000)
    status: str = Field("resolved", pattern="^(resolved|escalated|open)$")


@router.post("/advocate/{crid}/respond")
def advocate_respond(crid: int, b: RespondIn, db: Session = Depends(get_db), user: User = Depends(require_permission("work.run"))):
    from ..governance import core as gov

    c = db.get(Critique, crid)
    if c is None:
        raise HTTPException(404)
    if c.verdict == "block" and b.status == "resolved" and user.role != "admin":
        raise HTTPException(403, "a blocking finding is resolved by changing the decision, or by an admin")
    c.response, c.status = f"{user.email}: {b.response}", b.status
    gov.audit(db, user.email, "advocate.respond", f"critique:{c.id}", status=b.status)
    db.commit()
    return _cols(c)


# ------------------------------------------------------------------ Account Vault
@router.get("/accounts")
def accounts(db: Session = Depends(get_db), _: User = Depends(require_permission("runs.read"))):
    from ..autonomy import accounts as A
    from ..daemon.credentials import ATTESTATION

    rows = db.scalars(select(ServiceAccount).order_by(ServiceAccount.id.desc())).all()
    return {"accounts": [A.public(a) for a in rows], "services": {k: A.research(k) for k in A.SERVICES}, "levels": A.LEVELS,
            "justification": A.JUSTIFICATION_HELP, "attestation": ATTESTATION}


class ProposeIn(BaseModel):
    service: str = Field(min_length=2, max_length=48, pattern=r"^[a-z0-9_.-]+$")
    identity: str = Field(min_length=1, max_length=128)
    purpose: str = Field(min_length=5, max_length=2000)
    scopes: list[str] = Field(default_factory=list, max_length=20)
    justification: dict[str, str] = Field(default_factory=dict)
    level: int = Field(2, ge=0, le=4)
    paid: bool = False


@router.post("/accounts")
def account_propose(b: ProposeIn, db: Session = Depends(get_db), user: User = Depends(require_permission("system.configure"))):
    from ..autonomy import accounts as A

    a = A.propose(db, service=b.service, identity=b.identity, purpose=b.purpose, scopes=b.scopes, justification=b.justification,
                  level=b.level, paid=b.paid, requested_by=f"user:{user.email}")
    return A.public(a)


class ConnectIn(BaseModel):
    secret: str = Field(min_length=8, max_length=4000)
    attestation: str
    expires_at: datetime | None = None


@router.post("/accounts/{aid}/connect")
def account_connect(aid: int, b: ConnectIn, db: Session = Depends(get_db), user: User = Depends(require_role("admin"))):
    from ..autonomy import accounts as A

    try:
        a = A.connect(db, aid, b.secret, attestation=b.attestation, actor=user.email, expires_at=b.expires_at)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    return A.public(a)


@router.post("/accounts/{aid}/health")
def account_health(aid: int, db: Session = Depends(get_db), user: User = Depends(require_permission("system.configure"))):
    from ..autonomy import accounts as A

    try:
        return A.health(db, aid, actor=user.email)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/accounts/{aid}/revoke")
def account_revoke(aid: int, reason: str = "", db: Session = Depends(get_db), user: User = Depends(require_permission("system.configure"))):
    from ..autonomy import accounts as A

    try:
        return A.public(A.revoke(db, aid, actor=user.email, reason=reason))
    except LookupError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/accounts/{aid}/uses")
def account_uses(aid: int, db: Session = Depends(get_db), _: User = Depends(require_permission("audit.read"))):
    """The access log: every time a tool used this account's credential (from the tamper-evident audit trail)."""
    from ..autonomy import accounts as A
    from ..models import AuditLog

    a = db.get(ServiceAccount, aid)
    if a is None:
        raise HTTPException(404)
    rows = db.scalars(select(AuditLog).where(AuditLog.target == f"credential:{A.scope_of(a)}").order_by(AuditLog.id.desc()).limit(200)).all()
    return [{"at": r.created_at, "actor": r.actor, "action": r.action, "details": r.details} for r in rows]
