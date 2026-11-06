"""CREATIVE TOURNAMENT MODE — DAEMON CREATIVE COLLABORATION + SYNTHESIS ENGINE.

A brief goes to several models; each writes its own version; critics (other models, never judging their own work)
score them together with deterministic checks; a synthesis model combines the strongest lines, structures and ideas
into ONE new version (a paste-up of candidates, or a synthesis that scores worse than the best candidate, is rejected);
targeted revisions fix only what the critics named. Every tournament has a HARD budget and explicit STOP CONDITIONS:

  quality target reached · budget (calls / tokens / USD) would be exceeded · time limit · diminishing returns
  (a round improves the score by less than `min_gain`) · rounds exhausted · no model available

Caps keep a tournament from becoming 27 models debating one line: at most 6 contestants, 3 critics, 4 revision rounds,
40 model calls. Paid spending above CREATIVE_AUTONOMOUS_USD needs a human approval (policy engine); local and verified
free models run autonomously. Every call is policy-checked per model, budget-reserved, traced, and stored with provenance.

Strategies: AUTOMATIC (decides from task complexity and budget) · SINGLE · COMPARISON (candidates + critics, best wins)
· TOURNAMENT (candidates + critics + synthesis + refinement) · ITERATIVE (one model, critic, revisions).
"""
from __future__ import annotations

import hashlib
import os
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import providers as P
from . import quality as Q

STRATEGIES = ["AUTOMATIC", "SINGLE", "COMPARISON", "TOURNAMENT", "ITERATIVE"]
HARD = {"max_models": 6, "critics": 3, "max_rounds": 4, "max_calls": 40, "max_seconds": 3600, "max_tokens": 200_000}
LABELS = "ABCDEF"


def autonomous_usd() -> float:
    return float(os.getenv("CREATIVE_AUTONOMOUS_USD", "0.50"))


@dataclass
class Budget:
    max_calls: int = 8
    max_tokens: int = 20_000
    max_usd: float = 0.0  # 0 = local / verified-free models only
    max_seconds: int = 900
    max_rounds: int = 1   # revision rounds after the first round
    max_models: int = 3   # contestants
    critics: int = 2

    @classmethod
    def of(cls, d: dict[str, Any] | None) -> Budget:
        b = cls(**{k: v for k, v in (d or {}).items() if k in cls.__dataclass_fields__})
        b.max_models = max(1, min(int(b.max_models), HARD["max_models"]))
        b.critics = max(0, min(int(b.critics), HARD["critics"]))
        b.max_rounds = max(0, min(int(b.max_rounds), HARD["max_rounds"]))
        b.max_calls = max(1, min(int(b.max_calls), HARD["max_calls"]))
        b.max_seconds = max(10, min(int(b.max_seconds), HARD["max_seconds"]))
        b.max_tokens = max(500, min(int(b.max_tokens), HARD["max_tokens"]))
        b.max_usd = max(0.0, float(b.max_usd))
        return b


class Meter:
    """What the tournament has used — checked BEFORE every call; a call that would cross a limit is not made."""

    def __init__(self, b: Budget) -> None:
        self.b, self.calls, self.tokens, self.usd, self.t0 = b, 0, 0, 0.0, time.monotonic()
        self.tokens_in = self.tokens_out = 0

    def seconds(self) -> float:
        return time.monotonic() - self.t0

    def refuse(self, est_tokens: int, est_usd: float, reserve_calls: int = 0) -> str | None:
        if self.calls + 1 + reserve_calls > self.b.max_calls:
            return f"call budget ({self.b.max_calls})"
        if self.tokens + est_tokens > self.b.max_tokens:
            return f"token budget ({self.b.max_tokens})"
        if self.usd + est_usd > self.b.max_usd + 1e-9 and est_usd > 0:
            return f"USD budget (${self.b.max_usd:.2f})"
        if self.seconds() > self.b.max_seconds:
            return f"time limit ({self.b.max_seconds} s)"
        return None

    def add(self, r: dict[str, Any]) -> None:
        self.calls += 1
        self.tokens_in += int(r.get("input_tokens", 0))
        self.tokens_out += int(r.get("output_tokens", 0))
        self.tokens += int(r.get("input_tokens", 0)) + int(r.get("output_tokens", 0))
        self.usd += float(r.get("cost_usd", 0.0))

    def as_dict(self) -> dict[str, Any]:
        return {"calls": self.calls, "tokens": self.tokens, "usd": round(self.usd, 6), "seconds": round(self.seconds(), 1)}


def _hash(*parts: Any) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


def _system(category: str, language: str) -> str:
    lang = "Swedish" if language == "sv" else "English"
    return (f"You are a {('songwriter' if category == 'songwriting' else 'poet' if category == 'poetry' else 'writer and expert')} "
            f"working for Demonkoncernen AB. Write in {lang}. Be original: avoid clichés, filler and generic AI phrasing. "
            "Output only the work itself — no preamble, no explanation.")


def _strategy(task: dict[str, Any], requested: str, b: Budget) -> tuple[str, int, str]:
    """(strategy, contestants, why) — AUTOMATIC uses one model unless the task is creative/complex AND the budget can pay
    for candidates + critics + synthesis. More models are never used just because they exist."""
    if requested != "AUTOMATIC":
        n = 1 if requested in ("SINGLE", "ITERATIVE") else max(2, b.max_models)
        return requested, n, f"{requested} requested"
    creative = task["category"] in P.CREATIVE
    if task["complexity"] == "low" and not creative:
        return "SINGLE", 1, "simple task: one model is enough"
    want = 4 if task["complexity"] == "high" else 3
    n = min(b.max_models, want)
    while n > 1 and n + min(b.critics, 1) + 1 > b.max_calls:
        n -= 1
    if n <= 1:
        return ("ITERATIVE" if b.max_calls >= 2 else "SINGLE"), 1, f"budget of {b.max_calls} call(s) allows one model"
    return "TOURNAMENT", n, f"{task['category']} task of {task['complexity']} complexity: {n} contestants + critics + synthesis"


def _visible_cached(db: Session, key: str, actor: str, target: float) -> Any:
    from ..models import CreativeTournament

    since = datetime.now(UTC) - timedelta(days=30)
    for t in db.scalars(select(CreativeTournament).where(CreativeTournament.cache_key == key, CreativeTournament.status == "completed",
                                                          CreativeTournament.created_at >= since).order_by(CreativeTournament.id.desc())):
        if (t.final_score or 0) >= target and t.result_entry_id and (t.created_by == actor or t.classification in ("PUBLIC", "INTERNAL")):
            return t
    return None


def run(db: Session, brief: str, *, user: Any | None = None, agent_id: str | None = None, workflow: str = "creative.tournament",
        mode: str = "FREE_FIRST", strategy: str = "AUTOMATIC", category: str | None = None, quality_target: float = 0.75,
        budget: dict[str, Any] | None = None, allow_parallel: bool = True, classification: str = "INTERNAL", min_gain: float = 0.02,
        use_cache: bool = True, approval_id: int | None = None, alternatives: bool = True, router: Any | None = None) -> Any:
    """Run one Creative Tournament end to end (prepare + execute). Returns the CreativeTournament row (status completed /
    stopped / failed / pending_approval). Raises PolicyDenied when the policy refuses outright."""
    t = prepare(db, brief, user=user, agent_id=agent_id, workflow=workflow, mode=mode, strategy=strategy, category=category,
                quality_target=quality_target, budget=budget, classification=classification, use_cache=use_cache,
                approval_id=approval_id, router=router)
    if t.status == "ready":
        execute(db, t, user=user, agent_id=agent_id, allow_parallel=allow_parallel, min_gain=min_gain, alternatives=alternatives,
                router=router)
    return t


def prepare(db: Session, brief: str, *, user: Any | None = None, agent_id: str | None = None, workflow: str = "creative.tournament",
            mode: str = "FREE_FIRST", strategy: str = "AUTOMATIC", category: str | None = None, quality_target: float = 0.75,
            budget: dict[str, Any] | None = None, classification: str = "INTERNAL", use_cache: bool = True,
            approval_id: int | None = None, router: Any | None = None) -> Any:
    """The fast, synchronous part: validation, policy, cache, model choice and plan. Returns the row with status
    'ready' (call execute), or a final state (pending_approval / completed from cache)."""
    from ..governance import core as gov
    from ..governance.policy import ApprovalRequired, Request, enforce
    from ..knowledge.vault import sensitivity_for
    from ..models import CreativeEntry, CreativeTournament

    strategy = (strategy or "AUTOMATIC").upper()
    if strategy not in STRATEGIES:
        raise ValueError(f"strategy must be one of {STRATEGIES}")
    mode = (mode or "FREE_FIRST").upper().replace("-", "_")
    if mode not in P.MODES:
        raise ValueError(f"routing mode must be one of {P.MODES}")
    b = Budget.of(budget)
    quality_target = max(0.0, min(1.0, float(quality_target)))
    actor = getattr(user, "email", None) or (f"agent:{agent_id}" if agent_id else "system")
    task = P.analyze(brief)
    if category:
        task["category"] = category
    sensitivity = sensitivity_for(classification)
    key = _hash(brief.strip().lower(), task["category"], mode, strategy, quality_target, b.max_usd > 0)

    def new_row() -> Any:
        row = CreativeTournament(created_by=actor, agent_id=agent_id or "", workflow=workflow, brief=brief[:20_000], category=task["category"],
                                 language=task["language"], routing_mode=mode, strategy=strategy, quality_target=quality_target,
                                 budget=asdict(b), usage={}, plan={}, classification=classification, cache_key=key)
        db.add(row)
        db.flush()
        return row

    # policy first: autonomous within limits; paid spending above the autonomous limit needs a human approval.
    # A plain refusal (PolicyDenied) propagates before anything is created.
    action = "creative.tournament.paid" if b.max_usd > autonomous_usd() else "creative.tournament"
    try:
        enforce(db, Request(action=action, agent_id=agent_id, user_email=getattr(user, "email", None), user_role=getattr(user, "role", None),
                            workflow=workflow, classification=classification, approval_id=approval_id,
                            payload={"brief_sha": _hash(brief), "max_usd": b.max_usd, "mode": mode}),
                request_approval_title=f"Creative tournament with up to ${b.max_usd:.2f} paid model spend")
    except ApprovalRequired as e:
        t = new_row()
        t.status, t.approval_id = "pending_approval", e.decision.approval_id
        t.stop_reason = f"paid budget ${b.max_usd:.2f} is above the autonomous limit ${autonomous_usd():.2f} — waiting for approval"
        db.commit()
        return t

    cached = _visible_cached(db, key, actor, quality_target) if use_cache else None
    t = new_row()
    if cached is not None:
        src = db.get(CreativeEntry, cached.result_entry_id)
        e = CreativeEntry(tournament_id=t.id, role="cached", model_id=src.model_id, provider=src.provider, model_version=src.model_version,
                          text=src.text, deterministic=src.deterministic, critiques=src.critiques, score=src.score, sources=[src.id],
                          accepted=True)
        db.add(e)
        db.flush()
        t.status, t.result_entry_id, t.final_score = "completed", e.id, cached.final_score
        t.usage = {"calls": 0, "tokens": 0, "usd": 0.0, "seconds": 0.0, "cache_hit": cached.id}
        t.stop_reason = f"reused the result of tournament #{cached.id} (same brief and settings, score {cached.final_score:.2f}) — no model called"
        t.finished_at = datetime.now(UTC)
        gov.audit(db, actor, "creative.tournament.cached", f"creative:{t.id}", source=cached.id)
        db.commit()
        return t

    strat, n, why = _strategy(task, strategy, b)
    allowed = None if b.max_usd > 0 else ["local", "free_tier", "open_endpoint"]
    choice = P.choose_models(db, brief, mode="CREATIVE_ENSEMBLE" if (strat in ("TOURNAMENT", "COMPARISON") and mode == "FREE_FIRST")
                             else mode, n=n, sensitivity=sensitivity, category=task["category"], allowed_cost_classes=allowed, router=router)
    ranked = choice["ranked"]
    contestants = [r["model"] for r in ranked[:n]]
    critic_pool = [r["model"] for r in sorted(ranked, key=lambda r: r["quality"], reverse=True) if r["model"] not in contestants]
    critics = (critic_pool + [m for m in sorted(contestants, key=lambda m: -next(r["quality"] for r in ranked if r["model"] == m))])[:b.critics]
    synthesizer = max(ranked, key=lambda r: r["quality"])["model"] if ranked else None
    t.strategy, t.status = strat, "ready"
    t.plan = {"why": why, "task": task, "contestants": contestants, "critics": critics, "synthesizer": synthesizer,
              "selection": choice["explanation"], "excluded": choice["excluded"][:20],
              "candidates_considered": [{k: r[k] for k in ("model", "score", "quality", "why")} for r in ranked[:8]],
              "ranked": [{"model": r["model"], "quality": r["quality"], "est_cost_usd": r["est_cost_usd"],
                          "candidate": {k: r["candidate"][k] for k in ("version", "locality", "family", "cost_class")}} for r in ranked]}
    db.commit()
    return t


def execute(db: Session, t: Any, *, user: Any | None = None, agent_id: str | None = None, allow_parallel: bool = True,
            min_gain: float = 0.02, alternatives: bool = True, router: Any | None = None) -> Any:
    """The model calls: candidates, critics, synthesis, refinement — under the budget and stop conditions in `t`."""
    from ..governance import core as gov
    from ..governance import observability as obs
    from ..knowledge.vault import sensitivity_for
    from ..models import CreativeEntry

    brief, task, b, mode, strat = t.brief, t.plan["task"], Budget.of(t.budget), t.routing_mode, t.strategy
    quality_target, sensitivity, actor, workflow = t.quality_target, sensitivity_for(t.classification), t.created_by, t.workflow
    ranked, contestants, critics, synthesizer = t.plan["ranked"], t.plan["contestants"], t.plan["critics"], t.plan["synthesizer"]
    t.status = "running"
    db.commit()
    trace = obs.start("creative", f"creative:{t.id}", workflow=workflow, agent_id=agent_id or "", user_email=getattr(user, "email", "") or "",
                      parent_id=obs.current_run.get(), input={"brief": brief[:2000], "strategy": strat, "mode": mode, "budget": asdict(b)})
    t.trace_run_id = trace
    token = obs.current_run.set(trace)
    m = Meter(b)
    stop = ""
    try:
        obs.event("plan", strat, t.plan)
        gov.audit(db, actor, "creative.tournament", f"creative:{t.id}", strategy=strat, mode=mode, contestants=contestants, budget=asdict(b))
        db.commit()
        if not contestants:
            stop = "no permitted model can do this task here: " + "; ".join(f"{x['model']}: {x['why']}" for x in t.plan["excluded"][:4])
            t.status = "failed"
            return t
        system = _system(task["category"], task["language"])
        max_tok = task["max_tokens"]
        reserve = (1 if critics else 0) + (1 if strat == "TOURNAMENT" else 0)  # keep room for judging and synthesis

        info = {r["model"]: r for r in ranked}

        def est(model_id: str, prompt: str, out_tokens: int = max_tok) -> tuple[int, float]:
            c = info.get(model_id)
            tok = len(system + prompt) // 3 + out_tokens
            usd = (c["est_cost_usd"] if c else 0.0)
            return tok, usd

        def call(model_id: str, prompt: str, role: str, session: Session) -> Any:
            try:
                return P.call_model(session, model_id, system=system, prompt=prompt, max_tokens=max_tok, sensitivity=sensitivity,
                                    user_email=getattr(user, "email", None), agent_id=agent_id, workflow=workflow, purpose=f"creative.{role}",
                                    router=router)
            except Exception as ex:  # noqa: BLE001 — a failing model is recorded and replaced, never hidden
                return ex

        def record(model_id: str, prompt: str, role: str, round_: int, res: Any, sources: list[int] | None = None) -> Any:
            e = CreativeEntry(tournament_id=t.id, round=round_, role=role, model_id=model_id, provider=model_id.split(":", 1)[0],
                              model_version=info.get(model_id, {}).get("candidate", {}).get("version", ""),
                              prompt_hash=_hash(system, prompt)[:32], sources=sources or [])
            if isinstance(res, Exception):
                e.status, e.error = "failed", f"{type(res).__name__}: {str(res)[:300]}"
            else:
                m.add(res)
                det = Q.deterministic(res["text"], brief, task["category"])
                e.text, e.deterministic = det.pop("cleaned"), det
                e.input_tokens, e.output_tokens, e.cost_usd, e.latency_ms = res["input_tokens"], res["output_tokens"], res["cost_usd"], res["latency_ms"]
                e.score = det["score"]
                if not e.text.strip():
                    e.status, e.error = "failed", "empty output"
            db.add(e)
            db.flush()
            obs.event(role, model_id, {"entry": e.id, "status": e.status, "score": e.score, "error": e.error[:200],
                                       "tokens": e.input_tokens + e.output_tokens, "cost_usd": e.cost_usd}, duration_ms=e.latency_ms)
            db.commit()
            return e

        def gen(model_id: str, prompt: str, role: str, round_: int, sources: list[int] | None = None) -> Any:
            tok, usd = est(model_id, prompt)
            why_not = m.refuse(tok, usd, reserve if role == "candidate" else 0)
            if why_not:
                return why_not
            return record(model_id, prompt, role, round_, call(model_id, prompt, role, db), sources)

        # ---- round 1: candidates (failed providers are replaced by the next permitted model)
        brief_prompt = f"BRIEF (from Demonkoncernen):\n{brief}"
        entries: list[Any] = []
        queue = list(contestants)
        spare = [r["model"] for r in ranked if r["model"] not in contestants]
        remote = [mid for mid in queue if info[mid]["candidate"]["locality"] != "local"]
        if allow_parallel and len(remote) >= 2:
            # remote providers answer in parallel (each call in its own DB session); local models share this machine's
            # CPU, so they run one after another — running them together would only slow every one of them down
            from concurrent.futures import ThreadPoolExecutor

            from ..db import SessionLocal

            batch, pend_tok, pend_usd = [], 0, 0.0
            for mid in remote:
                tok, usd = est(mid, brief_prompt)
                if m.refuse(pend_tok + tok, pend_usd + usd, reserve + len(batch)):
                    break
                batch.append(mid)
                pend_tok, pend_usd = pend_tok + tok, pend_usd + usd

            def one(mid: str) -> Any:
                s_ = SessionLocal()
                try:
                    return call(mid, brief_prompt, "candidate", s_)
                finally:
                    s_.close()

            with ThreadPoolExecutor(max_workers=len(batch) or 1) as pool:
                results = list(pool.map(one, batch))
            for mid, res in zip(batch, results, strict=True):
                queue.remove(mid)
                e = record(mid, brief_prompt, "candidate", 1, res)
                entries.append(e)
                if e.status != "ok" and spare:
                    queue.append(spare.pop(0))
            t.plan = {**t.plan, "parallel": batch}
        else:
            t.plan = {**t.plan, "parallel": [], "parallel_why": "local models share this machine's CPU" if not remote else "parallel not allowed"}
        while queue:
            mid = queue.pop(0)
            res = gen(mid, brief_prompt, "candidate", 1)
            if isinstance(res, str):
                stop = f"stopped before {mid}: {res} would be exceeded"
                break
            if res.status != "ok":
                if spare:
                    nxt = spare.pop(0)
                    queue.insert(0, nxt)
                    obs.event("fallback", f"{mid} → {nxt}", {"failed": mid, "error": res.error[:200], "replacement": nxt})
                    t.plan = {**t.plan, "fallbacks": [*t.plan.get("fallbacks", []), {"from": mid, "to": nxt, "error": res.error[:200]}]}
                continue
            entries.append(res)
        ok = [e for e in entries if e.status == "ok"]
        if not ok:
            stop = stop or "every contestant failed — see the entries"
            t.status = "failed"
            return t

        # ---- critics: each reviews all candidates in ONE call; never scores its own candidate
        def judge(items: list[Any]) -> None:
            if not critics or not items:
                return
            labelled = [(LABELS[i], x.text) for i, x in enumerate(items[:len(LABELS)])]
            sys_c, prompt_c = Q.critic_prompt(brief, task["category"], labelled)
            for cm in critics:
                if m.refuse(*est(cm, prompt_c, 700)):
                    obs.event("critique_skipped", cm, {"why": "budget"})
                    continue
                try:
                    r = P.call_model(db, cm, system=sys_c, prompt=prompt_c, max_tokens=700, sensitivity=sensitivity,
                                     user_email=getattr(user, "email", None), agent_id=agent_id, workflow=workflow, purpose="creative.critique",
                                     router=router)
                    m.add(r)
                    parsed = Q.parse_critique(r["text"], [lab for lab, _ in labelled], dict(labelled), task["category"])
                except Exception as ex:  # noqa: BLE001
                    obs.event("critique_failed", cm, {"error": str(ex)[:200]})
                    continue
                for i, x in enumerate(items[:len(LABELS)]):
                    c = parsed.get(LABELS[i])
                    if c and x.model_id != cm:  # a critic never grades its own work
                        x.critiques = [*(x.critiques or []), {"critic": cm, "independent": True, **c}]
                obs.event("critique", cm, {"parsed": sorted(parsed), "entries": [x.id for x in items]})
            for x in items:
                x.score = Q.combine(x.deterministic["score"], [c["score"] for c in (x.critiques or [])])
            db.commit()

        judge(ok)
        best = max(ok, key=lambda x: x.score or 0)
        first_best = best.score or 0
        if strat == "TOURNAMENT" and best.model_id != synthesizer:
            # evidence from THIS brief outranks a benchmark score: the author of the best candidate synthesizes and revises
            t.plan = {**t.plan, "synthesizer_planned": synthesizer, "synthesizer": best.model_id,
                      "synthesizer_why": f"{best.model_id} wrote the best candidate in round 1 ({best.score:.2f})"}
            synthesizer = best.model_id
            obs.event("synthesizer", synthesizer, {"why": t.plan["synthesizer_why"]})
        if (best.score or 0) >= quality_target and not stop:
            stop = f"quality target {quality_target:.2f} reached by {best.model_id} ({best.score:.2f})"

        # ---- synthesis: combine the strongest elements — never a paste-up, never worse than the best candidate
        if not stop and strat == "TOURNAMENT" and len(ok) >= 2 and synthesizer:
            top = sorted(ok, key=lambda x: x.score or 0, reverse=True)[:3]
            parts = []
            for i, x in enumerate(top):
                good = [q for c in (x.critiques or []) for q in c.get("best_lines", [])][:4]
                weak = [w for c in (x.critiques or []) for w in c.get("weaknesses", [])][:3] + x.deterministic.get("notes", [])[:2]
                parts.append(f"=== VERSION {LABELS[i]} (score {x.score:.2f}) ===\n{x.text[:2500]}\nStrongest: {good or 'not named'}\nWeak: {weak or 'none named'}")
            prompt_s = (f"BRIEF:\n{brief}\n\nSeveral writers answered the brief. Create ONE new, coherent version that keeps the strongest "
                        "lines, images and structure from them (reuse the best lines where they fit), fixes the named weaknesses and follows "
                        "the brief exactly. Do not list or label the versions, do not average them into something generic, keep what is "
                        "distinctive.\n\n" + "\n\n".join(parts))
            s = gen(synthesizer, prompt_s, "synthesis", 2, [x.id for x in top])
            if isinstance(s, str):
                stop = f"no synthesis: {s} would be exceeded"
            elif s.status == "ok":
                judge([s])
                if Q.is_concatenation(s.text, [x.text for x in top]):
                    s.status, s.error = "rejected", "concatenation of candidates, not a synthesis"
                elif (s.score or 0) < (best.score or 0):  # the result is never worse than something already in hand
                    s.status, s.error = "rejected", f"scored {s.score:.3f}, below the best candidate {best.score:.3f}"
                else:
                    best = s
                obs.event("synthesis_decision", s.status, {"entry": s.id, "score": s.score, "best": best.id, "reason": s.error})
                db.commit()
            if not stop and (best.score or 0) >= quality_target:
                stop = f"quality target {quality_target:.2f} reached ({best.score:.2f})"

        # ---- targeted refinement: fix only what was named; stop on diminishing returns
        rounds = 0
        while not stop and rounds < b.max_rounds and strat in ("TOURNAMENT", "ITERATIVE"):
            notes = [w for c in (best.critiques or []) for w in c.get("weaknesses", [])][:4] + best.deterministic.get("notes", [])[:3]
            if not notes:
                stop = "nothing specific left to fix"
                break
            reviser = synthesizer if strat != "ITERATIVE" else contestants[0]
            prompt_r = (f"BRIEF:\n{brief}\n\nCURRENT VERSION:\n{best.text[:3000]}\n\nFix ONLY these problems and keep everything else "
                        "unchanged:\n- " + "\n- ".join(notes))
            r2 = gen(reviser, prompt_r, "revision", 3 + rounds, [best.id])
            rounds += 1
            if isinstance(r2, str):
                stop = f"refinement stopped: {r2} would be exceeded"
                break
            if r2.status != "ok":
                stop = f"revision failed ({r2.error[:80]})"
                break
            judge([r2])
            gain = (r2.score or 0) - (best.score or 0)
            obs.event("refinement", f"gain {gain:+.3f}", {"entry": r2.id, "score": r2.score, "previous": best.score})
            if gain > 0:
                best = r2
            else:
                r2.status, r2.error = "rejected", f"no improvement ({gain:+.3f})"
            db.commit()
            if (best.score or 0) >= quality_target:
                stop = f"quality target {quality_target:.2f} reached after revision ({best.score:.2f})"
            elif gain < min_gain:
                stop = f"diminishing returns: revision changed the score by {gain:+.3f} (< {min_gain})"
        if not stop:
            stop = "rounds exhausted" if b.max_rounds else "single pass complete"

        # ---- result, alternatives, value per resource
        best.accepted = True
        t.result_entry_id, t.final_score = best.id, best.score
        t.status = "completed" if (best.score or 0) >= quality_target else "stopped"
        all_ok = [e for e in db.scalars(select(CreativeEntry).where(CreativeEntry.tournament_id == t.id, CreativeEntry.status == "ok"))]
        if alternatives and len(all_ok) > 1:
            crit = lambda e, d: max((c["scores"].get(d, 0) for c in (e.critiques or [])), default=0)  # noqa: E731
            t.alternatives = [{"label": "best overall", "entry": best.id},
                              {"label": "most original", "entry": max(all_ok, key=lambda e: crit(e, "originality")).id},
                              {"label": "most faithful to the brief", "entry": max(all_ok, key=lambda e: e.deterministic.get("score", 0)).id}]
        u = m.as_dict()
        units = u["tokens"] / 10_000 + u["usd"] / 0.01 + u["seconds"] / 60
        extra = max(1, u["calls"] - len(ok))
        t.usage = {**u, "rounds": 1 + rounds, "models": sorted({e.model_id for e in all_ok}), "first_round_best": first_best,
                   "creative_value_per_resource_unit": round((best.score or 0) / (1 + units), 4),
                   "gain_per_extra_call": round(((best.score or 0) - first_best) / extra, 4), "resource_units": round(units, 3)}
        if t.status == "stopped":
            stop += f" — final score {best.score:.2f} is below the target {quality_target:.2f}: human review suggested"
        return t
    finally:
        t.stop_reason = t.stop_reason or stop
        if not t.usage:
            t.usage = m.as_dict()
        t.finished_at = datetime.now(UTC)
        gov.audit(db, actor, "creative.tournament.finished", f"creative:{t.id}", status=t.status, score=t.final_score, usage=t.usage,
                  stop=t.stop_reason[:300])
        db.commit()
        obs.event("stop", t.status, {"reason": t.stop_reason, "usage": t.usage, "result_entry": t.result_entry_id})
        obs.finish(trace, {"completed": "succeeded"}.get(t.status, t.status), output={"result_entry": t.result_entry_id, "score": t.final_score,
                                                                                     "stop_reason": t.stop_reason},
                   tokens_in=m.tokens_in, tokens_out=m.tokens_out, cost_usd=m.usd)
        obs.current_run.reset(token)


def save_to_vault(db: Session, t: Any, user: Any) -> int:
    """Keep an accepted result as model-generated material in the Knowledge Vault, with full provenance."""
    from ..governance import core as gov
    from ..knowledge import process
    from ..knowledge.extract import Extracted
    from ..models import CreativeEntry

    e = db.get(CreativeEntry, t.result_entry_id) if t.result_entry_id else None
    if e is None:
        raise ValueError("the tournament has no accepted result")
    prov = (f"Creative tournament #{t.id} · strategy {t.strategy} · routing {t.routing_mode} · final score {t.final_score:.2f} · "
            f"produced by {e.model_id} ({e.role}, round {e.round}) · sources {e.sources or '—'} · critics "
            f"{sorted({c['critic'] for c in (e.critiques or [])}) or 'none'} · requested by {t.created_by}")
    doc = process.ingest(db, Extracted("markdown", "text/markdown", e.text),
                         {"title": f"[{t.category}] {t.brief[:80]}", "description": prov, "source": f"creative tournament #{t.id}",
                          "tags": ["model-generated", "creative", t.category], "evidence_class": "model_generated",
                          "classification": t.classification, "collection": "creative-library"}, owner_id=getattr(user, "id", None))
    t.saved_document_id = doc.id
    gov.audit(db, user.email, "creative.save", f"document:{doc.id}", tournament=t.id, entry=e.id)
    db.commit()
    return doc.id
