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
    def __init__(self, db: Session, task: Task, agent_row: Agent, orchestrator: Orchestrator) -> None:
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
    def spawn(self, task_type: str, payload: dict[str, Any], priority: int = 50, agent_id: str | None = None,
              depends_on: list[int] | None = None) -> Task:
        return self.orch.submit(self.db, task_type, payload, requested_by=self.agent_row.id, parent=self.task,
                                priority=priority, agent_id=agent_id, depends_on=depends_on)

    # --- LLM
    def llm(self, system: str, prompt: str, schema: dict | None = None, tier: str | None = None, purpose: str = "") -> LLMResult:
        from ..ai import tracing
        from ..ai.llm import LLMRefused, LLMUnavailable

        self.orch.check_token_budget(self.db, self.agent_row)
        from ..daemon import prompts, telemetry

        est = prompts.estimate_tokens(system) + prompts.estimate_tokens(prompt)
        agent = self.orch.agents.get(self.agent_row.id)
        budget = agent.context_budget if agent else CONTEXT_BUDGET.get(self.agent_row.model_tier, 12000)
        if est > budget:  # measured and surfaced (never silently truncated: that could drop evidence)
            telemetry.event("context_over_budget", agent=self.agent_row.id, task=self.task.type, est_tokens=est, budget=budget)
        try:
            res = get_provider().complete(system=system, prompt=prompt, schema=schema, tier=tier or self.agent_row.model_tier)
        except (LLMUnavailable, LLMRefused) as e:
            tracing.record(self.db, getattr(e, "attempts", []), task_id=self.task.id, agent_id=self.agent_row.id, purpose=purpose or self.task.type)
            raise Blocked(str(e)) from e
        tracing.record(self.db, getattr(res, "attempts", []), task_id=self.task.id, agent_id=self.agent_row.id,
                       purpose=purpose or self.task.type, fallback_result=res)
        self.tokens += res.input_tokens + res.output_tokens
        self.cost_usd += res.cost_usd
        return res

    def audit(self, action: str, target: str = "", **details: Any) -> None:
        gov.audit(self.db, f"agent:{self.agent_row.id}", action, target, **details)


CONTEXT_BUDGET = {"fast": 4000, "standard": 12000, "deep": 24000}  # tokens per model call; measured, then enforced


class BaseAgent:
    id: str = ""
    name: str = ""
    division: str = ""
    description: str = ""
    level: int = 0
    tier: str = "standard"
    task_types: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()  # DAEMON tools this agent may call; empty = none
    success_criterion: str = "returns an AgentOutput with a summary and labelled evidence; blocked/failed outcomes are reported, never faked"
    context_budget_tokens: int | None = None  # default by tier (CONTEXT_BUDGET)

    @property
    def context_budget(self) -> int:
        return self.context_budget_tokens or CONTEXT_BUDGET.get(self.tier, 12000)

    def handle(self, ctx: AgentContext, task: Task) -> AgentOutput:  # pragma: no cover - abstract
        raise NotImplementedError

    SYSTEM_RULES = (
        "You are an agent inside a governed commerce-intelligence system operating in Sweden/EU. "
        "Never fabricate sales figures, statistics, supplier credentials, reviews or testimonials. "
        "Label every claim as verified, estimate, assumption or hypothesis. "
        "Never impersonate creators or invent endorsements. No deceptive scarcity or fake discounts. "
        "Follow EU consumer, marketing and product-safety law."
    )
