"""Model abstraction layer.

Agents ask for a *tier* (deep / standard / fast), not a vendor model. The
provider maps tiers to concrete models (configurable via env). If no provider is
configured, ``LLMUnavailable`` is raised and the calling agent reports the task
as *blocked* — it never fabricates model output.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from ..config import get_settings

# USD per 1M tokens (input, output). Keep in sync with provider pricing.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}
EFFORT_BY_TIER = {"deep": "high", "standard": "medium", "fast": "low"}


class LLMUnavailable(RuntimeError):
    pass


class LLMRefused(RuntimeError):
    pass


@dataclass
class LLMResult:
    text: str
    data: Any | None
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


class LLMProvider(Protocol):
    name: str

    def complete(self, *, system: str, prompt: str, tier: str = "standard", schema: dict | None = None,
                 max_tokens: int = 16000) -> LLMResult: ...


def _cost(model: str, inp: int, out: int) -> float:
    pi, po = PRICES.get(model, (0.0, 0.0))
    return round(inp / 1e6 * pi + out / 1e6 * po, 6)


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, client: Any | None = None) -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self.client = client
        s = get_settings()
        self.models = {"deep": s.model_deep, "standard": s.model_standard, "fast": s.model_fast}

    def complete(self, *, system: str, prompt: str, tier: str = "standard", schema: dict | None = None,
                 max_tokens: int = 16000) -> LLMResult:
        model = self.models.get(tier, self.models["standard"])
        output_config: dict[str, Any] = {"effort": EFFORT_BY_TIER.get(tier, "medium")}
        if schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        kwargs: dict[str, Any] = dict(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            thinking={"type": "adaptive"},
            output_config=output_config,
        )
        if model in ("claude-opus-5-5", "claude-sonnet-5-5"):
            # Server-side refusal fallback (routes by refusal category).
            resp = self.client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
        else:
            resp = self.client.messages.create(**kwargs)
        if resp.stop_reason == "refusal":
            raise LLMRefused(f"model declined the request ({getattr(resp, 'stop_details', None)})")
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        data = None
        if schema is not None:
            try:
                data = json.loads(text)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"model returned invalid JSON: {e}") from e
        u = resp.usage
        return LLMResult(text=text, data=data, model=resp.model, input_tokens=u.input_tokens,
                         output_tokens=u.output_tokens, cost_usd=_cost(model, u.input_tokens, u.output_tokens))


class UnavailableProvider:
    name = "none"

    def complete(self, **_: Any) -> LLMResult:
        raise LLMUnavailable("No LLM provider configured: set ANTHROPIC_API_KEY (see INTEGRATIONS.md)")


_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        s = get_settings()
        if s.llm_enabled and s.anthropic_api_key_present:
            _provider = AnthropicProvider()
        else:
            _provider = UnavailableProvider()
    return _provider


def set_provider(p: LLMProvider | None) -> None:
    """Override (tests, or alternative providers registered at startup)."""
    global _provider
    _provider = p
