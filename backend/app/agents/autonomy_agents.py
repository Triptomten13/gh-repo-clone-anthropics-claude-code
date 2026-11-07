"""The Model Hunter and the Devil's Advocate as orchestrated agents (budgets, kill switch, dedupe, audit apply).

* Model Hunter (`model.discover`, `model.championship`, `model.request_acquisition`): searches, screens and measures. It
  may REQUEST a download — a person approves it — and never connects accounts or grants itself anything.
* Devil's Advocate (`decision.review`): reviews any decision record, including G-SUS's plans and the orchestrator's model
  choices. It can block only on policy/security violations; otherwise it recommends and escalates.
"""
from __future__ import annotations

from ..models import Task
from .base import AgentContext, AgentOutput, BaseAgent, Blocked


class ModelHunterAgent(BaseAgent):
    id, name, division = "model_hunter", "The Model Hunter", "laboratory"
    description = "Finds new models on Hugging Face, screens them before any download, and lets the Model Championship decide."
    level, tier = 1, "deep"  # analysis level; deep tier for the long championship timeout
    task_types = ("model.discover", "model.championship", "model.request_acquisition")

    def handle(self, ctx: AgentContext, task: Task) -> AgentOutput:
        from ..autonomy import championship, hunter

        p = task.payload or {}
        if task.type == "model.discover":
            try:
                r = hunter.discover(ctx.db, p.get("task", "general"), limit=int(p.get("limit", 15)), actor=f"agent:{self.id}")
            except RuntimeError as e:
                raise Blocked(str(e)) from e
            return AgentOutput(summary=f"{r['task']}: {r['searched']} searched, {r.get('shortlisted', 0)} shortlisted, "
                                       f"{r.get('screened_out', 0)} screened out, {r['unchanged']} unchanged since last scan",
                               result=r, epistemic="verified", confidence=0.9)
        if task.type == "model.request_acquisition":
            c = hunter.request_acquisition(ctx.db, int(p["candidate_id"]), actor=f"agent:{self.id}", agent_id=self.id)
            if c.status == "pending_approval":
                raise Blocked(f"download of {c.repo} waits for approval #{c.approval_id} (critique #{c.critique_id})")
            return AgentOutput(summary=f"{c.repo}: {c.status}", result={"candidate": c.id, "status": c.status, "critique": c.critique_id})
        ch = championship.run(ctx.db, actor=f"agent:{self.id}", models=p.get("models"), max_seconds=int(p.get("max_seconds", 2700)))
        return AgentOutput(summary=ch.summary or ch.error, result={"championship": ch.id, "status": ch.status, "deltas": ch.deltas},
                           epistemic="verified" if ch.status == "completed" else "estimate", confidence=0.9)


class DevilsAdvocateAgent(BaseAgent):
    id, name, division = "devils_advocate", "The Devil's Advocate", "security"
    description = "Challenges important decisions — including G-SUS's — with evidence and alternatives; blocks only on policy or security."
    level, tier = 1, "standard"
    task_types = ("decision.review",)

    def handle(self, ctx: AgentContext, task: Task) -> AgentOutput:
        from ..autonomy import advocate

        p = task.payload or {}
        d = p.get("decision") or {}
        if not d.get("kind"):
            raise Blocked("decision.review needs a decision record with a 'kind'")
        c = advocate.review(ctx.db, d, mode=p.get("mode", "DEVILS_ADVOCATE"), use_model=bool(p.get("use_model")), actor=f"agent:{self.id}")
        return AgentOutput(summary=c.summary, result={"critique": c.id, "verdict": c.verdict}, findings=c.findings,
                           risks=[f["weakness"] for f in c.findings if f["severity"] != "optional"],
                           epistemic="verified" if c.reviewer == "rules" else "estimate", confidence=0.85)
