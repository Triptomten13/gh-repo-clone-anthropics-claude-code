"""G-sus — the head orchestrator.

objective → understand (intents + entity resolution) → clarify if needed → plan (steps
over *registered* capabilities only, with dependencies) → execute through the central
orchestrator (parallel where independent) → approval gates for high-impact actions →
collect & compare results → detect contradictions → verify → answer (grounded research
and labelled creative output kept apart).

G-sus never executes high-impact actions itself and never grants permissions: approval
gates record a human decision; the responsible module performs the action afterwards.

Every run is traced (DAEMON OBSERVABILITY): one `runs` row (kind "gsus", ref "gsus:<id>", parent = the run that
started it, e.g. an /api/ai/ask request), events for the plan, each step, retrievals, approvals and the answer, and
the runs of its delegated tasks attached as children. A run that waits for an approval is reopened on resume.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents.catalog import build_orchestrator
from ..ai import tracing
from ..ai.llm import LLMRefused, LLMUnavailable, get_provider
from ..ai.providers import tokenize
from ..governance import core as gov
from ..governance import observability as obs
from ..knowledge import canon, search
from ..models import AgentMessage, Approval, CollaborationSession, Document, GsusRun, GsusStep, LLMCall, Product, Task
from ..security import untrusted
from . import modes as MODES

_BEINGS = (r"agents?|medarbetare|employee|colleague|kollega|specialist|assistent|assistant|demon|djinn|fairy|fé|elf|alv|"
           r"leprechaun|sasquatch|bigfoot|goblin|tomte|troll|spirit|ande|väsen|being|dragon|drake|kobold|gnome|undine|salamander")
INTENTS: list[tuple[str, str]] = [
    # Custom Agent Creator / personnel register — exclusive intents (see plan())
    ("create_agent", rf"\b(skapa|create|make|gör|bygg|build|summon|frammana|recruit|rekrytera|anställ|hire|design)\b[^.?!]{{0,60}}"
                     rf"\b({_BEINGS})\b|\b(we need|i need|jag behöver|vi behöver|jag vill ha|i want)\b[^.?!]{{0,30}}"
                     rf"\b(someone|somebody|någon|a new|en ny|ett nytt|an? ({_BEINGS})|en ({_BEINGS}))\b"),
    ("personnel_query", r"\b(who can|which agents?|vem kan|vilken agent|vilka agenter|who (handles|does|is responsible)|"
                        r"vem (ansvarar|sköter))\b"),
    ("approval_action", r"\b(launch|publish|buy|purchase|spend|place an order|send (an )?(email|message)|delete|lansera|publicera|köp|spendera|skicka|radera)\b"),
    ("product_evaluation", r"\b(evaluat\w*|analy[sz]\w*|assess\w*|scor\w*|economics|profitab\w*|margin|utvärdera|analysera|bedöm\w*|lönsam\w*)"),
    ("brand_creation", r"\b(brand\w*|concepts?|identit\w*|varumärke\w*|koncept\w*)"),
    ("council", r"\b(council|verdict|råd(et)?|rådslag)\b"),
    ("discussion", r"\b(discuss\w*|debate|diskutera\w*)"),
    ("think_sideways", r"(what else|sideways|unexpected|other markets|oväntade?|vad mer)"),
    ("campaign", r"\b(campaigns?|ads|advert\w*|kampanj\w*|annons\w*)"),
    ("market_scan", r"\b(trends?|market scan|scan the market|marknadsskanning|trender)\b"),
    ("canon_check", r"\b(canon|lore|contradictions?|archivum|kanon|motsägelse\w*)"),
    ("creative_writing", r"\b(song|lyrics|poem|poetry|haiku|jingle|slogans?|taglines?|låt(text)?|sångtext|dikt|refräng|visa)\b"),
    ("archive_question", r"(\?\s*$|^\s*(what|who|when|where|why|how|explain|describe|vad|vem|när|var|varför|hur|förklara|beskriv)\b|\barchive\b|\bsources?\b|\barkiv\w*|\bkäll\w*)"),
]
NEEDS_PRODUCT = {"product_evaluation", "brand_creation", "council", "discussion", "think_sideways", "campaign"}
HIGH_IMPACT = [(r"launch|lansera", "product.launch"), (r"publish|publicera", "content.publish"), (r"buy|purchase|order|köp", "purchase.order"),
               (r"spend|spendera", "ads.budget_change"), (r"send|skicka", "customer.message"), (r"delete|radera", "data.delete")]


# ----------------------------------------------------------------------------- understanding
def detect_intents(objective: str) -> list[str]:
    return [name for name, pat in INTENTS if re.search(pat, objective, re.I | re.M)]


def resolve_product(db: Session, objective: str) -> tuple[Product | None, list[dict[str, Any]]]:
    m = re.search(r"(?:product|produkt)\s*#?(\d+)|#(\d+)", objective, re.I)
    if m:
        p = db.get(Product, int(m.group(1) or m.group(2)))
        if p:
            return p, []
    obj = set(tokenize(objective))
    scored = []
    for p in db.scalars(select(Product)).all():
        name = set(tokenize(p.name))
        if not name:
            continue
        overlap = len(obj & name) / len(name)
        if overlap > 0:
            scored.append((overlap, len(obj & name), p))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    cands = [{"product_id": p.id, "name": p.name, "match": round(o, 2)} for o, _, p in scored[:3]]
    if scored and scored[0][0] >= 0.5 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.15 or scored[0][1] > scored[1][1]):
        return scored[0][2], cands
    return None, cands


def _llm_intents(objective: str, tier: str, run: GsusRun, db: Session) -> list[str] | None:
    provider = get_provider()
    if getattr(provider, "name", "none") == "none":
        return None
    schema = {"type": "object", "additionalProperties": False, "required": ["intents"],
              "properties": {"intents": {"type": "array", "items": {"type": "string", "enum": [n for n, _ in INTENTS] + ["risk_review"]}}}}
    try:
        res = provider.complete(system="Classify the user's objective into the platform's capabilities. Choose only from the enum.",
                                prompt=untrusted.wrap(objective, "objective", "user objective"), schema=schema, tier="fast")
    except (LLMUnavailable, LLMRefused):
        return None
    tracing.record(db, getattr(res, "attempts", []), run_id=run.id, agent_id="gsus", purpose="plan", fallback_result=res)
    return [i for i in (res.data or {}).get("intents", []) if i in dict(INTENTS) or i == "risk_review"] or None


def _has_model() -> bool:
    return getattr(get_provider(), "name", "none") != "none"


def _custom_delegate(db: Session, objective: str) -> dict[str, Any] | None:
    """G-SUS uses the personnel register when choosing whom to delegate to: an ACTIVE custom agent whose
    specializations clearly match takes objectives no built-in capability covers."""
    from ..personnel import registry

    for c in registry.find_agents(db, objective, limit=3):
        if c["custom"] and c["match"]["score"] >= 3:
            return c
    return None


def _swedish(text: str) -> bool:
    return bool(re.search(r"[åäö]|\b(och|jag|vi|som|skapa|behöver|vem|kan|en ny)\b", text, re.I))


# ----------------------------------------------------------------------------- planning
def plan(db: Session, run: GsusRun) -> list[dict[str, Any]]:
    s = run.settings
    intents = detect_intents(run.objective)
    if not intents and s.get("use_llm") and s.get("planner") == "llm":
        intents = _llm_intents(run.objective, MODES.DEPTH_TIER[s["depth"]], run, db) or []
        run.plan_method = "llm" if intents else "heuristic"
    for extra in MODES.MODES[s["mode"]]["extra_intents"]:
        if extra not in intents and (extra != "archive_question" or not (set(intents) & NEEDS_PRODUCT)):
            intents.append(extra)
    for exclusive in ("create_agent", "personnel_query"):  # recruiting or asking about staff is not product work
        if exclusive in intents:
            intents = [exclusive]
            break
    if not intents:
        intents = ["archive_question"] if db.query(Document).filter(Document.status == "ready").count() else []
        if (hit := _custom_delegate(db, run.objective)) is not None:  # a custom agent whose specialization matches
            intents = ["delegate_custom"]
    run.intent = ",".join(intents)
    product, cands = (None, [])
    if set(intents) & (NEEDS_PRODUCT | {"risk_review", "approval_action"}):
        product, cands = resolve_product(db, run.objective)
    if set(intents) & NEEDS_PRODUCT and product is None:
        run.status = "needs_clarification"
        run.clarification = ("Which product do you mean?" + (" Closest matches: " + "; ".join(f"#{c['product_id']} {c['name']}" for c in cands)
                                                            if cands else " No product in the database matches — name one, or add it in the Product Laboratory."))
        return []
    if not intents:
        run.status = "needs_clarification"
        run.clarification = ("I can evaluate products, create brand concepts, convene a council or discussion, think sideways, draft campaigns, "
                             "scan markets, answer from the Archive, and check canon for contradictions. What should I do?")
        return []
    steps: list[dict[str, Any]] = []

    def add(title: str, kind: str, task_type: str = "", payload: dict | None = None, deps: list[int] | None = None) -> int:
        steps.append({"ordinal": len(steps), "title": title, "kind": kind, "task_type": task_type, "payload": payload or {}, "depends_on": deps or []})
        return len(steps) - 1

    if intents == ["create_agent"]:
        from ..personnel import creator

        if not creator.detect_specializations(db, run.objective) and not (s.get("use_llm") and _has_model()):
            run.status = "needs_clarification"
            run.clarification = ("What should the new agent work on? One line is enough — e.g. research, software, "
                                 "monitoring, botany, costs, music — and I will propose the rest.")
            return []
        add("Agent Creator: duplicate check + proposal (nothing is created until you confirm)", "agent_proposal",
            payload={"idea": run.objective})
        add("Compare, verify and answer", "synthesis", deps=[0])
        return steps
    if intents == ["personnel_query"]:
        add("Personnel register: who can do this?", "personnel_lookup", payload={"question": run.objective})
        add("Compare, verify and answer", "synthesis", deps=[0])
        return steps
    if intents == ["delegate_custom"]:
        add(f"Delegate to {hit['display']}", "task", f"custom.{hit['id']}", {"objective": run.objective})
        add("Compare, verify and answer", "synthesis", deps=[0])
        return steps
    pid = product.id if product else None
    marker = f"gsus-{run.id}"
    ev = add(f"Evaluate '{product.name}'", "task", "ceo.evaluate_product", {"product_id": pid, "refresh": marker}) \
        if pid and ("product_evaluation" in intents or set(intents) & {"brand_creation", "council", "campaign"}) else None
    after = [ev] if ev is not None else []
    if "risk_review" in intents and pid:
        add(f"Risk review of '{product.name}'", "task", "risk.assess", {"product_id": pid, "reassess": True, "rev": marker})
    if "brand_creation" in intents:
        add("Creative competition + review panel", "task", "flare.competition", {"product_id": pid}, after)
    if "council" in intents:
        add("Creative council (8 seats)", "task", "flare.council", {"product_id": pid}, after)
    if "discussion" in intents:
        add("Structured agent discussion", "task", "flare.discussion", {"product_id": pid}, after)
    if "think_sideways" in intents:
        add("Think Sideways", "task", "flare.sideways", {"product_id": pid, "question": run.objective})
    if "campaign" in intents:
        add("Campaign testing matrix", "task", "flare.campaign_matrix", {"product_id": pid}, after)
    if "market_scan" in intents:
        scan = add("Market scan (configured sources)", "task", "intel.scan_market", {"rev": marker})
        add("Trend analysis", "task", "trend.analyze", {"rev": marker}, [scan])
    if "creative_writing" in intents:  # DAEMON CREATIVE INTELLIGENCE: several models, independent critics, synthesis, hard budget
        add("Creative tournament (models compete, critics judge, synthesis)", "task", "creative.tournament",
            {"brief": run.objective, "budget": {"max_calls": 8, "max_models": 3, "critics": 2, "max_rounds": 1}})
    if "canon_check" in intents:
        add("Canon contradiction check", "canon_check")
    if "archive_question" in intents:
        add("Archive retrieval + grounded answer", "retrieval", payload={"question": run.objective})
    if "approval_action" in intents:
        action = next((a for pat, a in HIGH_IMPACT if re.search(pat, run.objective, re.I)), "data.delete")
        add(f"Human approval required: {action}", "approval_gate", payload={"action": action, "product_id": pid},
            deps=[i for i in range(len(steps))])
    add("Compare, verify and answer", "synthesis", deps=list(range(len(steps))))
    return steps


# ----------------------------------------------------------------------------- execution
def start(db: Session, objective: str, mode: str, overrides: dict[str, Any], actor: str) -> GsusRun:
    run = GsusRun(objective=objective.strip()[:4000], mode=mode, settings=MODES.settings_for(mode, overrides), created_by=actor)
    db.add(run)
    db.flush()
    steps = plan(db, run)
    for st in steps:
        db.add(GsusStep(run_id=run.id, ordinal=st["ordinal"], title=st["title"], kind=st["kind"], task_type=st["task_type"],
                        payload=st["payload"], depends_on=st["depends_on"]))
    gov.audit(db, actor, "gsus.run", f"gsus_run:{run.id}", intents=run.intent, steps=len(steps))
    db.commit()  # before the trace opens: the trace writes in its own transaction and must not wait on this one
    with traced(db, run):
        obs.event("plan", f"{len(steps)} step(s)", {"intents": run.intent, "status": run.status, "steps": [
            {k: st[k] for k in ("ordinal", "title", "kind", "task_type", "depends_on")} for st in steps]})
        if run.status != "needs_clarification":
            execute(db, run)
    return run


_TRACE_STATUS = {"completed": "succeeded"}


@contextmanager
def traced(db: Session, run: GsusRun) -> Iterator[int]:
    """Open (or reopen) this run's trace, make it current, and close it with the run's state. Call with no write
    transaction open on `db`."""
    rid = obs.run_of_ref(db, f"gsus:{run.id}")
    if rid is None:
        rid = obs.start("gsus", f"gsus:{run.id}", workflow="gsus" if run.mode == "gsus" else f"gsus.{run.mode}", agent_id="gsus",
                        user_email=(run.created_by or "").removeprefix("user:"), parent_id=obs.current_run.get(),
                        input={"objective": run.objective, "mode": run.mode, "settings": run.settings})
    else:
        obs.reopen(rid)
    token = obs.current_run.set(rid)
    try:
        yield rid
    except Exception as e:
        db.rollback()
        obs.event("error", type(e).__name__, {"error": str(e)[:500]})
        obs.finish(rid, "failed", error=f"{type(e).__name__}: {e}")
        raise
    else:
        db.commit()
        calls = db.scalars(select(LLMCall).where(LLMCall.run_id == run.id)).all()
        obs.finish(rid, _TRACE_STATUS.get(run.status, run.status), output={"answer": run.answer, "answer_method": run.answer_method,
                   "verification": run.verification, "contradictions": run.contradictions, "citations": len(run.citations or [])},
                   tokens_in=sum(c.input_tokens for c in calls), tokens_out=sum(c.output_tokens for c in calls),
                   cost_usd=sum(c.cost_usd for c in calls))
    finally:
        obs.current_run.reset(token)


def _step_event(st: GsusStep) -> None:
    obs.event("step", st.title, {"ordinal": st.ordinal, "kind": st.kind, "task_type": st.task_type, "status": st.status,
                                 "task_id": st.task_id, "approval_id": st.approval_id, "summary": (st.summary or "")[:500]})


def _steps(db: Session, run: GsusRun) -> list[GsusStep]:
    return db.scalars(select(GsusStep).where(GsusStep.run_id == run.id).order_by(GsusStep.ordinal)).all()


def _challenged(db: Session, run: GsusRun, orch: Any, steps: list[Any]) -> bool:
    """The Devil's Advocate reviews G-SUS's own plan before anything runs, when the plan is consequential (a step handled by
    an agent of level ≥ 3: internal operations, publishing, money). Steps the platform will stop for a human approval are
    marked as such, so the review never blocks what governance already gates; a BLOCK stops the run before execution."""
    from ..autonomy import advocate

    task_steps = [st for st in steps if st.kind == "task" and st.status == "pending"]
    levels = {st.ordinal: int(getattr(orch.agents.get(orch.routes.get(st.task_type, "")), "level", 0) or 0) for st in task_steps}
    if not task_steps or max(levels.values(), default=0) < 3:
        return False
    crit = advocate.review(db, {
        "kind": "plan", "ref": f"gsus:{run.id}", "proposer": "agent:gsus", "summary": f"G-SUS plan for: {run.objective[:200]}",
        "objective": run.objective, "evidence": [f"intents: {run.intent or '—'}", f"planned by {run.plan_method}"],
        "alternatives": [], "assumptions": [], "risks": [f"step {st.task_type} runs with agent level {levels[st.ordinal]}" for st in task_steps if levels[st.ordinal] >= 3],
        "verification": "G-SUS collects and checks each step's result" if any(st.kind != "task" for st in steps) else "",
        "permissions": sorted({st.task_type for st in task_steps}),
        "steps": [{"action": st.task_type, "level": levels[st.ordinal], "approval_gated": levels[st.ordinal] >= 4} for st in task_steps]},
        actor="devils_advocate")
    run.settings = {**(run.settings or {}), "critique_id": crit.id, "critique_verdict": crit.verdict}
    if crit.verdict == "block":
        run.status, run.answer = "blocked", f"The Devil's Advocate stopped this plan before anything ran (critique #{crit.id}): {crit.summary}"
        db.commit()
        return True
    db.commit()
    return False


def execute(db: Session, run: GsusRun) -> GsusRun:
    if gov.kill_switch_engaged(db):
        run.status, run.answer = "cancelled", "Emergency stop is engaged; nothing was executed."
        db.commit()
        return run
    orch = build_orchestrator()
    run.status = "running"
    steps = _steps(db, run)
    by_ord = {s.ordinal: s for s in steps}
    if _challenged(db, run, orch, steps):
        return run
    # 1) submit every runnable task step (independent ones run in parallel order, dependent ones wait via depends_on)
    for st in steps:
        if st.kind != "task" or st.status != "pending":
            continue
        deps = [by_ord[d] for d in st.depends_on]
        if any(d.status in ("failed", "blocked", "cancelled") for d in deps):
            st.status, st.summary = "cancelled", "dependency did not complete"
            continue
        try:
            t = orch.submit(db, st.task_type, st.payload, requested_by="gsus", priority=8, force=True,
                            depends_on=[d.task_id for d in deps if d.task_id])
        except Exception as e:  # noqa: BLE001 - governance errors become step state
            st.status, st.summary = "blocked", str(e)
            continue
        st.task_id, st.status = t.id, "running"
    db.commit()
    for st in steps:
        if st.kind == "task" and st.status != "pending":
            _step_event(st)
    if (rid := obs.current_run.get()) is not None:
        obs.flush(rid)  # nothing is held open on `db` here
    orch.drain(500)
    db.expire_all()
    # 2) collect task results
    for st in _steps(db, run):
        if st.kind == "task" and st.task_id and st.status == "running":
            t = db.get(Task, st.task_id)
            msg = db.scalars(select(AgentMessage).where(AgentMessage.task_id == t.id).order_by(AgentMessage.id.desc())).first()
            st.status = {"succeeded": "completed", "blocked": "blocked", "failed": "failed", "cancelled": "cancelled"}.get(t.status, st.status)
            st.summary = (msg.summary if msg else t.error or t.status)[:2000]
            from ..personnel import registry

            st.output = _digest(db, st, t) | {"delegated_to": {"id": t.agent_id, "display": registry.identity_line(db, t.agent_id)}}
            _step_event(st)
    # 3) inline steps: canon, retrieval, approval gates
    for st in _steps(db, run):
        if st.status != "pending":
            continue
        if st.kind == "canon_check":
            cs = canon.contradictions(db)
            st.status, st.output = "completed", {"contradictions": cs}
            st.summary = f"{len(cs)} canon/timeline contradiction(s) found" if cs else "no contradictions in active canon"
        elif st.kind == "retrieval":
            llm = _llm_fn(db, run) if run.settings.get("use_llm") else None
            try:
                ans = search.grounded_answer(db, st.payload["question"], llm=llm, mode_prompt=MODES.system_prompt(run.settings),
                                             strictness=run.settings["strictness"], user=_run_user(db, run))
            except (LLMUnavailable, LLMRefused):
                ans = search.grounded_answer(db, st.payload["question"], user=_run_user(db, run))
            ans.pop("llm_result", None)
            st.status, st.output = "completed", ans
            st.summary = f"{len(ans['citations'])} cited passage(s); method {ans['method']}"
        elif st.kind == "agent_proposal":
            from ..personnel import creator

            prop = creator.design(db, st.payload["idea"], use_model=bool(run.settings.get("use_llm")), source="GSUS_CHAT")
            first = prop["proposals"][0]
            st.status, st.output = "completed", {"proposal": prop, "run_id": run.id}
            st.summary = (f"proposed {first['preview']['display']} ({prop['method']})"
                          + (f"; {len(prop['duplicates'])} similar agent(s) found" if prop["duplicates"] else "; no similar agent"))
        elif st.kind == "personnel_lookup":
            from ..personnel import registry

            hits = registry.find_agents(db, st.payload["question"], limit=5, only_active=False)
            st.status, st.output = "completed", {"agents": hits}
            st.summary = f"{len(hits)} matching agent(s)" if hits else "nobody in the register matches — the Agent Creator can propose one"
        elif st.kind == "approval_gate":
            deps = [by_ord[d] for d in st.depends_on]
            if any(d.status == "running" for d in deps):
                continue
            a = gov.request_approval(db, st.payload["action"], f"G-sus run #{run.id}: {run.objective[:120]}", "gsus",
                                     f"Requested by G-sus on behalf of {run.created_by}. Objective: {run.objective}", {"gsus_run": run.id, **st.payload})
            st.approval_id, st.status = a.id, "waiting_for_approval"
            st.summary = f"approval #{a.id} ({st.payload['action']}) pending — G-sus will not perform this action itself"
        if st.status != "pending":
            _step_event(st)
    if (rid := obs.current_run.get()) is not None:
        obs.link_children(db, rid, [st.task_id for st in _steps(db, run) if st.task_id])
    db.commit()
    return _finish(db, run)


def resume(db: Session, run: GsusRun) -> GsusRun:
    with traced(db, run):
        _resume(db, run)
    return run


def cancelled(db: Session, run: GsusRun, actor: str) -> None:
    """Record a cancellation in the run's trace (after the cancellation is committed)."""
    with traced(db, run):
        obs.event("cancelled", f"cancelled by {actor}", {"status": run.status})


def _resume(db: Session, run: GsusRun) -> GsusRun:
    for st in _steps(db, run):
        if st.status == "waiting_for_approval" and st.approval_id:
            a = db.get(Approval, st.approval_id)
            if a.status == "approved":
                st.status = "completed"
                st.summary = (f"approved by {a.decided_by}. The action is performed by its responsible module "
                              f"(e.g. Brand Portfolio activation, Campaign launch), never by G-sus.")
            elif a.status == "rejected":
                st.status, st.summary = "cancelled", f"rejected by {a.decided_by}: {a.decision_note}"
            else:
                continue
            obs.event("approval", f"approval #{a.id} {a.status}", {"approval_id": a.id, "decided_by": a.decided_by, "step": st.title})
            _step_event(st)
    db.commit()
    return _finish(db, run)


def _finish(db: Session, run: GsusRun) -> GsusRun:
    steps = _steps(db, run)
    waiting = [s for s in steps if s.status == "waiting_for_approval"]
    synth = next((s for s in steps if s.kind == "synthesis"), None)
    run.contradictions = detect_contradictions(db, run, steps)
    run.verification = verify(steps)
    citations = [c for s in steps if s.kind == "retrieval" for c in s.output.get("citations", [])]
    run.citations = citations
    if waiting:
        run.status = "waiting_for_approval"
    else:
        run.answer, run.answer_method = compose(db, run, steps)
        if synth:
            synth.status, synth.summary = "completed", "answer composed"
        hard_fail = [s for s in steps if s.kind != "synthesis" and s.status in ("failed",)]
        run.status = "failed" if hard_fail and len(hard_fail) == len([s for s in steps if s.kind != "synthesis"]) else "completed"
        run.finished_at = datetime.now(UTC)
        obs.event("answer", run.answer_method or "", {"status": run.status, "method": run.answer_method,
                                                       "contradictions": len(run.contradictions or []), "citations": len(citations),
                                                       "verification": run.verification})
    db.commit()
    return run


def _digest(db: Session, st: GsusStep, t: Task) -> dict[str, Any]:
    r = t.result or {}
    if st.task_type == "ceo.evaluate_product":
        p = db.get(Product, st.payload["product_id"])
        return {"product": p.name, "score": p.opportunity_score, "confidence": p.score_confidence, "net_margin": p.net_margin,
                "compliance": p.compliance_status, "flags": (p.score_breakdown or {}).get("flags", [])}
    if st.task_type in ("flare.competition", "flare.council", "flare.panel", "flare.discussion") and r.get("session_id"):
        s = db.get(CollaborationSession, r["session_id"])
        d = s.decision if s else {}
        return {"session_id": r["session_id"], "status": s.status if s else None,
                "ranking": [{k: x[k] for k in ("name", "mean", "stdev", "consensus")} for x in d.get("ranking", [])[:3]],
                "outcome": d.get("outcome"), "council": d.get("council"), "dissent": d.get("dissent")}
    if st.task_type == "flare.sideways":
        return {"high_potential": r.get("high_potential", []), "domains": [x["domain"] for x in r.get("domains", [])]}
    if st.task_type == "flare.campaign_matrix":
        return {"campaigns": len(r.get("campaign_ids", [])), "budget_sek": (r.get("cells") or [{}])[0].get("budget_recommendation_sek")}
    return {k: v for k, v in r.items() if isinstance(v, (int, float, str)) or k in ("trends",)}


# ----------------------------------------------------------------------------- comparison & verification
def detect_contradictions(db: Session, run: GsusRun, steps: list[GsusStep]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    ev = next((s.output for s in steps if s.task_type == "ceo.evaluate_product" and s.status == "completed"), None)
    if ev:
        if (ev.get("score") or 0) >= 65 and ev.get("net_margin") is not None and ev["net_margin"] <= 0:
            out.append({"between": "opportunity score ↔ economics", "detail": f"score {ev['score']} looks attractive but net margin is {ev['net_margin']:.0%}"})
        if ev.get("compliance") in ("blocked", "restricted") and "approval_action" in run.intent:
            out.append({"between": "objective ↔ compliance", "detail": f"you asked for a high-impact action but compliance is '{ev['compliance']}'"})
        if any("engagement_only" in f for f in ev.get("flags", [])):
            out.append({"between": "demand signal ↔ purchases", "detail": "demand rests on engagement, not verified purchases"})
    for s in steps:
        for r in (s.output or {}).get("ranking") or []:
            if r.get("consensus") == "split":
                out.append({"between": f"{s.title} seats", "detail": f"split verdict on '{r['name']}' (±{r['stdev']})"})
        if s.task_type == "flare.discussion" and (s.output or {}).get("outcome") == "iterate":
            comp = next((x for x in steps if x.task_type == "flare.competition" and x.status == "completed"), None)
            if comp:
                out.append({"between": "discussion ↔ competition", "detail": "the CEO seat says iterate while the competition shortlisted a concept"})
        if s.kind == "canon_check":
            for c in (s.output or {}).get("contradictions", []):
                out.append({"between": c["type"], "detail": f"{c['subject']} / {c['predicate']}: " + " vs ".join(v.get("object") or v.get("date_text", "") for v in c["values"])})
        if s.kind == "retrieval":
            classes = {c["evidence_class"] for c in (s.output or {}).get("citations", [])}
            if "fiction_canon" in classes and len(classes) > 1:
                out.append({"between": "archive sources", "detail": "answer draws on both fictional canon and non-fiction sources — they are labelled separately"})
            if (s.output or {}).get("grounding", {}).get("invalid_citations"):
                out.append({"between": "answer ↔ sources", "detail": "the model cited sources that were not retrieved; those citations were rejected"})
    return out


def verify(steps: list[GsusStep]) -> dict[str, Any]:
    work = [s for s in steps if s.kind != "synthesis"]
    by = {k: [s.title for s in work if s.status == k] for k in ("completed", "blocked", "failed", "cancelled", "waiting_for_approval", "pending", "running")}
    grounded = all((s.output or {}).get("grounding", {}).get("supported", True) for s in work if s.kind == "retrieval")
    return {"steps": len(work), **{k: v for k, v in by.items() if v}, "all_completed": len(by["completed"]) == len(work),
            "retrieval_grounded": grounded}


# ----------------------------------------------------------------------------- answer
def _run_user(db: Session, run: GsusRun):
    """Retrieval inside a run uses the permissions of the person who started it (agents never read more than them)."""
    from ..models import User

    return db.scalars(select(User).where(User.email == (run.created_by or "").removeprefix("user:"))).first()


def _llm_fn(db: Session, run: GsusRun):
    provider = get_provider()
    if getattr(provider, "name", "none") == "none":
        return None
    tier = MODES.DEPTH_TIER[run.settings["depth"]]

    def call(system: str, prompt: str, sensitivity: str = "normal"):
        try:
            res = provider.complete(system=system, prompt=prompt, tier=tier, sensitivity=sensitivity)
        except (LLMUnavailable, LLMRefused) as e:
            tracing.record(db, getattr(e, "attempts", []), run_id=run.id, agent_id="gsus", purpose="answer")
            raise
        tracing.record(db, getattr(res, "attempts", []), run_id=run.id, agent_id="gsus", purpose="answer", fallback_result=res)
        return res
    return call


def _proposal_lines(prop: dict[str, Any], sv: bool) -> list[str]:
    p = prop["proposals"][0]
    spec, pv = p["spec"], p["preview"]
    tasks = "; ".join(spec["mission"]["primary"][:2])
    skills = ", ".join(k["name"] for k in spec["skills"][:5])
    dups = prop["duplicates"]
    if sv:
        out = ["Jag föreslår en ny medarbetare:", "", pv["display"], spec["purpose"], "", f"Huvuduppgift: {tasks}",
               f"Personlighet: {', '.join(spec['traits']) or '—'}", f"Avdelning: {(pv.get('department') or {}).get('name', '—')}",
               f"Möjliga kompetenser (förslag, inte verifierade): {skills or '—'}"]
        if dups:
            out += ["", "Befintliga agenter med liknande ansvar: " + "; ".join(
                f"{d['agent']['display']} ({d['score']:.2f} → {d['recommendation']})" for d in dups[:3])]
        out += ["", "Vill du granska och justera profilen innan registrering? Inget är skapat ännu."]
    else:
        out = ["I propose a new colleague:", "", pv["display"], spec["purpose"], "", f"Main task: {tasks}",
               f"Personality: {', '.join(spec['traits']) or '—'}", f"Department: {(pv.get('department') or {}).get('name', '—')}",
               f"Possible skills (suggestions, not verified): {skills or '—'}"]
        if dups:
            out += ["", "Existing agents with similar responsibilities: " + "; ".join(
                f"{d['agent']['display']} ({d['score']:.2f} → {d['recommendation']})" for d in dups[:3])]
        out += ["", "Review and adjust the profile before registration? Nothing has been created yet."]
    if prop["method"] == "rules":
        out.append("(Assembled by deterministic rules — no language model was used.)" if not sv
                   else "(Sammanställt med deterministiska regler — ingen språkmodell användes.)")
    return out


def _lookup_lines(agents: list[dict[str, Any]], sv: bool) -> list[str]:
    if not agents:
        return ["Ingen i personalregistret matchar. Vill du att jag föreslår en ny agent?" if sv else
                "Nobody in the register matches. Shall I propose a new agent?"]
    head = "Det här är de som kan hjälpa till:" if sv else "These agents can help:"
    rows = []
    for c in agents:
        obs = c["observation"]
        state = {"observed": "observerad" if sv else "observed", "never_observed": "aldrig körd" if sv else "never run",
                 "offline": "offline", "suspended": "pausad" if sv else "suspended", "not_active": c["lifecycle"]}.get(obs["state"], obs["state"])
        rows.append(f"  • {c['display']} — {c['title']} ({c['department']['name'] if c['department'] else '—'}; {state}) — "
                    + "; ".join(c["match"]["why"][:2]))
    return [head, *rows]


def compose(db: Session, run: GsusRun, steps: list[GsusStep]) -> tuple[str, str]:
    mode = MODES.MODES[run.settings["mode"]]
    lines = [f"G-sus · {mode['title']} — objective: {run.objective}", ""]
    for s in steps:
        if s.kind == "synthesis":
            continue
        icon = {"completed": "✓", "blocked": "⊘", "failed": "✗", "cancelled": "–", "waiting_for_approval": "⧗"}.get(s.status, "·")
        lines.append(f"{icon} {s.title}: {s.summary}")
        if s.kind == "retrieval" and s.output.get("answer"):
            lines += ["", "RESEARCH (grounded in the Archive):", s.output["answer"], ""]
        if s.kind == "agent_proposal" and (s.output or {}).get("proposal"):
            lines += ["", *_proposal_lines(s.output["proposal"], _swedish(run.objective)), ""]
        if s.kind == "personnel_lookup":
            lines += ["", *_lookup_lines(s.output.get("agents") or [], _swedish(run.objective)), ""]
        council = (s.output or {}).get("council")
        if council:
            lines.append(f"   next experiment: {council['recommended_next_experiment']['type']}")
    if run.contradictions:
        lines += ["", "CONTRADICTIONS / TENSIONS:"] + [f"  ! {c['between']}: {c['detail']}" for c in run.contradictions]
    v = run.verification
    lines += ["", f"VERIFICATION: {len(v.get('completed', []))}/{v['steps']} steps completed"
              + (f"; blocked: {', '.join(v['blocked'])}" if v.get("blocked") else "") + (f"; failed: {', '.join(v['failed'])}" if v.get("failed") else "")]
    report = "\n".join(lines)
    method = "heuristic"
    if run.settings.get("use_llm") and mode["creative"]:
        llm = _llm_fn(db, run)
        if llm is None:
            report += "\n\nCREATIVE: not generated — no AI provider is configured (creative output is never faked)."
        else:
            facts = untrusted.wrap(json.dumps([{"step": s.title, "status": s.status, "summary": s.summary} for s in steps], ensure_ascii=False),
                                   "run-results", "results of this run")
            try:
                res = llm(MODES.system_prompt(run.settings) + " " + untrusted.GUARD,
                          f"Objective: {run.objective}\nWrite the final response. Put grounded findings first, then a section titled "
                          f"'CREATIVE (generated, not factual)' if you add any creative material.\n{facts}")
                report = res.text + "\n\n— Execution record —\n" + report
                method = "llm"
            except (LLMUnavailable, LLMRefused) as e:
                report += f"\n\nCREATIVE: not generated ({e})."
    return report, method
