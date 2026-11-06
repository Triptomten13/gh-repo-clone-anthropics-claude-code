"""DAEMON OBSERVABILITY CENTER — durable execution records (runs) and their ordered events.

Every task execution and every /api/ai/ask request opens a RUN; policy decisions, model attempts (with the routing
exclusions that explain the choice), retrievals (document/chunk references and classification — not the text),
tool invocations, approval requests, attempts, retries, escalation and the final output are appended as EVENTS.
Events are buffered per run in memory (sequence numbers assigned there) and written in their OWN transaction only at
points where the traced work holds no database write lock: after every attempt (the worker's session is closed), at
finish and when a replay is read. So a failing task that rolls back cannot erase its trace, and tracing never waits
on a lock held by the work it observes (measured: flushing from inside a task made SQLite writers wait for the 30 s
busy timeout — and then lose the events). A hard process crash can lose the current attempt's events.
A context variable carries the current run into nested calls (and is copied into the orchestrator's worker thread).

Replay = reconstruction of what was RECORDED, in order. It is not re-execution: a model's output appears in a replay
only where it was stored (task results, run outputs, answer text), never regenerated.
"""
from __future__ import annotations

import contextvars
import json
import threading
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

current_run: contextvars.ContextVar[int | None] = contextvars.ContextVar("current_run", default=None)
SECRET_HINTS = ("password", "secret", "token", "api_key", "apikey", "authorization", "credential", "cookie")
MAX_STR = 2000
MAX_BUFFERED = 5000  # per run; beyond this the oldest buffered events are dropped and the drop is recorded
_buf: dict[int, list[dict[str, Any]]] = {}
_seq: dict[int, int] = {}
_lock = threading.Lock()


def redact(value: Any, depth: int = 0) -> Any:
    if depth > 6:
        return "…"
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if any(h in str(k).lower() for h in SECRET_HINTS) else redact(v, depth + 1)) for k, v in list(value.items())[:200]}
    if isinstance(value, list | tuple):
        return [redact(v, depth + 1) for v in list(value)[:200]]
    if isinstance(value, str) and len(value) > MAX_STR:
        return value[:MAX_STR] + f"… [{len(value) - MAX_STR} chars not stored]"
    if isinstance(value, int | float | bool) or value is None:
        return value
    return redact(str(value), depth + 1) if not isinstance(value, str) else value


def _session():
    from ..db import SessionLocal

    return SessionLocal()


def start(kind: str, ref: str = "", *, workflow: str = "", agent_id: str = "", user_email: str = "", parent_id: int | None = None,
          input: Any = None) -> int:
    from ..governance.policy import active_rules, policy_version
    from ..models import Run

    s = _session()
    try:
        r = Run(kind=kind, ref=ref, workflow=workflow, agent_id=agent_id, user_email=user_email, parent_id=parent_id, status="running",
                input=redact(input) if input is not None else {}, policy_version=policy_version(active_rules(s)))
        s.add(r)
        s.commit()
        return r.id
    finally:
        s.close()


def event(type_: str, name: str = "", data: Any = None, *, run_id: int | None = None, duration_ms: int | None = None) -> None:
    rid = run_id or current_run.get()
    if not rid:
        return
    with _lock:
        _seq[rid] = _seq.get(rid, 0) + 1
        buf = _buf.setdefault(rid, [])
        buf.append({"run_id": rid, "seq": _seq[rid], "ts": datetime.now(UTC), "type": type_, "name": name[:160],
                    "data": redact(data) if data is not None else {}, "duration_ms": duration_ms})
        if len(buf) > MAX_BUFFERED:
            del buf[: len(buf) - MAX_BUFFERED]


def flush(run_id: int) -> None:
    from ..models import RunEvent

    with _lock:
        rows = _buf.pop(run_id, [])
    if not rows:
        return
    s = _session()
    try:
        s.add_all([RunEvent(**r) for r in rows])
        s.commit()
    except Exception:  # noqa: BLE001 — tracing must never break the work it observes
        s.rollback()
    finally:
        s.close()


def finish(run_id: int, status: str, *, output: Any = None, error: str | None = None, tokens_in: int = 0, tokens_out: int = 0,
           cost_usd: float = 0.0) -> None:
    from ..models import Run

    flush(run_id)
    with _lock:
        _seq.pop(run_id, None)
    s = _session()
    try:
        r = s.get(Run, run_id)
        if r is None:
            return
        r.status, r.finished_at = status, datetime.now(UTC)
        r.output = redact(output) if output is not None else {}
        r.error = (error or "")[:4000]
        r.tokens_in, r.tokens_out, r.cost_usd = tokens_in, tokens_out, round(cost_usd, 6)
        s.commit()
    finally:
        s.close()


def run_of_task(db, task_id: int | None) -> int | None:
    if not task_id:
        return None
    from ..models import Run

    return db.scalar(select(Run.id).where(Run.ref == f"task:{task_id}").order_by(Run.id.desc()).limit(1))


def replay(db, run_id: int) -> dict[str, Any]:
    """Everything recorded about one run, in order, plus linked records — a historical reconstruction."""
    from ..models import Approval, AuditLog, LLMCall, Run, RunEvent, ToolInvocation

    r = db.get(Run, run_id)
    if r is None:
        raise LookupError("run not found")
    flush(run_id)  # a running run shows what has happened so far
    cols = lambda o: {c.key: getattr(o, c.key) for c in o.__table__.columns}  # noqa: E731
    events = [cols(e) for e in db.scalars(select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq))]
    task_id = int(r.ref.split(":", 1)[1]) if r.ref.startswith("task:") else None
    calls = db.scalars(select(LLMCall).where((LLMCall.run_id == run_id) | ((LLMCall.task_id == task_id) if task_id else False)).order_by(LLMCall.id)).all()
    tools = db.scalars(select(ToolInvocation).where(ToolInvocation.run_id.in_([run_id] + ([task_id] if task_id else []))).order_by(ToolInvocation.id)).all()
    approvals = [cols(a) for a in db.scalars(select(Approval).where(Approval.id.in_(
        [e["data"].get("approval_id") for e in events if isinstance(e["data"], dict) and e["data"].get("approval_id")] or [-1])))]
    audit = db.scalars(select(AuditLog).where(AuditLog.target.in_([f"run:{run_id}"] + ([f"task:{task_id}"] if task_id else []))).order_by(AuditLog.id)).all()
    children = [cols(c) for c in db.scalars(select(Run).where(Run.parent_id == run_id).order_by(Run.id))]
    return {"run": cols(r), "events": events, "children": children,
            "model_calls": [{k: getattr(c, k) for k in ("id", "created_at", "provider", "model", "tier", "status", "input_tokens", "output_tokens",
                                                        "cost_usd", "latency_ms", "error", "purpose")} for c in calls],
            "tool_invocations": [cols(t) for t in tools], "approvals": approvals,
            "audit": [{"seq": a.seq, "actor": a.actor, "action": a.action, "target": a.target, "created_at": a.created_at} for a in audit],
            "replay_kind": "historical reconstruction of recorded events — not a re-execution; model text appears only where it was stored",
            "generated_at": datetime.now(UTC).isoformat()}


def dumps(o: Any) -> str:
    return json.dumps(o, default=str)
