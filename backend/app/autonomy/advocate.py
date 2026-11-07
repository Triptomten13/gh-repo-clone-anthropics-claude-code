"""THE DEVIL'S ADVOCATE — independent challenge of important decisions, including G-SUS's and the orchestrator's.

Built so that it cannot simply agree:
* The FIRST layer is model-independent: the 12-question protocol and rule packs per decision kind run on the decision
  record itself. No model — not the proposer, not the most powerful one — can talk these checks into agreeing.
* The optional SECOND layer asks a model from a DIFFERENT family than the proposer for the strongest counter-argument.
  Its findings count only with evidence AND an alternative; it can never block and never lift a rule finding.
* Only policy/security violations BLOCK (an unsafe file format, a licence that cannot be verified, a budget or approval
  requirement broken, agent credentials broader than least privilege). Everything else is a recommendation.
* "Sound" is a real outcome, and it lists what was checked. Manufactured objections are not the goal.
* A calibration set of known-bad and known-good decisions measures it, and the agreement rate over recent reviews is
  watched for rubber-stamping (almost always "sound") as well as obstruction (almost never "sound").

It asks for auditable decision explanations (objective, evidence, assumptions, alternatives, risks, verification) — never
for a model's hidden chain of thought.
"""
from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

# The mandatory questioning protocol → the decision-record field that answers it, and how bad a missing answer is.
PROTOCOL: list[tuple[str, str, str]] = [
    ("What are you trying to accomplish?", "objective", "important"),
    ("Why did you choose this action?", "summary", "important"),
    ("What evidence supports your decision?", "evidence", "important"),
    ("What alternatives did you consider?", "alternatives", "important"),
    ("Why did you reject those alternatives?", "alternatives", "optional"),
    ("What assumptions are you making?", "assumptions", "optional"),
    ("What could go wrong?", "risks", "important"),
    ("What are the security implications?", "permissions", "optional"),
    ("What are the resource implications?", "cost_usd", "optional"),
    ("Is this the simplest effective solution?", "alternatives", "optional"),
    ("What would make you change your mind?", "would_change_if", "optional"),
    ("How will we verify that the action worked?", "verification", "important"),
]
MODES = ["DEVILS_ADVOCATE", "RED_TEAM", "COST_CRITIC", "ARCHITECTURAL_CRITIC", "EVIDENCE_CRITIC", "CREATIVE_CRITIC",
         "SECURITY_CRITIC", "STRATEGIC_CRITIC", "CONTRARIAN", "INNOVATION"]
SAFE_FORMATS = {"gguf", "safetensors"}
BROAD_SCOPES = re.compile(r"(^|[:_.\-])(admin|owner|delete|write:org|admin:org|repo$|workflow|full|\*)($|[:_.\-])", re.I)


def _f(code: str, weakness: str, evidence: str, consequence: str, alternative: str, recommendation: str, severity: str,
       confidence: float = 0.9, blocking: bool = False, source: str = "rules") -> dict[str, Any]:
    return {"code": code, "weakness": weakness, "evidence": evidence, "consequence": consequence, "alternative": alternative,
            "recommendation": recommendation, "severity": severity, "confidence": round(confidence, 2), "blocking": blocking, "source": source}


def _missing(v: Any) -> bool:
    return v is None or v == "" or v == [] or v == {}


def protocol(d: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Unanswered protocol questions become findings; answered ones are recorded as checked."""
    out, checked = [], []
    seen: set[str] = set()
    for q, field, sev in PROTOCOL:
        if field in seen:
            continue
        if _missing(d.get(field)) and not (field == "cost_usd" and d.get("cost_usd") == 0):
            seen.add(field)
            out.append(_f(f"protocol.{field}", f"unanswered: {q}", f"the decision record has no '{field}'",
                          "the decision cannot be audited or verified on this point", "state it in the decision record",
                          f"answer: {q}", sev, 0.95))
        else:
            checked.append(q)
    return out, checked


def _general(d: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    cost, budget = d.get("cost_usd"), d.get("budget_usd")
    if cost is not None and budget is not None and float(cost) > float(budget):
        out.append(_f("budget.exceeded", "the action costs more than its budget", f"cost ${float(cost):.2f} > budget ${float(budget):.2f}",
                      "a hard budget would be broken", "a cheaper model / fewer calls, or a larger budget approved by a person",
                      "do not run it under this budget", "critical", 1.0, blocking=True))
    if d.get("irreversible") and not d.get("approval_id"):
        out.append(_f("approval.irreversible", "an irreversible action without a human approval", "irreversible=true, approval_id missing",
                      "it cannot be undone if it is wrong", "file an approval; prefer a reversible variant", "stop until approved",
                      "critical", 1.0, blocking=True))
    if d.get("external") and not d.get("verification"):
        out.append(_f("external.unverified", "an external action without a way to check it worked", "external=true, no verification plan",
                      "a failure outside the system goes unnoticed", "state how the result will be checked", "add a verification step", "important"))
    return out


def _model_acquisition(d: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    fmt = (d.get("format") or "").lower()
    if fmt not in SAFE_FORMATS:
        out.append(_f("model.unsafe_format", f"model format '{fmt or 'unknown'}' can execute code on load", f"format={fmt or 'unknown'}",
                      "pickle-based weights or repository code can run arbitrary code on this machine",
                      "a GGUF or safetensors build of the same model", "do not download", "critical", 1.0, blocking=True))
    lic = (d.get("license") or "").lower()
    if not lic:
        out.append(_f("model.licence_unknown", "the licence is not stated", "no licence in the model card metadata",
                      "use may be unlawful", "a model with a stated licence", "do not download", "critical", 1.0, blocking=True))
    elif d.get("commercial_use") not in ("permitted",):
        out.append(_f("model.licence_review", f"licence '{lic}' is not a known permissive licence", f"commercial_use={d.get('commercial_use')}",
                      "commercial use may be restricted", "a permissively licensed alternative", "have a person read the licence first", "important"))
    if d.get("gated"):
        out.append(_f("model.gated", "the repository is gated", "gated=true", "needs the owner's account and licence acceptance",
                      "an ungated mirror from the original publisher", "ask the owner", "important"))
    fit = d.get("fit_verdict")
    if fit == "does_not_fit":
        out.append(_f("model.does_not_fit", "the model does not fit this machine", f"fit={fit}; needs {d.get('ram_needed_gb')} GB",
                      "it would fail to load or swap the machine to a halt", "a smaller quantization or a smaller model",
                      "do not download", "critical", 1.0, blocking=True))
    elif fit == "tight":
        out.append(_f("model.tight", "the model barely fits", f"fit={fit}", "other models and the app compete for memory",
                      "a smaller quantization", "test with nothing else loaded", "important", 0.8))
    if d.get("safety_modified"):
        out.append(_f("model.safety_removed", "the weights were modified to remove safety training", f"tags: {', '.join(d.get('safety_tags', []))}",
                      "outputs bypass the publisher's safeguards", "the original publisher's model", "reject", "critical", 0.9))
    if not d.get("measured"):
        out.append(_f("evidence.not_measured", "the case for this model rests on popularity or public leaderboards, not on our tasks",
                      f"evidence: {', '.join(d.get('evidence') or ['none'])[:200]}",
                      "a model can rank high elsewhere and lose on Swedish, rhyme or our code", "run it in the Model Championship against the installed models",
                      "decide on the championship result", "important", 0.9))
    pb, best = d.get("parameters_b"), d.get("incumbent_parameters_b")
    if pb and best and pb > 2 * best and not d.get("measured"):
        out.append(_f("model.bigger_not_better", "a much larger model is assumed to be better", f"{pb} B vs incumbent {best} B",
                      "slower and more memory for possibly no gain on our tasks", "measure first", "compare in the championship", "optional", 0.7))
    return out


def _account_request(d: dict[str, Any]) -> list[dict[str, Any]]:
    from .accounts import JUSTIFICATION_KEYS

    out = []
    j = d.get("justification") or {}
    missing = [k for k in JUSTIFICATION_KEYS if _missing(j.get(k))]
    if missing:
        out.append(_f("account.justification", "the account request does not answer all ten questions", f"missing: {', '.join(missing)}",
                      "an account may be created that is not needed or not allowed", "complete the justification",
                      "answer the missing points", "important", 0.95))
    broad = [s for s in d.get("scopes") or [] if BROAD_SCOPES.search(s)]
    if broad and str(d.get("proposer", "")).startswith("agent:"):
        out.append(_f("account.broad_scope", "an agent asks for broad permissions", f"scopes: {', '.join(broad)}",
                      "a mistake or a prompt injection could act with owner rights", "read-only or repository-scoped tokens",
                      "least privilege: narrow the scopes", "critical", 1.0, blocking=True))
    if d.get("paid") and not d.get("approval_id"):
        out.append(_f("account.paid", "a paid service without a human approval", "paid=true", "a financial commitment",
                      "the free tier, or an approval", "file an approval", "critical", 1.0, blocking=True))
    if d.get("existing_account"):
        out.append(_f("account.duplicate", "an account for this service already exists", f"existing: {d.get('existing_account')}",
                      "duplicate identities; platforms may treat it as evasion", "use the existing account", "reuse it", "important", 0.9))
    return out


def _plan(d: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    steps = d.get("steps") or []
    for s in steps:
        if int(s.get("level", 0)) >= 4 and not s.get("approval_id"):
            out.append(_f("plan.unapproved_step", f"step '{s.get('action')}' is level {s.get('level')} without approval",
                          json.dumps(s)[:200], "an external or financial action would run without a person", "keep the step as a request for approval",
                          "the step must wait for approval", "critical", 1.0, blocking=True))
    if len(steps) > 6 and len((d.get("objective") or "").split()) < 12:
        out.append(_f("plan.complexity", "many steps for a short objective", f"{len(steps)} steps", "more cost and more failure points",
                      "a shorter plan", "remove steps that do not serve the objective", "optional", 0.6))
    return out


def _model_selection(d: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    if not d.get("measured"):
        out.append(_f("selection.unmeasured", "the chosen model has no measured profile for this task", f"model {d.get('model')}",
                      "it may be worse than an alternative already installed", "a measured model", "benchmark it", "important", 0.85))
    cheaper = d.get("cheaper_alternative")
    if cheaper and abs(float(cheaper.get("quality_gap", 1))) <= 0.05:
        out.append(_f("cost.cheaper_equivalent", "a cheaper model is about as good", f"{cheaper.get('model')} is within {cheaper.get('quality_gap')} quality",
                      "money or time spent for no measurable gain", cheaper.get("model", ""), "use the cheaper model", "important", 0.8))
    return out


PACKS = {"model_acquisition": _model_acquisition, "account_request": _account_request, "plan": _plan, "model_selection": _model_selection}


def _family(model_id: str) -> str:
    m = (model_id or "").split(":")[-1].lower()
    return re.split(r"[-_.\d]", m, maxsplit=1)[0] or m


def _model_review(db: Session, d: dict[str, Any], mode: str, router: Any | None) -> tuple[list[dict[str, Any]], str, str]:
    """Ask a model from a DIFFERENT family than the proposer for the strongest counter-argument. Findings without evidence
    or an alternative are dropped; a model can raise concerns, never block."""
    from ..creative import providers as P
    from ..security.untrusted import wrap

    proposer_family = _family(d.get("proposer_model", ""))
    cands = [c for c in P.available_models(db) if c.locality == "local" and "text" in c.capabilities and _family(c.id) != proposer_family]
    if not cands:
        return [], "", "no independent model available (every installed model is from the proposer's family)"
    prof = P.profiles(db, [c.id for c in cands])
    cands.sort(key=lambda c: -(prof.get(c.id, {}).get("overall", {}).get("score") or 0))
    reviewer = cands[0].id
    record = {k: d.get(k) for k in ("kind", "summary", "objective", "evidence", "assumptions", "alternatives", "risks", "verification", "cost_usd")}
    prompt = (f"You are the Devil's Advocate ({mode}). Construct the strongest REASONABLE argument against this decision. "
              "Do not agree by default and do not invent problems: if it is sound, return an empty list. Each finding needs "
              "concrete evidence from the record and a better alternative. Reply with JSON only: "
              '{"findings": [{"weakness": "...", "evidence": "...", "consequence": "...", "alternative": "...", "severity": "important|optional"}]}\n\n'
              + wrap(json.dumps(record, ensure_ascii=False)[:4000], source_id="decision-record", title="decision under review"))
    try:
        r = P.call_model(db, reviewer, system="You are an independent critic. Reply with JSON only.", prompt=prompt, max_tokens=500,
                         agent_id="devils_advocate", workflow="advocate.review", purpose="advocate.review", router=router)
    except Exception as e:  # noqa: BLE001 — an unavailable reviewer is reported, never replaced by an invented opinion
        return [], reviewer, f"model review failed: {str(e)[:120]}"
    m = re.search(r"\{.*\}", r.get("text") or "", re.S)
    out = []
    try:
        raw = (json.loads(m.group(0)) if m else {}).get("findings") or []
    except json.JSONDecodeError:
        raw = []
    for x in raw[:6]:
        if not isinstance(x, dict) or not str(x.get("evidence", "")).strip() or not str(x.get("alternative", "")).strip():
            continue
        sev = "important" if x.get("severity") == "important" else "optional"
        out.append(_f("model.counter_argument", str(x.get("weakness", ""))[:300], str(x["evidence"])[:300], str(x.get("consequence", ""))[:300],
                      str(x["alternative"])[:300], "consider the alternative", sev, 0.5, blocking=False, source=reviewer))
    return out, reviewer, ""


def review(db: Session | None, decision: dict[str, Any], *, mode: str = "DEVILS_ADVOCATE", use_model: bool = False, router: Any | None = None,
           actor: str = "devils_advocate", store: bool = True) -> Any:
    """Review one decision record. Returns the stored Critique (or a dict when store=False — calibration)."""
    from ..models import Critique

    if mode not in MODES:
        raise ValueError(f"unknown mode {mode}")
    findings, checked = protocol(decision)
    findings += _general(decision)
    pack = PACKS.get(decision.get("kind", ""))
    if pack:
        findings += pack(decision)
        checked.append(f"{decision['kind']} rules")
    reviewer, note = "rules", ""
    if use_model and db is not None:
        extra, who, note = _model_review(db, decision, mode, router)
        findings += extra
        if who:
            reviewer = f"rules+{who}"
    blocking = any(f["blocking"] for f in findings)
    serious = [f for f in findings if f["severity"] in ("critical", "important")]
    verdict = "block" if blocking else "concerns" if serious else "sound"
    summary = ("Blocked: " + "; ".join(f["weakness"] for f in findings if f["blocking"]) if blocking else
               f"{len(serious)} concern(s): " + "; ".join(f["weakness"] for f in serious[:3]) if serious else
               f"Sound — {len(checked)} checks passed, no significant problem found.")
    if note:
        summary += f" ({note})"
    out = {"subject_kind": decision.get("kind", "decision"), "subject_ref": str(decision.get("ref", ""))[:96], "summary": summary[:2000],
           "mode": mode, "verdict": verdict, "findings": findings, "checks": checked, "reviewer": reviewer,
           "proposer": str(decision.get("proposer", ""))[:160], "independent": True, "status": "escalated" if blocking else "open", "created_by": actor}
    if not store or db is None:
        return out
    c = Critique(**out)
    db.add(c)
    db.flush()
    from ..governance import core as gov

    gov.audit(db, actor, "advocate.review", f"{out['subject_kind']}:{out['subject_ref']}", verdict=verdict, critique=c.id,
              blocking=[f["code"] for f in findings if f["blocking"]])
    return c


# ---------------------------------------------------------------- calibration and agreement monitoring
def _good_acq() -> dict[str, Any]:
    return {"kind": "model_acquisition", "ref": "cal-good", "summary": "acquire a small Swedish-capable model", "objective": "better Swedish lyrics at the same speed",
            "evidence": ["championship: songwriting 0.71 vs incumbent 0.66 on our dataset"], "alternatives": ["keep the incumbent: 0.05 lower"],
            "assumptions": ["the dataset reflects real briefs"], "risks": ["slightly more RAM"], "verification": "next championship",
            "would_change_if": "the gain disappears in the next championship", "permissions": ["models.acquire"], "cost_usd": 0,
            "format": "gguf", "license": "apache-2.0", "commercial_use": "permitted", "fit_verdict": "fits", "measured": True, "parameters_b": 1.7}


CALIBRATION: list[tuple[str, dict[str, Any], str]] = [
    ("good: measured, permissive, fits", _good_acq(), "sound"),
    ("bad: 70B on a 16 GB CPU machine", {**_good_acq(), "ref": "cal-70b", "fit_verdict": "does_not_fit", "parameters_b": 70, "ram_needed_gb": 44}, "block"),
    ("bad: pickle weights", {**_good_acq(), "ref": "cal-pickle", "format": "pytorch_model.bin"}, "block"),
    ("bad: chosen from a leaderboard", {**_good_acq(), "ref": "cal-board", "measured": False, "evidence": ["#1 on a public leaderboard"]}, "concerns"),
    ("bad: safety training removed", {**_good_acq(), "ref": "cal-abl", "safety_modified": True, "safety_tags": ["abliterated"]}, "concerns"),
    ("bad: no evidence, no verification", {**_good_acq(), "ref": "cal-empty", "evidence": [], "verification": ""}, "concerns"),
    ("bad: agent wants an admin token", {"kind": "account_request", "ref": "cal-admin", "summary": "GitHub for the agents", "objective": "open pull requests",
                                          "evidence": ["needed for the development division"], "alternatives": ["a GitHub App"], "risks": ["token misuse"],
                                          "verification": "health check", "scopes": ["admin:org", "delete_repo"], "proposer": "agent:model_hunter",
                                          "justification": {k: "answered" for k in ("service", "usefulness", "existing", "capabilities", "terms", "ownership",
                                                                                     "permissions", "costs", "alternative_integration", "decision")}}, "block"),
    ("good: read-only Hugging Face token", {"kind": "account_request", "ref": "cal-hf", "summary": "Hugging Face read token for model search",
                                            "objective": "higher API rate limits for the Model Hunter", "evidence": ["anonymous search is rate limited"],
                                            "alternatives": ["anonymous access: works, slower"], "risks": ["token leak — read-only"], "verification": "whoami health check",
                                            "would_change_if": "anonymous limits suffice", "assumptions": ["free tier"], "permissions": ["read-repos"], "cost_usd": 0,
                                            "scopes": ["read-repos"], "proposer": "agent:model_hunter",
                                            "justification": {k: "answered" for k in ("service", "usefulness", "existing", "capabilities", "terms", "ownership",
                                                                                       "permissions", "costs", "alternative_integration", "decision")}}, "sound"),
    ("bad: over budget", {**_good_acq(), "ref": "cal-budget", "cost_usd": 12.0, "budget_usd": 2.0}, "block"),
]


def calibrate() -> dict[str, Any]:
    """Run the rule layer on the known cases. A critic that passes bad decisions or flags good ones is visible here."""
    rows = []
    for name, d, expected in CALIBRATION:
        got = review(None, d, store=False)["verdict"]
        rows.append({"case": name, "expected": expected, "got": got, "ok": got == expected})
    bad = [r for r in rows if r["expected"] != "sound"]
    good = [r for r in rows if r["expected"] == "sound"]
    return {"cases": rows, "correct": sum(r["ok"] for r in rows), "total": len(rows),
            "bad_flagged": sum(1 for r in bad if r["got"] != "sound"), "bad_total": len(bad),
            "good_passed": sum(1 for r in good if r["got"] == "sound"), "good_total": len(good)}


def agreement(db: Session, n: int = 50) -> dict[str, Any]:
    """How often the advocate has agreed recently. Always agreeing is a rubber stamp; never agreeing is obstruction."""
    from ..models import Critique

    rows = db.scalars(select(Critique).order_by(Critique.id.desc()).limit(n)).all()
    if not rows:
        return {"reviews": 0, "sound_share": None, "warning": ""}
    sound = sum(1 for c in rows if c.verdict == "sound") / len(rows)
    warn = ""
    if len(rows) >= 20 and sound > 0.9:
        warn = "rubber-stamp risk: more than 90 % of recent reviews found nothing — check the decision records and the rules"
    elif len(rows) >= 20 and sound < 0.1:
        warn = "obstruction risk: fewer than 10 % of recent reviews found a decision sound"
    return {"reviews": len(rows), "sound_share": round(sound, 3), "by_verdict": {v: sum(1 for c in rows if c.verdict == v) for v in ("sound", "concerns", "block")},
            "warning": warn}
