"""Autonomous operating loop (spec section 17).

A lightweight, DB-backed scheduler: each job records its last run in
SystemState so restarts never double-run a job, and the orchestrator's dedupe
window prevents redundant research. For multi-node deployments, replace the
tick loop with Celery beat or a cron trigger calling POST /api/scheduler/tick.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, UTC

from ..agents.catalog import build_orchestrator
from ..db import SessionLocal
from ..governance import core as gov

log = logging.getLogger("rocky.scheduler")

JOBS: list[tuple[str, timedelta, list[tuple[str, dict]]]] = [
    ("daily", timedelta(days=1), [("intel.scan_market", {}), ("ceo.evaluate_pipeline", {"limit": 25})]),
    ("weekly", timedelta(days=7), [("ceo.weekly_review", {})]),
    ("monthly", timedelta(days=30), [("system.self_evaluate", {})]),
]


def tick(now: datetime | None = None) -> dict[str, list]:
    now = now or datetime.now(UTC)
    orch = build_orchestrator()
    ran: dict[str, list] = {}
    db = SessionLocal()
    try:
        if gov.kill_switch_engaged(db):
            return {"skipped": ["kill switch engaged"]}
        state = gov.get_state(db, "scheduler")
        for name, every, tasks in JOBS:
            last = state.get(name)
            if last and now - datetime.fromisoformat(last) < every:
                continue
            ran[name] = []
            for ttype, payload in tasks:
                try:
                    t = orch.submit(db, ttype, payload, requested_by="scheduler", priority=1)
                    ran[name].append({"task_id": t.id, "type": ttype})
                except Exception as e:  # noqa: BLE001
                    ran[name].append({"type": ttype, "error": str(e)})
            state[name] = now.isoformat()
        gov.set_state(db, "scheduler", state)
        db.commit()
    finally:
        db.close()
    if ran:
        orch.drain(max_tasks=200)
    return ran


async def loop(interval_s: int) -> None:
    while True:
        try:
            await asyncio.to_thread(tick)
        except Exception:  # noqa: BLE001
            log.exception("scheduler tick failed")
        await asyncio.sleep(interval_s)
