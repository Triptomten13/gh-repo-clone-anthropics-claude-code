"""Agent base classes and execution context."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from ..ai.llm import LLMResult, get_provider
from ..governance import core as gov
from ..models import Agent, Task
from ..security import permissions

if TYPE_CHECKING:  # pragma: no cover
    from .orchestrator import Orchestrator


class Blocked(Exception):
    """Task cannot proceed (missing data, credentials, permission, approval). Not retried."""


@dataclass
class AgentOutput:
    summary: str
    result: dict[str, Any] = field(default_factory=dict)
    findings: list[Any] = field(default_factory=list)
    evidence: list[Any] = field(default_factory=list)
    confidence: float = 0.5
    epistemic: str = "estimate"  # verified | estimate | assumption | hypothesis
    recommendations: list[Any] = field(default_factory=list)
    financial_impact_sek: float | None = None
    risks: list[Any] = field(default_factory=list)
    required_approvals: list[Any] = field(default_factory=list)


class AgentContext:
    def __init__(self, db: Session, task: Task, agent_row: Agent, orchestrator: "Orchestrator") -> None:
        self.db = db
        self.task = task
        self.agent_row = agent_row
        self.orch = orchestrator
        self.tokens = 0
        self.cost_usd = 0.0

    # --- permissions
    def check(self, action: str) -> None:
        try:
            permissions.check(self.agent_row.permission_level, action)
        except permissions.PermissionDenied as e:
            raise Blocked(str(e)) from e

    def request_approval(self, action: str, title: str, description: str = "", payload: dict | None = None,
                         amount_sek: float | None = None) -> dict[str, Any]:
        a = gov.request_approval(self.db, action, title, self.agent_row.id, description, payload, amount_sek)
        return {"approval_id": a.id, "action": action, "title": title, "status": a.status}

    # --- delegation
    def spawn(self, task_type: str, payload: dict[str, Any], priority: int = 50) -> Task:
        return self.orch.submit(self.db, task_type, payload, requested_by=self.agent_row.id, parent=self.task, priority=priority)

    # --- LLM
    def llm(self, system: str, prompt: str, schema: dict | None = None, tier: str | None = None) -> LLMResult:
        from ..ai.llm import LLMRefused, LLMUnavailable

        self.orch.check_token_budget(self.db, self.agent_row)
        try:
            res = get_provider().complete(system=system, prompt=prompt, schema=schema, tier=tier or self.agent_row.model_tier)
        except (LLMUnavailable, LLMRefused) as e:
            raise Blocked(str(e)) from e
        self.tokens += res.input_tokens + res.output_tokens
        self.cost_usd += res.cost_usd
        return res

    def audit(self, action: str, target: str = "", **details: Any) -> None:
        gov.audit(self.db, f"agent:{self.agent_row.id}", action, target, **details)


class BaseAgent:
    id: str = ""
    name: str = ""
    division: str = ""
    description: str = ""
    level: int = 0
    tier: str = "standard"
    task_types: tuple[str, ...] = ()

    def handle(self, ctx: AgentContext, task: Task) -> AgentOutput:  # pragma: no cover - abstract
        raise NotImplementedError

    SYSTEM_RULES = (
        "You are an agent inside a governed commerce-intelligence system operating in Sweden/EU. "
        "Never fabricate sales figures, statistics, supplier credentials, reviews or testimonials. "
        "Label every claim as verified, estimate, assumption or hypothesis. "
        "Never impersonate creators or invent endorsements. No deceptive scarcity or fake discounts. "
        "Follow EU consumer, marketing and product-safety law."
    )
