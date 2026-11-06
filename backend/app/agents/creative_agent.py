"""Creative Director — runs Creative Tournaments for other agents and G-sus (task type `creative.tournament`).

The agent chooses HOW (routing mode, strategy, models) within the tournament's hard budget; the policy engine decides
WHETHER it may (paid spending above the autonomous limit needs a human approval; an agent never approves). It reads only
what the person it works for may read, and its result is model-generated material — labelled as such.
"""
from __future__ import annotations

from sqlalchemy import select

from ..models import Task, User
from .base import AgentContext, AgentOutput, BaseAgent, Blocked


class CreativeDirectorAgent(BaseAgent):
    id, name, division = "creative_director", "Creative Director", "creative"
    description = "Runs multi-model Creative Tournaments: candidates, independent critics, synthesis, revision — under a hard budget."
    level, tier = 2, "deep"  # deep: local tournaments take minutes on CPU (task timeout follows the tier)
    task_types = ("creative.tournament",)

    def handle(self, ctx: AgentContext, task: Task) -> AgentOutput:
        from ..creative import tournament as T
        from ..governance.policy import PolicyDenied

        p = task.payload or {}
        brief = str(p.get("brief") or "").strip()
        if len(brief) < 3:
            raise Blocked("creative.tournament needs a 'brief'")
        user = None
        if (task.requested_by or "").startswith("user:"):
            user = ctx.db.scalars(select(User).where(User.email == task.requested_by[5:])).first()
        try:
            t = T.run(ctx.db, brief, user=user, agent_id=self.id, workflow=f"agent:{self.id}", mode=p.get("mode", "FREE_FIRST"),
                      strategy=p.get("strategy", "AUTOMATIC"), category=p.get("category"), quality_target=float(p.get("quality_target", 0.75)),
                      budget=p.get("budget"), classification=p.get("classification", "INTERNAL"), approval_id=p.get("approval_id"))
        except PolicyDenied as e:
            raise Blocked(f"policy: {e}") from e
        if t.status == "pending_approval":
            raise Blocked(f"tournament #{t.id} needs approval #{t.approval_id}: {t.stop_reason}")
        from ..models import CreativeEntry

        best = ctx.db.get(CreativeEntry, t.result_entry_id) if t.result_entry_id else None
        return AgentOutput(
            summary=f"Creative tournament #{t.id} ({t.strategy}): {t.status}, score {t.final_score if t.final_score is not None else '—'} — {t.stop_reason[:160]}",
            result={"tournament": t.id, "status": t.status, "score": t.final_score, "text": best.text if best else None,
                    "model": best.model_id if best else None, "usage": t.usage, "stop_reason": t.stop_reason},
            epistemic="hypothesis", confidence=float(t.final_score or 0.0),
            risks=["Model-generated creative material: review before publishing; publishing is a separate, approved action"])
