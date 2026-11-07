"""Central orchestrator: task registry, routing, governance limits, execution.

Guarantees (spec section 20):
* max recursion depth for delegated tasks
* duplicate-task detection within a time window (incremental research, no re-work)
* per-task timeout and retry limit; non-retryable "blocked" outcomes
* per-agent daily token budgets and a global daily cost limit
* suspended agents and the global kill switch stop all execution
* every outcome is written to the message bus + audit trail
"""
from __future__ import annotations

import asyncio
import contextvars
import hashlib
import time
import json
import logging
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutTimeout
from datetime import datetime, timedelta, UTC
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import SessionLocal
from ..governance import core as gov
from ..integrations.base import NotConfigured, NotImplementedPlatform
from ..models import Agent, AgentMessage, Task, TaskStatus
from .base import AgentContext, AgentOutput, BaseAgent, Blocked

log = logging.getLogger("rocky.orchestrator")
ACTIVE = (TaskStatus.queued.value, TaskStatus.running.value)


class GovernanceError(Exception):
    pass


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def dedupe_key(task_type: str, agent_id: str, payload: dict[str, Any]) -> str:
    raw = json.dumps({"t": task_type, "a": agent_id, "p": payload}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class Orchestrator:
    def __init__(self) -> None:
        self.agents: dict[str, BaseAgent] = {}
        self.routes: dict[str, str] = {}
        self._drain_lock = threading.Lock()

    # ------------------------------------------------------------ registry
    def register(self, agent: BaseAgent) -> None:
        self.agents[agent.id] = agent
        for t in agent.task_types:
            if t in self.routes and self.routes[t] != agent.id:
                raise ValueError(f"task type {t} already routed to {self.routes[t]}")
            self.routes[t] = agent.id

    def sync_agents(self, db: Session) -> None:
        """Ensure an Agent row exists for each registered agent (and seed personas). Never
        overwrites a permission level or persona changed by a human admin."""
        from ..flare.service import seed_personas
        for a in self.agents.values():
            if getattr(a, "custom", False):
                continue  # a custom agent's row is its source of truth
            row = db.get(Agent, a.id)
            if row is None:
                db.add(Agent(id=a.id, name=a.name, division=a.division, description=a.description,
                             permission_level=a.level, model_tier=a.tier))
            else:
                row.name, row.division, row.description = a.name, a.division, a.description
        db.flush()
        seed_personas(db)
        from ..personnel import registry as personnel

        personnel.seed(db)  # Bestiary, departments and the identities of agents that have none yet
        from ..personnel import runtime as custom_runtime

        custom_runtime.load(db, self)  # custom agents created with the Agent Creator (task type custom.<id>)
        db.commit()

    # ------------------------------------------------------------ governance checks
    def check_token_budget(self, db: Session, row: Agent) -> None:
        if row.budget_day != _today():
            row.budget_day, row.tokens_today = _today(), 0
        if row.tokens_today >= row.daily_token_budget:
            raise Blocked(f"agent {row.id} exhausted its daily token budget ({row.daily_token_budget})")
        from ..ai.tracing import spent_today

        spent = spent_today(db)  # every model call counts, inside or outside tasks
        if spent >= get_settings().daily_cost_limit_usd:
            raise Blocked(f"global daily AI cost limit reached (${spent:.2f})")

    def submit(self, db: Session, task_type: str, payload: dict[str, Any] | None = None, requested_by: str = "system",
               parent: Task | None = None, priority: int = 50, agent_id: str | None = None,
               force: bool = False, depends_on: list[int] | None = None) -> Task:
        s = get_settings()
        payload = payload or {}
        if task_type not in self.routes and agent_id is None:
            raise GovernanceError(f"no agent handles task type '{task_type}'")
        agent_id = agent_id or self.routes[task_type]
        if agent_id not in self.agents:
            raise GovernanceError(f"unknown agent '{agent_id}'")
        if gov.kill_switch_engaged(db):
            raise GovernanceError("kill switch engaged: no new tasks accepted")
        depth = (parent.depth + 1) if parent else 0
        if depth > s.max_task_depth:
            raise GovernanceError(f"max delegation depth {s.max_task_depth} exceeded")
        # Loop detection: an ancestor with the same type+payload means circular delegation.
        key = dedupe_key(task_type, agent_id, payload)
        anc = parent
        while anc is not None:
            if anc.dedupe_key == key:
                raise GovernanceError("circular delegation detected")
            anc = db.get(Task, anc.parent_id) if anc.parent_id else None
        if not force:
            since = datetime.now(UTC) - timedelta(hours=s.dedupe_window_hours)
            dup = db.scalars(select(Task).where(Task.dedupe_key == key, Task.created_at >= since,
                                                Task.status.in_(ACTIVE + (TaskStatus.succeeded.value,)))
                             .order_by(Task.id.desc())).first()
            if dup:
                return dup
        t = Task(type=task_type, agent_id=agent_id, parent_id=parent.id if parent else None, depth=depth,
                 payload=payload, dedupe_key=key, priority=priority, requested_by=requested_by,
                 depends_on=list(depends_on or []),
                 max_attempts=s.default_max_attempts,
                 timeout_s=max(s.default_task_timeout_s, s.deep_task_timeout_s) if getattr(self.agents.get(agent_id), "tier", "") == "deep"
                 else s.default_task_timeout_s)
        db.add(t)
        db.flush()
        gov.bus.publish({"type": "task", "id": t.id, "task_type": task_type, "agent": agent_id, "status": t.status})
        return t

    # ------------------------------------------------------------ execution
    def _execute_once(self, task_id: int) -> tuple[str, AgentOutput | None, str | None, int, float]:
        db = SessionLocal()
        try:
            task = db.get(Task, task_id)
            row = db.get(Agent, task.agent_id)
            agent = self.agents[task.agent_id]
            ctx = AgentContext(db, task, row, self)
            try:
                if gov.kill_switch_engaged(db):
                    raise Blocked("kill switch engaged")
                if row.status != "active":
                    raise Blocked(f"agent {row.id} is {row.status}")
                if task.type.startswith("persona."):
                    # Any agent that carries a persona can sit on panels, councils and discussions.
                    from .flare_agents import persona_handle

                    out = persona_handle(ctx, task, task.payload.get("persona_id"))
                else:
                    out = agent.handle(ctx, task)
                db.commit()  # persist agent side effects (incl. spawned tasks)
                return TaskStatus.succeeded.value, out, None, ctx.tokens, ctx.cost_usd
            except (Blocked, NotConfigured, NotImplementedPlatform) as e:
                db.rollback()
                return TaskStatus.blocked.value, None, str(e), ctx.tokens, ctx.cost_usd
            except Exception as e:  # noqa: BLE001 - recorded and retried
                db.rollback()
                log.exception("task %s failed", task_id)
                return TaskStatus.failed.value, None, f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}", ctx.tokens, ctx.cost_usd
        finally:
            db.close()

    def run_task(self, task_id: int) -> Task:
        """Execute a queued task with timeout + retries. Returns the final Task row."""
        db = SessionLocal()
        try:
            task = db.get(Task, task_id)
            if task is None or task.status not in ACTIVE:
                return task
            task.status, task.started_at = TaskStatus.running.value, datetime.now(UTC)
            db.commit()
            gov.bus.publish({"type": "task", "id": task.id, "task_type": task.type, "agent": task.agent_id, "status": "running"})
            from ..governance import observability as obs

            run_id = obs.start("task", f"task:{task.id}", workflow=task.type, agent_id=task.agent_id,
                               user_email=(task.requested_by or "").removeprefix("user:"),
                               parent_id=obs.run_of_task(db, task.parent_id), input={"payload": task.payload, "priority": task.priority,
                                                                                      "requested_by": task.requested_by, "max_attempts": task.max_attempts,
                                                                                      "timeout_s": task.timeout_s})
            token = obs.current_run.set(run_id)
            status, out, err, tokens, cost = TaskStatus.failed.value, None, None, 0, 0.0
            with ThreadPoolExecutor(max_workers=1) as pool:
                while task.attempts < task.max_attempts:
                    task.attempts += 1
                    db.commit()
                    if task.attempts > 1:
                        obs.event("retry", f"attempt {task.attempts}/{task.max_attempts}", {"previous_error": (err or "")[:500]})
                    t0 = time.monotonic()
                    fut = pool.submit(contextvars.copy_context().run, self._execute_once, task_id)  # the run follows the work
                    try:
                        status, out, err, t_used, c_used = fut.result(timeout=task.timeout_s)
                    except FutTimeout:
                        status, out, err, t_used, c_used = TaskStatus.failed.value, None, f"timeout after {task.timeout_s}s", 0, 0.0
                    obs.event("attempt", f"attempt {task.attempts}", {"status": status, "error": (err or "")[:500], "tokens": t_used, "cost_usd": c_used},
                              duration_ms=int((time.monotonic() - t0) * 1000))
                    obs.flush(run_id)  # the worker's session is closed here: no lock to wait for
                    tokens += t_used
                    cost += c_used
                    if status != TaskStatus.failed.value:
                        break
            db.expire_all()
            task = db.get(Task, task_id)
            row = db.get(Agent, task.agent_id)
            task.status, task.error = status, err
            task.finished_at = datetime.now(UTC)
            task.tokens_used, task.cost_usd = tokens, cost
            if row.budget_day != _today():
                row.budget_day, row.tokens_today = _today(), 0
            row.tokens_today += tokens
            row.tokens_total += tokens
            row.cost_total_usd += cost
            row.last_active_at = task.finished_at
            if status == TaskStatus.succeeded.value:
                row.tasks_succeeded += 1
                task.result = out.result
                db.add(AgentMessage(agent_id=row.id, task_id=task.id, kind="result", summary=out.summary,
                                    findings=out.findings, evidence=out.evidence, confidence=out.confidence,
                                    epistemic=out.epistemic, recommendations=out.recommendations,
                                    financial_impact_sek=out.financial_impact_sek, risks=out.risks,
                                    required_approvals=out.required_approvals))
            elif status == TaskStatus.blocked.value:
                row.tasks_blocked += 1
                db.add(AgentMessage(agent_id=row.id, task_id=task.id, kind="blocked", summary=err or "blocked",
                                    confidence=1.0, epistemic="verified"))
            else:
                row.tasks_failed += 1
                db.add(AgentMessage(agent_id=row.id, task_id=task.id, kind="error", summary=(err or "")[:500],
                                    confidence=1.0, epistemic="verified"))
            if status == TaskStatus.failed.value and task.attempts >= task.max_attempts:
                # retries exhausted: escalate to humans (audit + live alert), never fail silently
                gov.audit(db, "system", "task.escalated", f"task:{task.id}", agent=task.agent_id, attempts=task.attempts, error=(err or "")[:300])
                gov.bus.publish({"type": "escalation", "task": task.id, "agent": task.agent_id, "error": (err or "")[:300]})
                obs.event("escalation", "retries exhausted → operators notified", {"attempts": task.attempts, "error": (err or "")[:500]})
            db.commit()
            obs.event("output", status, {"summary": out.summary if out else None, "result": task.result if out else None, "error": (err or "")[:500]})
            obs.finish(run_id, status, output={"summary": out.summary if out else None, "result": task.result if out else None},
                       error=err, tokens_in=tokens, cost_usd=cost)
            obs.current_run.reset(token)
            gov.bus.publish({"type": "task", "id": task.id, "task_type": task.type, "agent": task.agent_id,
                             "status": status, "summary": out.summary if out else err})
            return task
        finally:
            db.close()

    def next_queued(self, db: Session) -> Task | None:
        """Highest-priority queued task whose dependencies have all finished (any terminal state).
        Dependents of failed/blocked tasks still run and must handle missing inputs explicitly."""
        queued = db.scalars(select(Task).where(Task.status == TaskStatus.queued.value)
                            .order_by(Task.priority.asc(), Task.id.asc())).all()
        for t in queued:
            deps = t.depends_on or []
            if not deps:
                return t
            open_deps = db.scalar(select(func.count(Task.id)).where(Task.id.in_(deps), Task.status.in_(ACTIVE)))
            if not open_deps:
                return t
        return None

    def recover_interrupted(self, db: Session) -> dict[str, int]:
        """After a restart, tasks left 'running' were interrupted mid-flight: requeue them if attempts remain, else fail them.
        Nothing is marked succeeded without a result."""
        requeued = failed = 0
        for t in db.scalars(select(Task).where(Task.status == TaskStatus.running.value)).all():
            if t.attempts < t.max_attempts:
                t.status, requeued = TaskStatus.queued.value, requeued + 1
            else:
                t.status, t.error, failed = TaskStatus.failed.value, "interrupted by restart (no attempts left)", failed + 1
                t.finished_at = datetime.now(UTC)
        if requeued or failed:
            gov.audit(db, "system", "orchestrator.recover", "tasks", requeued=requeued, failed=failed)
        db.commit()
        return {"requeued": requeued, "failed": failed}

    def drain(self, max_tasks: int = 100) -> list[int]:
        """Run queued tasks (including ones spawned along the way) until the queue is empty.
        Single worker per process: a concurrent call returns immediately."""
        if not self._drain_lock.acquire(blocking=False):
            return []
        try:
            return self._drain(max_tasks)
        finally:
            self._drain_lock.release()

    def _drain(self, max_tasks: int) -> list[int]:
        done: list[int] = []
        for _ in range(max_tasks):
            db = SessionLocal()
            try:
                t = self.next_queued(db)
                tid = t.id if t else None
            finally:
                db.close()
            if tid is None:
                break
            self.run_task(tid)
            done.append(tid)
        return done

    async def drain_async(self, max_tasks: int = 100) -> list[int]:
        return await asyncio.to_thread(self.drain, max_tasks)


orchestrator = Orchestrator()
