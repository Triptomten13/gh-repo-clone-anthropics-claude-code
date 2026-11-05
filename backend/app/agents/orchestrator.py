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
import hashlib
import json
import logging
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutTimeout
from datetime import datetime, timedelta, timezone
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
    return datetime.now(timezone.utc).date().isoformat()


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


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
        """Ensure an Agent row exists for each registered agent. Never overwrites a
        permission level changed by a human admin."""
        for a in self.agents.values():
            row = db.get(Agent, a.id)
            if row is None:
                db.add(Agent(id=a.id, name=a.name, division=a.division, description=a.description,
                             permission_level=a.level, model_tier=a.tier))
            else:
                row.name, row.division, row.description = a.name, a.division, a.description
        db.commit()

    # ------------------------------------------------------------ governance checks
    def check_token_budget(self, db: Session, row: Agent) -> None:
        if row.budget_day != _today():
            row.budget_day, row.tokens_today = _today(), 0
        if row.tokens_today >= row.daily_token_budget:
            raise Blocked(f"agent {row.id} exhausted its daily token budget ({row.daily_token_budget})")
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        spent = db.scalar(select(func.coalesce(func.sum(Task.cost_usd), 0.0)).where(Task.created_at >= start)) or 0.0
        if spent >= get_settings().daily_cost_limit_usd:
            raise Blocked(f"global daily AI cost limit reached (${spent:.2f})")

    def submit(self, db: Session, task_type: str, payload: dict[str, Any] | None = None, requested_by: str = "system",
               parent: Task | None = None, priority: int = 50, agent_id: str | None = None,
               force: bool = False) -> Task:
        s = get_settings()
        payload = payload or {}
        if task_type not in self.routes and agent_id is None:
            raise GovernanceError(f"no agent handles task type '{task_type}'")
        agent_id = agent_id or self.routes[task_type]
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
            since = datetime.now(timezone.utc) - timedelta(hours=s.dedupe_window_hours)
            dup = db.scalars(select(Task).where(Task.dedupe_key == key, Task.created_at >= since,
                                                Task.status.in_(ACTIVE + (TaskStatus.succeeded.value,)))
                             .order_by(Task.id.desc())).first()
            if dup:
                return dup
        t = Task(type=task_type, agent_id=agent_id, parent_id=parent.id if parent else None, depth=depth,
                 payload=payload, dedupe_key=key, priority=priority, requested_by=requested_by,
                 max_attempts=s.default_max_attempts, timeout_s=s.default_task_timeout_s)
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
            task.status, task.started_at = TaskStatus.running.value, datetime.now(timezone.utc)
            db.commit()
            gov.bus.publish({"type": "task", "id": task.id, "task_type": task.type, "agent": task.agent_id, "status": "running"})

            status, out, err, tokens, cost = TaskStatus.failed.value, None, None, 0, 0.0
            with ThreadPoolExecutor(max_workers=1) as pool:
                while task.attempts < task.max_attempts:
                    task.attempts += 1
                    db.commit()
                    fut = pool.submit(self._execute_once, task_id)
                    try:
                        status, out, err, t_used, c_used = fut.result(timeout=task.timeout_s)
                    except FutTimeout:
                        status, out, err, t_used, c_used = TaskStatus.failed.value, None, f"timeout after {task.timeout_s}s", 0, 0.0
                    tokens += t_used
                    cost += c_used
                    if status != TaskStatus.failed.value:
                        break
            db.expire_all()
            task = db.get(Task, task_id)
            row = db.get(Agent, task.agent_id)
            task.status, task.error = status, err
            task.finished_at = datetime.now(timezone.utc)
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
            db.commit()
            gov.bus.publish({"type": "task", "id": task.id, "task_type": task.type, "agent": task.agent_id,
                             "status": status, "summary": out.summary if out else err})
            return task
        finally:
            db.close()

    def next_queued(self, db: Session) -> Task | None:
        return db.scalars(select(Task).where(Task.status == TaskStatus.queued.value)
                          .order_by(Task.priority.asc(), Task.id.asc())).first()

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
