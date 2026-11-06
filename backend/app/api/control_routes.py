"""DAEMON CONTROL PLANE API — audit & provenance, identity (roles/permissions); further sections are added per phase.

Every endpoint checks a PERMISSION (security/rbac.py), not just a role, and every state change is audited."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..governance import audit_chain
from ..governance import core as gov
from ..models import User
from ..security.rbac import PERMISSIONS, ROLES, require_permission

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


@router.post("/audit/prune")
def audit_prune(p: PruneIn, db: Session = Depends(get_db), user: User = Depends(require_permission("audit.retention"))):
    try:
        out = audit_chain.prune(db, p.before, user.email)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    db.commit()
    return out


# ------------------------------------------------------------------ identity & access
@router.get("/rbac/roles")
def rbac_roles(_: User = Depends(require_permission("policy.read"))):
    return {"permissions": PERMISSIONS, "roles": {r: sorted(p) for r, p in ROLES.items()},
            "note": "roles never inherit implicitly; builders cannot approve, approvers cannot change policy, auditors change nothing"}
