"""Runtime for agents made with the Custom Agent Creator.

A custom agent is an ordinary row in `agents` (custom=True) registered in the ONE orchestrator under the task type
`custom.<id>`: budgets, kill switch, dedupe, audit, tracing and Tool Gateway grants apply exactly as for code agents.
Its identity shapes the prompt (voice, priorities); its authority comes only from permission_level and grants.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents.base import AgentContext, AgentOutput, BaseAgent, Blocked
from ..models import Agent, Species, Task
from ..security import untrusted

ANSWER_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["answer", "facts", "assumptions", "escalate"],
    "properties": {"answer": {"type": "string"}, "facts": {"type": "array", "items": {"type": "string"}},
                   "assumptions": {"type": "array", "items": {"type": "string"}}, "escalate": {"type": "boolean"},
                   "escalation_reason": {"type": "string"}},
}

GOVERNANCE_RULES = (
    "Chain of command: you report to G-SUS and obey it within the scope it delegates — whatever your race, rank or "
    "'dimension'. G-SUS itself can never override the human owner, the law, governance, budgets, approvals, security rules "
    "or the kill switch, and neither can you. You cannot grant yourself permissions or tools; if a task needs access you do "
    "not have, or information you lack, set escalate=true and say why instead of guessing. Keep facts (with their source) "
    "and assumptions in separate lists. Your personality shapes HOW you speak, never WHAT you are allowed to do."
)


def task_type(agent_id: str) -> str:
    return f"custom.{agent_id}"


def system_prompt(row: Agent, species: Species | None = None) -> str:
    m = row.mission or {}
    lines = [
        BaseAgent.SYSTEM_RULES,
        GOVERNANCE_RULES,
        f"You are {row.persona_name or row.name}, {row.title or row.name} in Demonkoncernen AB "
        f"({species.name if species else (row.species_key or 'unassigned species')}; fictional identity).",
        f"Purpose: {row.purpose}" if row.purpose else "",
        "Primary tasks: " + "; ".join(m.get("primary", [])) if m.get("primary") else "",
        "Secondary tasks: " + "; ".join(m.get("secondary", [])) if m.get("secondary") else "",
        "You must NOT: " + "; ".join(m.get("not_to_do", [])) if m.get("not_to_do") else "",
        "Specializations: " + ", ".join(row.specializations or []) if row.specializations else "",
        "Personality (expression only): " + ", ".join(row.traits or []) + (f". {row.personality}" if row.personality else "")
        if (row.traits or row.personality) else "",
        "Communication style: " + ", ".join(row.communication_style or []) if row.communication_style else "",
        "Answer in the language of the request (" + ", ".join(row.languages or ["English"]) + " supported)."
    ]
    return "\n".join(x for x in lines if x)


class CustomAgent(BaseAgent):
    custom = True
    success_criterion = "answers within its mission with facts and assumptions separated; escalates instead of guessing"

    def __init__(self, row: Agent) -> None:
        self.id, self.name, self.division = row.id, row.name, row.division or "custom"
        self.description, self.level, self.tier = row.description, row.permission_level, row.model_tier or "standard"
        self.task_types = (task_type(row.id),)

    def handle(self, ctx: AgentContext, task: Task) -> AgentOutput:
        row = ctx.agent_row  # the live row: lifecycle and identity edits apply immediately
        if row.lifecycle != "ACTIVE":
            raise Blocked(f"{row.persona_name or row.id} is {row.lifecycle}, not ACTIVE")
        ctx.check("custom.task")
        p = task.payload or {}
        objective = str(p.get("objective") or p.get("prompt") or "").strip()
        if not objective:
            raise Blocked("no objective given")
        context = ""
        if p.get("use_archive"):  # through the Tool Gateway: needs this agent's own grant, like any tool use
            hits = ctx.tool("archive.search", {"query": objective[:300], "k": 4})
            context = "\n\n" + untrusted.wrap(str(hits)[:4000], source_id="archive.search", title="archive search results")
        species = ctx.db.get(Species, row.species_key) if row.species_key else None
        res = ctx.llm(system_prompt(row, species), objective + context, schema=ANSWER_SCHEMA, purpose=f"custom:{row.id}")
        data: dict[str, Any] = res.data if isinstance(res.data, dict) else {"answer": res.text, "facts": [], "assumptions": [],
                                                                             "escalate": False}
        out = AgentOutput(summary=(data.get("answer") or res.text or "")[:2000], result=data | {"model": res.model},
                          findings=data.get("facts", []), epistemic="estimate", confidence=0.5)
        if data.get("escalate"):
            out.required_approvals.append({"escalation": data.get("escalation_reason") or "the agent asked for help"})
        return out


def register(orch: Any, row: Agent) -> None:
    """(Re-)register one custom agent in the shared orchestrator — overwrite, so edits take effect."""
    agent = CustomAgent(row)
    orch.agents[row.id] = agent
    orch.routes[task_type(row.id)] = row.id


def unregister(orch: Any, agent_id: str) -> None:
    orch.routes.pop(task_type(agent_id), None)
    orch.agents.pop(agent_id, None)


def load(db: Session, orch: Any) -> int:
    n = 0
    for row in db.scalars(select(Agent).where(Agent.custom.is_(True), Agent.lifecycle.notin_(("ARCHIVED", "DRAFT")))):
        register(orch, row)
        n += 1
    return n
