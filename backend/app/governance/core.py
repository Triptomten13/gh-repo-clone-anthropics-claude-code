"""Governance primitives: audit trail, event bus, kill switch, approvals."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, UTC
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Approval, ApprovalStatus, AuditLog, SystemState
from ..security.permissions import required_level


# ---------------------------------------------------------------- audit
def audit(db: Session, actor: str, action: str, target: str = "", **details: Any) -> AuditLog:
    entry = AuditLog(actor=actor, action=action, target=target, details=json.loads(json.dumps(details, default=str)))
    db.add(entry)
    db.flush()
    bus.publish({"type": "audit", "actor": actor, "action": action, "target": target})
    return entry


# ---------------------------------------------------------------- event bus (live UI feed)
class EventBus:
    """In-process pub/sub for WebSocket subscribers. Durable state lives in the DB;
    this bus only fans out live notifications. Swap for Redis pub/sub when running
    multiple API replicas (see docs/ARCHITECTURE.md)."""

    def __init__(self) -> None:
        self._subs: dict[asyncio.Queue, asyncio.AbstractEventLoop] = {}

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subs[q] = asyncio.get_running_loop()
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.pop(q, None)

    @staticmethod
    def _put(q: asyncio.Queue, event: dict[str, Any]) -> None:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass  # slow consumer: drop rather than block agents

    def publish(self, event: dict[str, Any]) -> None:
        """Thread-safe: agents publish from worker threads."""
        event = {**event, "ts": datetime.now(UTC).isoformat()}
        for q, loop in list(self._subs.items()):
            try:
                loop.call_soon_threadsafe(self._put, q, event)
            except RuntimeError:  # loop closed
                self._subs.pop(q, None)


bus = EventBus()


# ---------------------------------------------------------------- system state / kill switch
def get_state(db: Session, key: str, default: dict | None = None) -> dict:
    row = db.get(SystemState, key)
    return dict(row.value) if row else dict(default or {})


def set_state(db: Session, key: str, value: dict) -> None:
    row = db.get(SystemState, key)
    if row:
        row.value = value
    else:
        db.add(SystemState(key=key, value=value))
    db.flush()


def kill_switch_engaged(db: Session) -> bool:
    return bool(get_state(db, "kill_switch").get("engaged"))


def set_kill_switch(db: Session, engaged: bool, actor: str, reason: str = "") -> None:
    set_state(db, "kill_switch", {"engaged": engaged, "by": actor, "reason": reason,
                                  "at": datetime.now(UTC).isoformat()})
    audit(db, actor, "kill_switch.engage" if engaged else "kill_switch.release", "system", reason=reason)
    bus.publish({"type": "kill_switch", "engaged": engaged})


# ---------------------------------------------------------------- approvals
def request_approval(db: Session, action: str, title: str, requested_by: str, description: str = "",
                     payload: dict | None = None, amount_sek: float | None = None) -> Approval:
    # Re-use an identical pending request instead of spamming the approval queue.
    existing = db.scalars(select(Approval).where(Approval.action == action, Approval.title == title,
                                                 Approval.status == ApprovalStatus.pending.value)).first()
    if existing:
        return existing
    a = Approval(action=action, level=int(required_level(action)), title=title, description=description,
                 payload=payload or {}, amount_sek=amount_sek, requested_by=requested_by)
    db.add(a)
    db.flush()
    audit(db, requested_by, "approval.requested", f"approval:{a.id}", approval_action=action, title=title, amount_sek=amount_sek)
    bus.publish({"type": "approval", "id": a.id, "status": a.status, "title": title})
    return a


def decide_approval(db: Session, approval: Approval, approve: bool, actor: str, note: str = "") -> Approval:
    if approval.status != ApprovalStatus.pending.value:
        raise ValueError(f"approval already {approval.status}")
    approval.status = ApprovalStatus.approved.value if approve else ApprovalStatus.rejected.value
    approval.decided_by = actor
    approval.decision_note = note
    approval.decided_at = datetime.now(UTC)
    audit(db, actor, "approval.approved" if approve else "approval.rejected", f"approval:{approval.id}", note=note)
    bus.publish({"type": "approval", "id": approval.id, "status": approval.status})
    return approval


def is_approved(db: Session, approval_id: int | None, action: str) -> bool:
    if approval_id is None:
        return False
    a = db.get(Approval, approval_id)
    return bool(a and a.action == action and a.status == ApprovalStatus.approved.value)
