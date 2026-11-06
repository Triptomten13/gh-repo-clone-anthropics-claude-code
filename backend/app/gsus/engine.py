"""G-sus — the head orchestrator.

objective → understand (intents + entity resolution) → clarify if needed → plan (steps
over *registered* capabilities only, with dependencies) → execute through the central
orchestrator (parallel where independent) → approval gates for high-impact actions →
collect & compare results → detect contradictions → verify → answer (grounded research
and labelled creative output kept apart).

G-sus never executes high-impact actions itself and never grants permissions: approval
gates record a human decision; the responsible module performs the action afterwards.
"""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents.catalog import build_orchestrator
from ..ai import tracing
from ..ai.llm import LLMRefused, LLMUnavailable, get_provider
from ..ai.providers import tokenize
from ..governance import core as gov
from ..knowledge import canon, search
from ..models import AgentMessage, Approval, CollaborationSession, Document, GsusRun, GsusStep, Product, Task
from ..security import untrusted
from . import modes as MODES

INTENTS: list[tuple[str, str]] = [
    ("approval_action", r"\b(launch|publish|buy|purchase|spend|place an order|send (an )?(email|message)|delete|lansera|publicera|köp|spendera|skicka|radera)\b"),
    ("product_evaluation", r"\b(evaluat\w*|analy[sz]\w*|assess\w*|scor\w*|economics|profitab\w*|margin|utvärdera|analysera|bedöm\w*|lönsam\w*)"),
    ("brand_creation", r"\b(brand\w*|concepts?|identit\w*|varumärke\w*|koncept\w*)"),
    ("council", r"\b(council|verdict|råd(et)?|rådslag)\b"),
    ("discussion", r"\b(discuss\w*|debate|diskutera\w*)"),
    ("think_sideways", r"(what else|sideways|unexpected|other markets|oväntade?|vad mer)"),
    ("campaign", r"\b(campaigns?|ads|advert\w*|kampanj\w*|annons\w*)"),
    ("market_scan", r"\b(trends?|market scan|scan the market|marknadsskanning|trender)\b"),
    ("canon_check", r"\b(canon|lore|contradictions?|archivum|kanon|motsägelse\w*)"),
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
    if not intents:
        intents = ["archive_question"] if db.query(Document).filter(Document.status == "ready").count() else []
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
    db.commit()
    if run.status != "needs_clarification":
        execute(db, run)
    return run


def _steps(db: Session, run: GsusRun) -> list[GsusStep]:
    return db.scalars(select(GsusStep).where(GsusStep.run_id == run.id).order_by(GsusStep.ordinal)).all()


def execute(db: Session, run: GsusRun) -> GsusRun:
    if gov.kill_switch_engaged(db):
        run.status, run.answer = "cancelled", "Emergency stop is engaged; nothing was executed."
        db.commit()
        return run
    orch = build_orchestrator()
    run.status = "running"
    steps = _steps(db, run)
    by_ord = {s.ordinal: s for s in steps}
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
    orch.drain(500)
    db.expire_all()
    # 2) collect task results
    for st in _steps(db, run):
        if st.kind == "task" and st.task_id and st.status == "running":
            t = db.get(Task, st.task_id)
            msg = db.scalars(select(AgentMessage).where(AgentMessage.task_id == t.id).order_by(AgentMessage.id.desc())).first()
            st.status = {"succeeded": "completed", "blocked": "blocked", "failed": "failed", "cancelled": "cancelled"}.get(t.status, st.status)
            st.summary = (msg.summary if msg else t.error or t.status)[:2000]
            st.output = _digest(db, st, t)
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
        elif st.kind == "approval_gate":
            deps = [by_ord[d] for d in st.depends_on]
            if any(d.status == "running" for d in deps):
                continue
            a = gov.request_approval(db, st.payload["action"], f"G-sus run #{run.id}: {run.objective[:120]}", "gsus",
                                     f"Requested by G-sus on behalf of {run.created_by}. Objective: {run.objective}", {"gsus_run": run.id, **st.payload})
            st.approval_id, st.status = a.id, "waiting_for_approval"
            st.summary = f"approval #{a.id} ({st.payload['action']}) pending — G-sus will not perform this action itself"
    db.commit()
    return _finish(db, run)


def resume(db: Session, run: GsusRun) -> GsusRun:
    for st in _steps(db, run):
        if st.status == "waiting_for_approval" and st.approval_id:
            a = db.get(Approval, st.approval_id)
            if a.status == "approved":
                st.status = "completed"
                st.summary = (f"approved by {a.decided_by}. The action is performed by its responsible module "
                              f"(e.g. Brand Portfolio activation, Campaign launch), never by G-sus.")
            elif a.status == "rejected":
                st.status, st.summary = "cancelled", f"rejected by {a.decided_by}: {a.decision_note}"
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
