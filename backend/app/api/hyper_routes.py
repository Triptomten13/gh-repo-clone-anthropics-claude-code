"""DAEMON HYPERINTELLIGENCE API: orchestrated answering, research, monitoring, Control Center telemetry."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..governance import core as gov
from ..models import BenchmarkRun, Document, LLMCall, Monitor, MonitorEvent, ResearchRun, Task, User, WebResource
from ..security.auth import current_user, require_role

router = APIRouter(prefix="/api")
operator = require_role("admin", "operator")
admin = require_role("admin")


def _cols(o: Any) -> dict[str, Any]:
    return {c.key: getattr(o, c.key) for c in o.__table__.columns}


# ------------------------------------------------------------------ orchestrated answering
class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=20_000)
    research_depth: Literal["quick", "standard", "deep"] | None = None
    samples: int = Field(1, ge=1, le=5)
    strategy: Literal["deterministic", "archive", "research", "model_fast", "model_standard", "model_deep", "gsus"] | None = None
    sensitivity: Literal["normal", "private", "sensitive"] = "normal"


@router.post("/ai/ask")
def ai_ask(a: AskIn, db: Session = Depends(get_db), user: User = Depends(operator)):
    """Think before using a model: classify → cheapest reliable strategy → execute → answer with an execution trace."""
    from ..ai.router import LLMRefused, LLMUnavailable
    from ..daemon import intel
    from ..governance import budgets
    from ..governance import observability as obs

    run_id = obs.start("ask", "", workflow="ai.ask", user_email=user.email, input={"question": a.question, "strategy": a.strategy,
                                                                                   "sensitivity": a.sensitivity, "research_depth": a.research_depth})
    token = obs.current_run.set(run_id)
    try:
        out = intel.answer(db, user, a.question, research_depth=a.research_depth, samples=a.samples, force_strategy=a.strategy,
                           sensitivity=a.sensitivity)
        db.commit()  # release this request's write lock before the trace is written
        obs.event("output", out.get("plan", {}).get("strategy", ""), {"answer": out.get("answer"), "status": out.get("status"),
                                                                     "sources": len(out.get("sources") or []), "model_calls": out.get("model_calls")})
        obs.finish(run_id, out.get("status") or "succeeded", output={"answer": out.get("answer"), "plan": out.get("plan")},
                   cost_usd=out.get("cost_usd") or 0.0)
        out["run_id"] = run_id
        return out
    except budgets.BudgetExceeded as e:
        db.rollback()  # no write lock held while the trace is written
        obs.finish(run_id, "blocked", error=str(e))
        raise HTTPException(429, str(e)) from e
    except LLMRefused as e:
        db.rollback()  # no write lock held while the trace is written
        obs.finish(run_id, "failed", error=str(e))
        raise HTTPException(422, f"model declined: {e}") from e
    except LLMUnavailable as e:
        db.rollback()  # no write lock held while the trace is written
        obs.finish(run_id, "failed", error=str(e))
        raise HTTPException(503, {"error": str(e), "attempts": getattr(e, "attempts", []), "run_id": run_id}) from e
    finally:
        obs.current_run.reset(token)


class PlanIn(BaseModel):
    question: str = Field(min_length=2, max_length=20_000)


@router.post("/ai/plan")
def ai_plan(p: PlanIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    """Dry run: how would this be solved, and why — no model call, no network request."""
    from dataclasses import asdict

    from ..daemon import intel, library, state

    c = intel.classify(p.question)
    st = state.load(db)
    pl = intel.plan(c, offline=st["offline_mode"], has_local={s: library.resolve(db, s) is not None for s in ("eco", "chat", "deep")})
    return {"classification": asdict(c), "plan": asdict(pl)}


# ------------------------------------------------------------------ research
class ResearchIn(BaseModel):
    query: str = Field(min_length=3, max_length=2000)
    depth: Literal["quick", "standard", "deep"] = "quick"
    force_refresh: bool = False


@router.post("/research")
def research_run(r: ResearchIn, db: Session = Depends(get_db), user: User = Depends(operator)):
    from ..internet import research

    out = research.run(db, r.query, depth=r.depth, actor=user.email, force_refresh=r.force_refresh)
    gov.audit(db, user.email, "research.run", f"research:{out.get('run_id')}", depth=r.depth, cached=out.get("cached"))
    db.commit()
    return out


@router.get("/research")
def research_list(limit: int = Query(50, le=200), db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [{"id": r.id, "query": r.query, "depth": r.depth, "status": r.status, "answer_kind": r.answer_kind, "sources": len(r.sources or []),
             "created_at": r.created_at, "created_by": r.created_by, "stats": r.stats}
            for r in db.scalars(select(ResearchRun).order_by(ResearchRun.id.desc()).limit(limit))]


@router.get("/research/{rid}")
def research_get(rid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    from ..internet.research import _out

    r = db.get(ResearchRun, rid)
    if not r:
        raise HTTPException(404)
    return _out(r)


class PromoteIn(BaseModel):
    url: str = Field(min_length=8, max_length=1024)
    evidence_class: str = "unclassified"


@router.post("/research/promote")
def research_promote_url(p: PromoteIn, db: Session = Depends(get_db), user: User = Depends(operator)):
    w = db.scalars(select(WebResource).where(WebResource.url == p.url)).first()
    if not w:
        raise HTTPException(404, "source not in the research cache (it may have expired) — run the research again")
    return research_promote(w.id, p.evidence_class, db, user)


@router.post("/research/sources/{wid}/promote")
def research_promote(wid: int, evidence_class: str = "unclassified", db: Session = Depends(get_db), user: User = Depends(operator)):
    """A human decides a source is worth keeping: its excerpt enters the Archive with provenance (retrieval date, URL, licence)."""
    from ..knowledge import process
    from ..knowledge.extract import Extracted
    from ..models import EVIDENCE_CLASSES

    if evidence_class not in EVIDENCE_CLASSES:
        raise HTTPException(422, f"evidence_class must be one of {EVIDENCE_CLASSES}")
    w = db.get(WebResource, wid)
    if not w:
        raise HTTPException(404)
    if w.promoted_document_id:
        return {"document_id": w.promoted_document_id, "already": True}
    text = f"{w.title}\n\nSource: {w.url}\nRetrieved: {w.retrieved_at:%Y-%m-%d %H:%M} UTC\nLicence: {w.license_note}\n\n{w.excerpt}"
    doc = process.ingest(db, Extracted("txt", "text/plain", text), {"title": w.title[:255], "source": f"web:{w.host}", "source_url": w.url,
                                                                     "evidence_class": evidence_class,
                                                                     "description": f"excerpt promoted from {w.source} (reliability: {w.reliability})"},
                         owner_id=user.id)
    w.promoted_document_id = doc.id
    gov.audit(db, user.email, "research.promote", f"web:{w.id}", document=doc.id)
    db.commit()
    return {"document_id": doc.id}


# ------------------------------------------------------------------ monitoring
class MonitorIn(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    purpose: str = Field(min_length=3, max_length=500)
    query: str = Field(min_length=2, max_length=512)
    sources: list[Literal["wikipedia", "arxiv", "crossref", "github", "hn", "pypi", "osv", "nvd", "hf", "rss"]] = Field(["hn"], min_length=1, max_length=10)
    every_minutes: int = Field(1440, ge=60, le=60 * 24 * 30)
    max_requests: int = Field(4, ge=1, le=10)


class MonitorPatch(BaseModel):
    """Same bounds as creation — a PATCH must not lift a monitor's request budget or frequency past them."""
    enabled: bool | None = None
    every_minutes: int | None = Field(None, ge=60, le=60 * 24 * 30)
    max_requests: int | None = Field(None, ge=1, le=10)
    purpose: str | None = Field(None, min_length=3, max_length=500)


@router.get("/monitors")
def monitors(db: Session = Depends(get_db), _: User = Depends(current_user)):
    from ..internet.monitor import TEMPLATES

    return {"monitors": [_cols(m) | {"seen": len(m.seen or [])} for m in db.scalars(select(Monitor).order_by(Monitor.id))], "templates": TEMPLATES}


@router.post("/monitors")
def monitor_add(m: MonitorIn, db: Session = Depends(get_db), user: User = Depends(operator)):
    row = Monitor(**(m.model_dump() | {"sources": list(dict.fromkeys(m.sources))}), created_by=user.email)
    db.add(row)
    db.flush()
    gov.audit(db, user.email, "monitor.create", f"monitor:{row.id}", query=m.query, every_minutes=m.every_minutes)
    db.commit()
    return _cols(row)


@router.patch("/monitors/{mid}")
def monitor_patch(mid: int, p: MonitorPatch, db: Session = Depends(get_db), user: User = Depends(operator)):
    m = db.get(Monitor, mid)
    if not m:
        raise HTTPException(404)
    ch = p.model_dump(exclude_none=True)
    for k, v in ch.items():
        setattr(m, k, v)
    gov.audit(db, user.email, "monitor.update", f"monitor:{mid}", **{k: v for k, v in ch.items() if k != "purpose"})
    db.commit()
    return _cols(m)


@router.delete("/monitors/{mid}")
def monitor_delete(mid: int, db: Session = Depends(get_db), user: User = Depends(operator)):
    m = db.get(Monitor, mid)
    if not m:
        raise HTTPException(404)
    db.query(MonitorEvent).filter(MonitorEvent.monitor_id == mid).delete()
    db.delete(m)
    gov.audit(db, user.email, "monitor.delete", f"monitor:{mid}")
    db.commit()
    return {"deleted": mid}


@router.post("/monitors/{mid}/run")
def monitor_run(mid: int, db: Session = Depends(get_db), user: User = Depends(operator)):
    from ..internet import monitor

    m = db.get(Monitor, mid)
    if not m:
        raise HTTPException(404)
    out = monitor.run_one(db, m)
    gov.audit(db, user.email, "monitor.run", f"monitor:{mid}", new=out["new"], errors=len(out["errors"]))
    db.commit()
    return out


@router.get("/monitors/events")
def monitor_events(limit: int = Query(50, le=200), db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [_cols(e) for e in db.scalars(select(MonitorEvent).order_by(MonitorEvent.id.desc()).limit(limit))]


@router.post("/monitors/events/{eid}/ack")
def monitor_ack(eid: int, db: Session = Depends(get_db), user: User = Depends(operator)):
    e = db.get(MonitorEvent, eid)
    if not e:
        raise HTTPException(404)
    e.acknowledged = True
    gov.audit(db, user.email, "monitor.ack", f"monitor_event:{eid}")
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ Control Center
@router.get("/control/overview")
def control_overview(db: Session = Depends(get_db), _: User = Depends(current_user)):
    """Real measurements only. Fields that cannot be measured on this host are null, not invented."""
    from ..daemon import cache, costs, library, residency, semantic_cache, telemetry
    from ..daemon import state as dstate
    from ..daemon.runtime import get_local
    from ..internet.http import paused_hosts
    from ..knowledge.index import enabled as index_enabled
    from ..knowledge.index import stats as _ix_stats

    def index_stats() -> dict[str, Any]:
        return dict(_ix_stats)

    now = datetime.now(UTC)
    day = now - timedelta(days=1)
    s = telemetry.latest() or telemetry.sample()
    tasks = dict(db.execute(select(Task.status, func.count(Task.id)).where(Task.created_at >= day).group_by(Task.status)).all())
    queue = dict(db.execute(select(Task.status, func.count(Task.id)).where(Task.status.in_(("queued", "running"))).group_by(Task.status)).all())
    calls = db.execute(select(func.count(LLMCall.id), func.coalesce(func.sum(LLMCall.input_tokens + LLMCall.output_tokens), 0),
                              func.coalesce(func.avg(LLMCall.latency_ms), 0), func.coalesce(func.sum(LLMCall.energy_wh), 0.0))
                       .where(LLMCall.created_at >= day, LLMCall.status == "ok")).one()
    cache_hits = db.scalar(select(func.count(LLMCall.id)).where(LLMCall.created_at >= day, LLMCall.cache_hit.is_(True))) or 0
    research_24h = db.execute(select(func.count(ResearchRun.id)).where(ResearchRun.created_at >= day)).scalar() or 0
    succeeded = tasks.get("succeeded", 0)
    finished = succeeded + tasks.get("failed", 0) + tasks.get("blocked", 0)
    econ = cache.get("cost-dashboard", 30, maxsize=8).get_or_set(("1d",), lambda: costs.dashboard(db, 1))
    quality = {f"{b.provider}:{b.model}": {"accuracy": b.summary.get("accuracy"), "avg_latency_ms": b.summary.get("avg_latency_ms")}
               for b in db.scalars(select(BenchmarkRun).where(BenchmarkRun.status == "completed").order_by(BenchmarkRun.id))}
    hosts = telemetry.hosts()
    net_bytes = sum(h["bytes_in"] for h in hosts)
    p = get_local()
    slots = {sl: (m.key if (m := library.resolve(db, sl)) else None) for sl in ("chat", "eco", "deep", "embedding")}
    proc = s.get("process") or {}
    return {
        "measured_at": now.isoformat(),
        "intelligence": {"active_models": slots, "resident_models": p.residency(), "model_loads": p.load_count, "model_unloads": p.unload_count,
                         "load_ms_total": p.load_ms_total, "resource_mode": {"configured": residency.configured_mode(), "effective": residency.effective_mode()},
                         "queue": queue, "tasks_24h": tasks, "task_success_rate_24h": round(succeeded / finished, 3) if finished else None,
                         "model_quality": quality, "research_runs_24h": research_24h,
                         "monitors": db.scalar(select(func.count(Monitor.id)).where(Monitor.enabled.is_(True))) or 0,
                         "unacknowledged_alerts": db.scalar(select(func.count(MonitorEvent.id)).where(MonitorEvent.acknowledged.is_(False))) or 0},
        "hardware": {k: s.get(k) for k in ("cpu_pct", "ram_total_bytes", "ram_available_bytes", "page_cache_bytes", "swap_used_bytes", "disk_total_bytes",
                                            "disk_free_bytes", "disk_read_bps", "disk_write_bps", "cpu_temp_c", "gpus")}
        | {"process_rss_bytes": proc.get("rss_bytes"), "process_cpu_s": proc.get("cpu_s"), "threads": proc.get("threads"),
           "vram": [{"name": g["name"], "total_mb": g["vram_total_mb"], "free_mb": g["vram_free_mb"]} for g in s.get("gpus") or []] or None},
        "network": {"rx_bps": s.get("net_rx_bps"), "tx_bps": s.get("net_tx_bps"), "hosts": hosts, "paused_hosts": paused_hosts(),
                    "external_bytes_in_since_start": net_bytes, "offline_mode": dstate.load(db)["offline_mode"]},
        "economics": {"today": econ["totals"], "savings": econ["savings"], "forecast": econ["forecast"], "limits": econ["limits"]},
        "efficiency": {"model_calls_24h": calls[0], "avg_tokens_per_call": round(calls[1] / calls[0]) if calls[0] else None,
                       "avg_model_latency_ms": round(float(calls[2])) if calls[0] else None, "energy_wh_24h_estimate": round(float(calls[3]), 3),
                       "response_cache_hits_24h": cache_hits, "semantic_cache": semantic_cache.stats, "l1_caches": cache.stats(),
                       "api_latency": telemetry.summary_latency(), "energy_wh_per_successful_task_estimate":
                           round(float(calls[3]) / succeeded, 4) if succeeded else None},
        "events": telemetry.events(20),
        "archive_documents": db.scalar(select(func.count(Document.id))) or 0,
        "archive_index": {**index_stats(), "enabled": index_enabled()},
    }


@router.get("/control/history")
def control_history(points: int = Query(120, le=720), _: User = Depends(current_user)):
    from ..daemon import telemetry

    return {"samples": telemetry.history(points), "every_s": telemetry.SAMPLE_EVERY_S}


@router.get("/control/routes")
def control_routes(_: User = Depends(current_user)):
    from ..daemon import telemetry

    return {"routes": telemetry.routes(40), "note": "since process start; latency p50/p95 over the last 200 requests per route"}


@router.post("/control/retention")
def control_retention(db: Session = Depends(get_db), user: User = Depends(admin)):
    from ..daemon import retention

    out = retention.run(db)
    gov.audit(db, user.email, "retention.run", "daemon", **out["deleted"])
    db.commit()
    return out


@router.post("/control/unload/{cache_key:path}")
def control_unload(cache_key: str, db: Session = Depends(get_db), user: User = Depends(admin)):
    from ..daemon.runtime import get_local

    ok = get_local().unload(cache_key, reason=f"manual by {user.email}")
    gov.audit(db, user.email, "model.unload", f"model:{cache_key[:200]}", unloaded=ok)
    db.commit()
    return {"unloaded": ok}


# ------------------------------------------------------------------ agent efficiency (delegation cost / benefit)
@router.get("/agents/efficiency")
def agents_efficiency(days: int = Query(7, ge=1, le=90), db: Session = Depends(get_db), _: User = Depends(current_user)):
    """Per agent: outcomes, time, tokens, cost per success, and what delegating to sub-tasks actually bought."""
    since = datetime.now(UTC) - timedelta(days=days)
    rows = db.execute(select(Task.id, Task.agent_id, Task.status, Task.parent_id, Task.started_at, Task.finished_at, Task.tokens_used, Task.cost_usd)
                      .where(Task.created_at >= since)).all()
    by_id = {r.id: r for r in rows}
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        a = out.setdefault(r.agent_id, {"agent": r.agent_id, "tasks": 0, "succeeded": 0, "failed": 0, "blocked": 0, "tokens": 0, "cost_usd": 0.0,
                                        "durations": [], "spawned": 0, "spawned_succeeded": 0})
        a["tasks"] += 1
        a[r.status] = a.get(r.status, 0) + 1
        a["tokens"] += r.tokens_used or 0
        a["cost_usd"] += r.cost_usd or 0.0
        if r.started_at and r.finished_at:
            a["durations"].append((r.finished_at - r.started_at).total_seconds())
        parent = by_id.get(r.parent_id) if r.parent_id else None
        if parent is not None:
            pa = out.setdefault(parent.agent_id, {"agent": parent.agent_id, "tasks": 0, "succeeded": 0, "failed": 0, "blocked": 0, "tokens": 0,
                                                  "cost_usd": 0.0, "durations": [], "spawned": 0, "spawned_succeeded": 0})
            pa["spawned"] += 1
            pa["spawned_succeeded"] += 1 if r.status == "succeeded" else 0
    res = []
    for a in out.values():
        d = a.pop("durations")
        a["avg_seconds"] = round(sum(d) / len(d), 2) if d else None
        # Intelligence Efficiency Score: verified successes per resource unit (1 unit = 10k tokens, $0.01 or 1 minute).
        # No successes → 0, however cheap: a cheap wrong answer is not efficiency.
        units = a["tokens"] / 10_000 + a["cost_usd"] / 0.01 + sum(d) / 60
        a["ies"] = round(a["succeeded"] / (1 + units), 3)
        a["ies_components"] = {"verified_successes": a["succeeded"], "tokens": a["tokens"], "cost_usd": round(a["cost_usd"], 6),
                               "execution_minutes": round(sum(d) / 60, 2), "resource_units": round(units, 3)}
        a["success_rate"] = round(a["succeeded"] / a["tasks"], 3) if a["tasks"] else None
        a["cost_per_success_usd"] = round(a["cost_usd"] / a["succeeded"], 6) if a["succeeded"] else None
        a["delegation"] = (None if not a["spawned"] else {"subtasks": a["spawned"], "subtask_success_rate": round(a["spawned_succeeded"] / a["spawned"], 3),
                                                          "subtasks_per_task": round(a["spawned"] / max(a["tasks"], 1), 2)})
        a["cost_usd"] = round(a["cost_usd"], 6)
        res.append(a)
    return {"days": days, "agents": sorted(res, key=lambda x: (-x["tasks"], x["agent"])),
            "note": "delegation is worth it when sub-tasks succeed and add information; many low-success sub-tasks are wasted compute",
            "ies_definition": "IES = verified successes / (1 + resource units); 1 unit = 10 000 tokens, $0.01 model cost or 1 minute of "
                              "execution. A heuristic composite — read it with its components. RAM/VRAM/energy are measured system-wide "
                              "(Control Center), not yet attributed per task."}
