"""Backwards-compatible facade over the provider router.

Agents ask for a *tier* (deep / standard / fast), never a vendor model. If no
provider can serve a request, ``LLMUnavailable`` is raised and the calling agent
reports the task as *blocked* — it never fabricates model output.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..config import get_settings
from . import registry
from .providers import AnthropicProvider, LLMRefused  # noqa: F401 - re-exported
from .router import EFFORT_BY_TIER, LLMRouter, LLMUnavailable  # noqa: F401 - re-exported

PRICES = {m.model_id: (m.input_usd_per_mtok, m.output_usd_per_mtok) for m in registry.ANTHROPIC}


@dataclass
class LLMResult:
    text: str
    data: Any | None
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    provider: str = ""
    latency_ms: int = 0
    attempts: list[dict] = field(default_factory=list)


class LLMProvider(Protocol):
    name: str

    def complete(self, *, system: str, prompt: str, tier: str = "standard", schema: dict | None = None,
                 max_tokens: int = 16000) -> LLMResult: ...


class UnavailableProvider:
    name = "none"

    def complete(self, **_: Any) -> LLMResult:
        raise LLMUnavailable("No LLM provider configured: set ANTHROPIC_API_KEY or OLLAMA_BASE_URL (see docs/AI_SYSTEM.md)")

    def stream(self, **_: Any):
        raise LLMUnavailable("No LLM provider configured")

    def health(self) -> list[dict[str, Any]]:
        return []


_override: Any = None
_router: LLMRouter | None = None
_UNAVAILABLE = UnavailableProvider()


def get_router() -> LLMRouter:
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router


def get_provider() -> Any:
    """The active completion provider: a test override, else the router when enabled and any provider (local
    model, worker, or authorised API) is configured, else 'none'. Re-evaluated on every call so that installing
    or activating a local model takes effect without a restart."""
    if _override is not None:
        return _override
    r = get_router()
    return r if get_settings().llm_enabled and r.configured() else _UNAVAILABLE


def set_provider(p: Any | None) -> None:
    """Override (tests, or alternative providers registered at startup). None resets to auto-detection."""
    global _override, _router
    _override = p
    if p is None:
        _router = None
