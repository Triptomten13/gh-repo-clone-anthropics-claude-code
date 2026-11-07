"""The shared personnel register: seeding, cards, profiles, hierarchy and search.

One register for every agent, whatever its race. Departments are functional. Nothing here grants a permission: the
profile *reports* `permission_level`, Tool Gateway grants and budgets — it never derives them from race, rank, title,
personality or relationships.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models import (Agent, AgentRelationship, AgentVersion, Department, LLMCall, Species, Specialization, Task, ToolGrant)
from ..security import permissions
from . import bestiary_data as B
from . import personnel_data as P

OBSERVED_WINDOW = timedelta(days=7)
ACTIVE_TASK = ("queued", "running", "waiting_approval")


def _now() -> datetime:
    return datetime.now(UTC)


def excerpt(text: str, limit: int = 320) -> str:
    """Whole sentences up to `limit` characters; never cut mid-word."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("; "))
    return (cut[:end + 1] if end > limit // 3 else cut[:cut.rfind(" ")].rstrip(",;:") + " …").strip()


def _aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=UTC) if dt is not None and dt.tzinfo is None else dt


# ------------------------------------------------------------------------------------------------- seeding
def seed(db: Session) -> dict[str, int]:
    """Insert missing Bestiary entries, specializations and departments; give agents that have no identity yet their
    seed identity. Idempotent; never overwrites anything a person has edited (only empty identities are filled)."""
    n = {"species": 0, "specializations": 0, "departments": 0, "identities": 0, "relationships": 0}
    have = set(db.scalars(select(Species.key)))
    for s in B.SPECIES:
        if s["key"] not in have:
            db.add(Species(**s, user_created=False, created_by="system", updated_at=_now()))
            n["species"] += 1
    have = set(db.scalars(select(Specialization.key)))
    for s in P.SPECIALIZATIONS:
        if s["key"] not in have:
            db.add(Specialization(**s, user_created=False))
            n["specializations"] += 1
    have = set(db.scalars(select(Department.key)))
    leads = {d: aid for aid, ident in P.IDENTITIES.items() for d in [ident[5]] if ident[4] == "Department Lead"}
    for d in P.DEPARTMENTS:
        if d["key"] not in have:
            db.add(Department(**d, manager_id=leads.get(d["key"])))
            n["departments"] += 1
    db.flush()
    div_dept = {div: d["key"] for d in P.DEPARTMENTS for div in d["divisions"]}
    for a in db.scalars(select(Agent).where(Agent.persona_name == "")):
        ident = P.IDENTITIES.get(a.id)
        if ident:
            (a.persona_name, a.species_key, a.specializations, a.title, a.rank, a.department_key, a.supervisor_id,
             a.traits, a.communication_style, a.purpose) = (ident[0], ident[1], list(ident[2]), ident[3], ident[4], ident[5],
                                                             ident[6], list(ident[7]), list(ident[8]), ident[9])
            a.languages = ["English", "Swedish"]
            a.mission = {"primary": [a.description] if a.description else [], "not_to_do": list(_DEFAULT_LIMITS)}
        else:  # an agent this release has no identity for: honest defaults, no invented race
            a.persona_name, a.title = a.name, a.name
            a.department_key = div_dept.get(a.division, "")
            a.supervisor_id = None if a.id == "gsus" else "gsus"
            a.purpose = a.description
        a.created_at = a.created_at or _now()
        a.updated_at = _now()
        n["identities"] += 1
    # skills for code agents that have none and were never edited: their specializations' competencies, ASSIGNED and
    # Unverified — measured performance is shown separately, from recorded tasks
    comp = {sp.key: sp.competencies or [] for sp in db.scalars(select(Specialization))}
    for a in db.scalars(select(Agent).where(Agent.source == "CODE", Agent.version == 1)):
        if not a.skills and a.id in P.IDENTITIES:
            names = list(dict.fromkeys(c for k in a.specializations or [] for c in comp.get(k, [])))[:6]
            a.skills = [{"name": c, "level": "Unverified", "basis": "assigned", "ai_generated": False} for c in names]
    if not db.scalar(select(func.count(AgentRelationship.id))):
        ids = set(db.scalars(select(Agent.id)))
        for src, dst, kind, desc in P.RELATIONSHIPS:
            if src in ids and dst in ids:
                db.add(AgentRelationship(source_agent_id=src, target_agent_id=dst, relationship_type=kind, description=desc))
                n["relationships"] += 1
    db.flush()
    return n


_DEFAULT_LIMITS = ("Grant itself permissions or tool access", "Act outside the scope G-SUS delegates",
                   "Override the human owner, governance, budgets, approvals or the kill switch")


# ------------------------------------------------------------------------------------------------- lookups
class Lookups:
    """Species / specialization / department names in one query each (cards are built in bulk)."""

    def __init__(self, db: Session) -> None:
        self.species = {s.key: s for s in db.scalars(select(Species))}
        self.specs = {s.key: s for s in db.scalars(select(Specialization))}
        self.depts = {d.key: d for d in db.scalars(select(Department))}
        self.names = dict(db.execute(select(Agent.id, Agent.persona_name)).all())

    def species_ref(self, key: str) -> dict[str, Any] | None:
        s = self.species.get(key)
        if s is None:
            return {"key": key, "name": key, "category": "custom", "known": False} if key else None
        return {"key": s.key, "name": s.name, "category": s.category, "user_created": s.user_created, "known": True}

    def spec_refs(self, keys: list[str]) -> list[dict[str, Any]]:
        return [{"key": k, "name": self.specs[k].name if k in self.specs else k, "custom": k not in self.specs} for k in keys or []]

    def dept_ref(self, key: str) -> dict[str, Any] | None:
        d = self.depts.get(key)
        return {"key": d.key, "name": d.name} if d else ({"key": key, "name": key} if key else None)


def observation(a: Agent) -> dict[str, Any]:
    """Whether G-SUS can actually see this agent working — reported openly, never assumed."""
    last = _aware(a.last_active_at)
    if a.lifecycle not in ("ACTIVE",):
        return {"state": "not_active", "note": f"Lifecycle {a.lifecycle}: not accepting missions.", "last_active_at": last}
    if a.status != "active":
        return {"state": "suspended", "note": "Suspended by an administrator.", "last_active_at": last}
    if last is None:
        return {"state": "never_observed", "note": "No task has run yet — nothing to observe.", "last_active_at": None}
    if _now() - last > OBSERVED_WINDOW:
        return {"state": "offline", "note": f"No activity for {(_now() - last).days} days — reported as not currently observed.",
                "last_active_at": last}
    return {"state": "observed", "note": P.TRACE_WARNING, "last_active_at": last}


def achievements(a: Agent, onboarding: dict[str, Any] | None = None) -> list[str]:
    """Computed from recorded outcomes only — nothing is awarded that the logs do not show."""
    out = []
    ok = a.tasks_succeeded or 0
    for n, label in ((1, "First mission completed"), (10, "10 missions completed"), (100, "100 missions completed")):
        if ok >= n:
            out.append(label)
    if ok >= 10 and not (a.tasks_failed or 0):
        out.append("No failed missions (10+)")
    tests = (onboarding or {}).get("tests") or {}
    if tests and tests.get("passed") and tests.get("passed") == tests.get("total"):
        out.append("Onboarding capability checks passed")
    return out


def card(a: Agent, lk: Lookups, latest: dict[int | str, Any] | None = None) -> dict[str, Any]:
    sp = lk.species_ref(a.species_key)
    specs = lk.spec_refs(a.specializations or [])
    display = " · ".join(x for x in [a.persona_name or a.name, sp["name"] if sp else "Unassigned species",
                                     specs[0]["name"] if specs else (a.title or a.name)] if x)
    return {"id": a.id, "persona_name": a.persona_name or a.name, "role_name": a.name, "title": a.title or a.name,
            "display": display, "species": sp, "specializations": specs, "department": lk.dept_ref(a.department_key),
            "rank": a.rank, "lifecycle": a.lifecycle, "status": a.status, "custom": a.custom, "source": a.source,
            "supervisor": {"id": a.supervisor_id, "name": lk.names.get(a.supervisor_id) or a.supervisor_id} if a.supervisor_id else None,
            "description": a.description, "purpose": a.purpose, "traits": a.traits or [],
            "skills": a.skills or [], "latest_mission": (latest or {}).get(a.id), "achievements": achievements(a, a.onboarding),
            "observation": observation(a), "permission_level": a.permission_level,
            "performance": {"succeeded": a.tasks_succeeded, "failed": a.tasks_failed, "blocked": a.tasks_blocked,
                            "last_active_at": _aware(a.last_active_at)}}


def latest_missions(db: Session, ids: list[str] | None = None) -> dict[str, dict[str, Any]]:
    q = select(Task.agent_id, func.max(Task.id)).group_by(Task.agent_id)
    if ids is not None:
        q = q.where(Task.agent_id.in_(ids))
    last = dict(db.execute(q).all())
    out: dict[str, dict[str, Any]] = {}
    if last:
        for t in db.scalars(select(Task).where(Task.id.in_(list(last.values())))):
            out[t.agent_id] = {"id": t.id, "type": t.type, "status": t.status, "created_at": _aware(t.created_at)}
    return out


# ------------------------------------------------------------------------------------------------- listing
SORTS = {"name": lambda c: (c["persona_name"] or "").lower(),
         "rank": lambda c: (_RANK_ORDER.get(c["rank"], 99), (c["persona_name"] or "").lower()),
         "performance": lambda c: (-(c["performance"]["succeeded"] or 0), (c["persona_name"] or "").lower()),
         "activity": lambda c: (-(c["performance"]["last_active_at"].timestamp() if c["performance"]["last_active_at"] else 0),
                                (c["persona_name"] or "").lower())}
_RANK_ORDER = {"Custom": 0, "Council Member": 1, "Department Lead": 2, "Advisor": 3, "Team Lead": 4, "Senior Specialist": 5,
               "Specialist": 6, "Junior Agent": 7}


def list_cards(db: Session, *, q: str = "", department: str = "", specialization: str = "", species: str = "",
               status: str = "", sort: str = "name", include_archived: bool = False) -> list[dict[str, Any]]:
    """Everyone in one register — filters narrow it; nothing groups agents by race."""
    stmt = select(Agent)
    if not include_archived and status != "ARCHIVED":
        stmt = stmt.where(Agent.lifecycle != "ARCHIVED")
    if department:
        stmt = stmt.where(Agent.department_key == department)
    if species:
        stmt = stmt.where(Agent.species_key == species)
    if status:
        stmt = stmt.where(or_(Agent.lifecycle == status.upper(), Agent.status == status.lower()))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Agent.persona_name).like(like), func.lower(Agent.name).like(like),
                              func.lower(Agent.title).like(like)))
    agents = list(db.scalars(stmt))
    if specialization:  # JSON list column: filtered in Python (portable — no JSON equality in SQL)
        agents = [a for a in agents if specialization in (a.specializations or [])]
    lk = Lookups(db)
    latest = latest_missions(db, [a.id for a in agents])
    cards = [card(a, lk, latest) for a in agents]
    return sorted(cards, key=SORTS.get(sort, SORTS["name"]))


def facets(db: Session) -> dict[str, Any]:
    lk = Lookups(db)
    rows = list(db.scalars(select(Agent).where(Agent.lifecycle != "ARCHIVED")))
    count = lambda xs: {k: xs.count(k) for k in sorted(set(xs))}  # noqa: E731
    return {"departments": [{"key": d.key, "name": d.name, "count": sum(1 for a in rows if a.department_key == d.key),
                             "manager_id": d.manager_id} for d in lk.depts.values()],
            "species": [{"key": k, "name": (lk.species[k].name if k in lk.species else k), "count": v}
                        for k, v in count([a.species_key for a in rows if a.species_key]).items()],
            "specializations": [{"key": k, "name": (lk.specs[k].name if k in lk.specs else k), "count": v}
                                for k, v in count([s for a in rows for s in (a.specializations or [])]).items()],
            "statuses": count([a.lifecycle for a in rows]), "ranks": P.RANKS, "total": len(rows)}


# ------------------------------------------------------------------------------------------------- profile
def chain_of_command(db: Session, a: Agent) -> list[dict[str, Any]]:
    out, seen, cur = [], {a.id}, a
    while cur.supervisor_id and cur.supervisor_id not in seen:
        sup = db.get(Agent, cur.supervisor_id)
        if sup is None:
            out.append({"id": cur.supervisor_id, "name": cur.supervisor_id, "missing": True})
            break
        out.append({"id": sup.id, "name": sup.persona_name or sup.name, "title": sup.title or sup.name})
        seen.add(sup.id)
        cur = sup
    return out


def permissions_view(db: Session, a: Agent) -> dict[str, Any]:
    """What the agent may actually do — read from permission_level, grants and budgets. Race/rank/personality: nothing."""
    lvl = a.permission_level
    allowed = sorted(k for k, v in permissions.ACTION_LEVELS.items() if int(v) <= lvl and v < permissions.APPROVAL_THRESHOLD)
    approval = sorted(k for k, v in permissions.ACTION_LEVELS.items() if v >= permissions.APPROVAL_THRESHOLD)
    grants = [{"tool": g.tool, "operations": g.operations, "enabled": g.enabled, "expires_at": _aware(g.expires_at),
               "max_calls_per_day": g.max_calls_per_day}
              for g in db.scalars(select(ToolGrant).where(ToolGrant.subject_kind == "agent", ToolGrant.subject_id == a.id))]
    return {"permission_level": lvl, "allowed_actions": allowed, "approval_required_actions": approval, "tool_grants": grants,
            "tool_suggestions": a.tool_suggestions or [], "daily_token_budget": a.daily_token_budget,
            "tokens_today": a.tokens_today, "not_to_do": (a.mission or {}).get("not_to_do", []),
            "note": "Race, rank, title, personality and relationships grant nothing. Access comes only from the permission "
                    "level and Tool Gateway grants, set through governance; LEVEL 4–5 actions always need a human approval."}


def profile(db: Session, a: Agent) -> dict[str, Any]:
    lk = Lookups(db)
    base = card(a, lk, latest_missions(db, [a.id]))
    sp = lk.species.get(a.species_key)
    subs = [{"id": s.id, "name": s.persona_name or s.name, "title": s.title or s.name}
            for s in db.scalars(select(Agent).where(Agent.supervisor_id == a.id, Agent.lifecycle != "ARCHIVED"))]
    rels = []
    for r in db.scalars(select(AgentRelationship).where(or_(AgentRelationship.source_agent_id == a.id,
                                                            AgentRelationship.target_agent_id == a.id))):
        other = r.target_agent_id if r.source_agent_id == a.id else r.source_agent_id
        rels.append({"id": r.id, "type": r.relationship_type, "with": {"id": other, "name": lk.names.get(other, other)},
                     "direction": "out" if r.source_agent_id == a.id else "in", "description": r.description})
    current = [{"id": t.id, "type": t.type, "status": t.status, "created_at": _aware(t.created_at)}
               for t in db.scalars(select(Task).where(Task.agent_id == a.id, Task.status.in_(ACTIVE_TASK)).order_by(Task.id.desc()).limit(20))]
    history = [{"id": t.id, "type": t.type, "status": t.status, "created_at": _aware(t.created_at),
                "finished_at": _aware(t.finished_at)}
               for t in db.scalars(select(Task).where(Task.agent_id == a.id).order_by(Task.id.desc()).limit(25))]
    versions = [{"version": v.version, "note": v.note, "changed_by": v.changed_by, "changed_at": _aware(v.changed_at)}
                for v in db.scalars(select(AgentVersion).where(AgentVersion.agent_id == a.id).order_by(AgentVersion.version.desc()).limit(30))]
    calls = db.scalar(select(func.count(LLMCall.id)).where(LLMCall.agent_id == a.id)) or 0
    done = (a.tasks_succeeded or 0) + (a.tasks_failed or 0) + (a.tasks_blocked or 0)
    return base | {
        "identity": {"persona_name": a.persona_name or a.name, "alt_names": a.alt_names or [], "title": a.title or a.name,
                     "traits": a.traits or [], "personality": a.personality,
                     "note": "Personality shapes expression and priorities — never security, permissions or tool access."},
        "race": {"species": base["species"], "folklore_excerpt": excerpt(sp.folklore) if sp else "",
                 "canon_excerpt": excerpt(sp.canon) if sp else "", "article": f"/bestiary/{a.species_key}" if a.species_key else None,
                 "note": "Race is an identity dimension; it does not limit what the agent can be trained to do."},
        "job": {"description": a.description, "mission": a.mission or {}, "title": a.title or a.name},
        "tools": {"skills": a.skills or [], "suggestions": a.tool_suggestions or []},
        "hierarchy": {"department": base["department"], "rank": a.rank, "chain_of_command": chain_of_command(db, a)},
        "subordinates": subs,
        "permissions": permissions_view(db, a),
        "current_missions": current,
        "history": {"tasks": history, "versions": versions},
        "results": {"succeeded": a.tasks_succeeded, "failed": a.tasks_failed, "blocked": a.tasks_blocked,
                    "success_rate": round((a.tasks_succeeded or 0) / done, 3) if done else None,
                    "tokens_total": a.tokens_total, "cost_total_usd": a.cost_total_usd, "model_calls": calls,
                    "onboarding": a.onboarding or {},
                    "note": "Measured from recorded tasks and model calls; no figure here is estimated."},
        "communication": {"styles": a.communication_style or [], "languages": a.languages or []},
        "relationships": rels,
        "trace": {"tasks_traced": done, "observation": observation(a)},
    }


# ------------------------------------------------------------------------------------------------- G-SUS support
_WORD = re.compile(r"[a-zåäöéü0-9+#.'/-]+")


def find_agents(db: Session, text: str, *, limit: int = 5, only_active: bool = True) -> list[dict[str, Any]]:
    """Who can do this? Scores agents by specialization keywords, names and descriptions (deterministic, explainable)."""
    words = set(_WORD.findall(text.lower()))
    low = text.lower()
    lk = Lookups(db)
    scored = []
    for a in db.scalars(select(Agent).where(Agent.lifecycle != "ARCHIVED")):
        if only_active and (a.lifecycle != "ACTIVE" or a.status != "active"):
            continue
        why, score = [], 0.0
        for k in a.specializations or []:
            sp = lk.specs.get(k)
            hits = [kw for kw in (sp.keywords if sp else [k]) if (kw in words if " " not in kw else kw in low)]
            if hits:
                score += 2 + len(hits)
                why.append(f"{sp.name if sp else k}: {', '.join(hits[:3])}")
        hay = f"{a.title} {a.name} {a.description} {a.purpose}".lower()
        overlap = [w for w in words if len(w) > 3 and w in hay]
        if overlap:
            score += 0.5 * len(overlap)
            why.append("role/description: " + ", ".join(sorted(overlap)[:4]))
        if score:
            scored.append((score, a, why))
    scored.sort(key=lambda x: (-x[0], x[1].id))
    latest = latest_missions(db, [a.id for _, a, _ in scored[:limit]])
    return [card(a, lk, latest) | {"match": {"score": round(s, 2), "why": why}} for s, a, why in scored[:limit]]


def identity_line(db: Session, agent_id: str) -> str:
    a = db.get(Agent, agent_id)
    if a is None:
        return agent_id
    lk = Lookups(db)
    return card(a, lk)["display"]
