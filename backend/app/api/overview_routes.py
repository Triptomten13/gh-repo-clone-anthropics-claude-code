"""ONE SYSTEM — the views that connect the modules (docs/COMPLETION_AUDIT.md).

* `GET /api/attention` — what needs attention across the organisation, and whether the system is operational. Every
  item is computed from stored records at request time and links to where it is handled; nothing is estimated.
* `GET /api/search?q=` — one search over agents, tasks, runs, approvals, documents, products, experiments, research,
  creative tournaments, models and audit records. Each kind applies the SAME permission as its own list endpoint
  (documents through the Knowledge Vault's read check), so search never reveals what the caller could not open.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Agent, Approval, AuditLog, Experiment, LLMCall, Product, Task, User
from ..security.auth import current_user
from ..security.rbac import has

router = APIRouter(prefix="/api", tags=["overview"])

APPLY_FROM_APPROVALS = {"policy.write", "audit.prune", "tools.grant", "knowledge.declassify", "budget.change", "deploy.loosen_egress", "gates.change"}


def _aware(d: datetime | None) -> datetime | None:
    return d.replace(tzinfo=UTC) if d is not None and d.tzinfo is None else d


@router.get("/attention")
def attention(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict[str, Any]:
    from ..ai.llm import get_provider
    from ..config import get_settings
    from ..daemon import state as dstate
    from ..governance import core as gov

    now = datetime.now(UTC)
    day = now - timedelta(hours=24)
    me = f"user:{user.email}"
    items: list[dict[str, Any]] = []

    def add(severity: str, title: str, detail: str, href: str, count: int | None = None) -> None:
        items.append({"severity": severity, "title": title, "detail": detail, "href": href, "count": count})

    # ---- system state
    kill = gov.get_state(db, "kill_switch") or {}
    if kill.get("engaged"):
        add("critical", "Emergency stop is engaged", kill.get("reason") or "no agent work runs until it is released", "/agents")
    st = dstate.load(db)
    s = get_settings()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    spent = float(db.scalar(select(func.coalesce(func.sum(Task.cost_usd), 0.0)).where(Task.created_at >= start)) or 0)
    if s.daily_cost_limit_usd and spent >= 0.8 * s.daily_cost_limit_usd:
        add("warning", "AI spend is near today's limit", f"${spent:.2f} of ${s.daily_cost_limit_usd:g}", "/daemon")

    # ---- approvals: waiting for this person, and approved changes this person can now apply
    pending = [a for a in db.scalars(select(Approval).where(Approval.status == "pending").order_by(Approval.id.desc()).limit(200))
               if a.revoked_at is None and not (a.expires_at and _aware(a.expires_at) < now)]
    if has(user, "approval.decide"):
        mine = [a for a in pending if a.requested_by != me and (not a.delegated_to or a.delegated_to == user.email)]
        if mine:
            add("action", f"{len(mine)} approval{'s' if len(mine) != 1 else ''} waiting for your decision",
                "; ".join(f"#{a.id} {a.title}" for a in mine[:3]), f"/approvals?id={mine[0].id}" if len(mine) == 1 else "/approvals", len(mine))
    own = [a for a in pending if a.requested_by == me]
    if own:
        add("info", f"{len(own)} of your requests wait for someone else", "; ".join(f"#{a.id} {a.title}" for a in own[:3]), "/approvals", len(own))
    ready = [a for a in db.scalars(select(Approval).where(Approval.status == "approved", Approval.consumed_at.is_(None), Approval.revoked_at.is_(None),
                                                          Approval.requested_by == me).order_by(Approval.id.desc()).limit(50))
             if a.action in APPLY_FROM_APPROVALS and not (a.expires_at and _aware(a.expires_at) < now)]
    if ready:
        add("action", f"{len(ready)} approved change{'s' if len(ready) != 1 else ''} ready to apply", "; ".join(f"#{a.id} {a.title}" for a in ready[:3]),
            f"/approvals?id={ready[0].id}", len(ready))

    # ---- work that failed or is stuck
    bad = db.scalars(select(Task).where(Task.status.in_(("failed", "blocked")), Task.created_at >= day).order_by(Task.id.desc()).limit(200)).all()
    if bad:
        add("warning", f"{len(bad)} agent task{'s' if len(bad) != 1 else ''} failed or blocked in 24 h",
            "; ".join(f"#{t.id} {t.type} ({t.status}{': ' + t.error[:60] if t.error else ''})" for t in bad[:3]), f"/agents?task={bad[0].id}", len(bad))
    if has(user, "runs.read"):
        from ..models import Run

        runs_failed = db.scalars(select(Run).where(Run.status == "failed", Run.started_at >= day).order_by(Run.id.desc()).limit(100)).all()
        if runs_failed:
            add("warning", f"{len(runs_failed)} traced run{'s' if len(runs_failed) != 1 else ''} failed in 24 h",
                "; ".join(f"#{r.id} {r.workflow or r.kind}" for r in runs_failed[:3]), f"/governance#runs/{runs_failed[0].id}", len(runs_failed))
        from ..models import CreativeTournament

        review = db.scalar(select(func.count(CreativeTournament.id)).where(CreativeTournament.status == "stopped",
                                                                          CreativeTournament.created_at >= now - timedelta(days=7),
                                                                          CreativeTournament.created_by == user.email)) or 0
        if review:
            add("info", f"{review} creative result{'s' if review != 1 else ''} below target — human review suggested", "", "/creative", review)

    # ---- providers
    try:
        runtimes = get_provider().health() if hasattr(get_provider(), "health") else []
    except Exception:  # noqa: BLE001 — a failing health probe is itself a finding
        runtimes = []
    providers = [{"provider": r.get("provider"), "locality": r.get("locality"), "configured": bool(r.get("configured")), "state": r.get("state"),
                  "last_error": (r.get("last_error") or "")[:160] or None} for r in runtimes if isinstance(r, dict)]
    for p in providers:
        if p["configured"] and p["state"] == "open":
            add("warning", f"Provider {p['provider']} is failing (circuit open)", p["last_error"] or "", "/creative#providers")
    if not any(p["configured"] for p in providers):
        add("warning", "No AI provider is available", "install a local model or add a provider key", "/daemon")

    # ---- research monitors: changes in the last 24 h
    from ..models import MonitorEvent

    changes = db.scalar(select(func.count(MonitorEvent.id)).where(MonitorEvent.acknowledged.is_(False), MonitorEvent.created_at >= now - timedelta(days=7))) or 0
    if changes:
        add("info", f"{changes} monitored change{'s' if changes != 1 else ''} not yet reviewed", "research monitors, last 7 days", "/research", changes)

    # ---- security signals (auditors and admins)
    if has(user, "audit.read"):
        denied = db.scalar(select(func.count(AuditLog.id)).where(AuditLog.created_at >= day, or_(AuditLog.action.like("%denied%"),
                                                                                                  AuditLog.action.like("%blocked%")))) or 0
        if denied:
            add("info", f"{denied} refused action{'s' if denied != 1 else ''} in 24 h", "policy or tool-gateway refusals in the audit trail", "/governance#audit", denied)

    rank = {"critical": 0, "action": 1, "warning": 2, "info": 3}
    items.sort(key=lambda i: rank[i["severity"]])
    used = db.execute(select(LLMCall.provider, LLMCall.model, func.count(LLMCall.id)).where(LLMCall.created_at >= start, LLMCall.status == "ok")
                      .group_by(LLMCall.provider, LLMCall.model).order_by(func.count(LLMCall.id).desc()).limit(6)).all()
    active_since = now - timedelta(minutes=15)
    agents = db.scalars(select(Agent)).all()
    return {
        "generated_at": now.isoformat(),
        "attention": items,
        "status": {
            "kill_switch": bool(kill.get("engaged")),
            "offline_mode": bool(st.get("offline_mode")),
            "agents": len(agents),
            "agents_active": sum(1 for a in agents if a.last_active_at and _aware(a.last_active_at) >= active_since),
            "agents_suspended": sum(1 for a in agents if a.status != "active"),
            "tasks_running": db.scalar(select(func.count(Task.id)).where(Task.status == "running")) or 0,
            "tasks_queued": db.scalar(select(func.count(Task.id)).where(Task.status == "queued")) or 0,
            "tasks_done_24h": db.scalar(select(func.count(Task.id)).where(Task.status == "succeeded", Task.created_at >= day)) or 0,
            "approvals_pending": len(pending),
            "cost_today_usd": round(spent, 4),
            "daily_cost_limit_usd": s.daily_cost_limit_usd,
            "models_today": [{"provider": p, "model": m, "calls": n} for p, m, n in used],
            "providers": providers,
        },
    }


@router.get("/search")
def search(q: str = Query(min_length=2, max_length=200), limit: int = Query(5, ge=1, le=20), db: Session = Depends(get_db),
           user: User = Depends(current_user)) -> dict[str, Any]:
    term = f"%{q.strip().lower()}%"
    like = lambda col: func.lower(col).like(term)  # noqa: E731 — portable (SQLite + PostgreSQL), no JSON equality
    out: list[dict[str, Any]] = []

    def put(kind: str, rows: Any, title: Any, sub: Any, href: Any) -> None:
        for r in rows:
            out.append({"kind": kind, "id": r.id, "title": str(title(r))[:140], "sub": str(sub(r) or "")[:160], "href": href(r)})

    digits = q.strip().lstrip("#")
    num = int(digits) if digits.isdigit() else None
    put("agent", db.scalars(select(Agent).where(or_(like(Agent.name), like(Agent.id), like(Agent.division), like(Agent.description))).limit(limit)),
        lambda a: a.name, lambda a: f"{a.division} · {a.status}", lambda a: f"/agents?agent={a.id}")
    put("task", db.scalars(select(Task).where(or_(like(Task.type), like(Task.agent_id), Task.id == num if num else False)).order_by(Task.id.desc()).limit(limit)),
        lambda t: f"Task #{t.id} · {t.type}", lambda t: f"{t.agent_id} · {t.status}", lambda t: f"/agents?task={t.id}")
    put("approval", db.scalars(select(Approval).where(or_(like(Approval.title), like(Approval.action), Approval.id == num if num else False))
                               .order_by(Approval.id.desc()).limit(limit)),
        lambda a: f"Approval #{a.id} · {a.title}", lambda a: f"{a.action} · {a.status}", lambda a: f"/approvals?id={a.id}")
    if has(user, "runs.read"):
        from ..models import CreativeTournament, Run
        from .creative_routes import _visible

        put("run", db.scalars(select(Run).where(or_(like(Run.workflow), like(Run.kind), like(Run.ref), like(Run.agent_id), Run.id == num if num else False))
                              .order_by(Run.id.desc()).limit(limit)),
            lambda r: f"Run #{r.id} · {r.workflow or r.kind}", lambda r: f"{r.agent_id or r.user_email or ''} · {r.status}", lambda r: f"/governance#runs/{r.id}")
        ts = [t for t in db.scalars(select(CreativeTournament).where(like(CreativeTournament.brief)).order_by(CreativeTournament.id.desc()).limit(limit * 3))
              if _visible(t, user)][:limit]
        put("tournament", ts, lambda t: f"Tournament #{t.id} · {t.brief[:80]}", lambda t: f"{t.category} · {t.status}", lambda t: f"/creative#t-{t.id}")
    from ..knowledge.vault import readable_ids
    from ..models import Document

    docs = db.scalars(select(Document).where(or_(like(Document.title), like(Document.description), like(Document.author))).order_by(Document.id.desc()).limit(limit * 4)).all()
    ok = readable_ids(db, user, [d.id for d in docs]) if docs else set()
    put("document", [d for d in docs if d.id in ok][:limit], lambda d: d.title, lambda d: f"{d.doc_type} · {d.evidence_class}", lambda d: f"/knowledge#doc-{d.id}")
    put("product", db.scalars(select(Product).where(or_(like(Product.name), like(Product.category))).order_by(Product.id.desc()).limit(limit)),
        lambda p: p.name, lambda p: p.category, lambda p: f"/lab/{p.id}")
    put("experiment", db.scalars(select(Experiment).where(like(Experiment.name)).order_by(Experiment.id.desc()).limit(limit)),
        lambda e: e.name, lambda e: e.status, lambda e: "/experiments")
    from ..models import LocalModel, ResearchRun

    put("research", db.scalars(select(ResearchRun).where(like(ResearchRun.query)).order_by(ResearchRun.id.desc()).limit(limit)),
        lambda r: r.query, lambda r: f"{r.depth} · {r.status}", lambda r: "/research")
    put("model", db.scalars(select(LocalModel).where(or_(like(LocalModel.display_name), like(LocalModel.key), like(LocalModel.family))).limit(limit)),
        lambda m: m.display_name, lambda m: f"local · {m.status}", lambda m: "/creative#models")
    if has(user, "audit.read"):
        put("audit", db.scalars(select(AuditLog).where(or_(like(AuditLog.action), like(AuditLog.actor), like(AuditLog.target))).order_by(AuditLog.id.desc()).limit(limit)),
            lambda a: f"{a.action} · {a.target}", lambda a: a.actor, lambda a: "/governance#audit")
    return {"q": q, "results": out}
