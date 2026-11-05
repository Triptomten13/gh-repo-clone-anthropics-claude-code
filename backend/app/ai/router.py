"""Provider-independent router: tier → ordered (provider, model) chain, with
per-provider circuit breakers, fallback on unavailability (never on refusal),
and a record of every attempt for tracing and cost accounting."""
from __future__ import annotations

import os
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from . import registry
from .providers import AnthropicProvider, LLMRefused, OllamaProvider, Provider, ProviderUnavailable

EFFORT_BY_TIER = {"deep": "high", "standard": "medium", "fast": "low", "local": "medium"}


class LLMUnavailable(RuntimeError):
    def __init__(self, msg: str, attempts: list[dict] | None = None):
        super().__init__(msg)
        self.attempts = attempts or []


@dataclass
class Breaker:
    failures: int = 0
    open_until: float = 0.0
    last_ok: float | None = None
    last_error: str | None = None
    last_latency_ms: int | None = None
    threshold: int = int(os.getenv("LLM_BREAKER_THRESHOLD", "3"))
    cooldown_s: float = float(os.getenv("LLM_BREAKER_COOLDOWN_S", "60"))

    def is_open(self) -> bool:
        return time.time() < self.open_until

    def ok(self, latency_ms: int | None = None) -> None:
        self.failures, self.last_ok, self.last_latency_ms = 0, time.time(), latency_ms

    def fail(self, err: str) -> None:
        self.failures += 1
        self.last_error = err[:300]
        if self.failures >= self.threshold:
            self.open_until = time.time() + self.cooldown_s

    def state(self) -> dict[str, Any]:
        return {"state": "open" if self.is_open() else "closed", "consecutive_failures": self.failures, "last_ok": self.last_ok,
                "last_error": self.last_error, "last_latency_ms": self.last_latency_ms}


@dataclass
class RouterResult:
    text: str
    data: Any
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    provider: str = ""
    latency_ms: int = 0
    attempts: list[dict] = field(default_factory=list)


class LLMRouter:
    def __init__(self, providers: dict[str, Provider] | None = None) -> None:
        self.providers: dict[str, Provider] = providers or {"anthropic": AnthropicProvider(), "ollama": OllamaProvider()}
        self.breakers: dict[str, Breaker] = {k: Breaker() for k in self.providers}

    @property
    def name(self) -> str:
        on = [k for k, p in self.providers.items() if p.configured()]
        return "+".join(on) if on else "none"

    def configured(self) -> bool:
        return any(p.configured() for p in self.providers.values())

    def complete(self, *, system: str, prompt: str, tier: str = "standard", schema: dict | None = None, max_tokens: int = 16000) -> RouterResult:
        attempts: list[dict] = []
        for prov_id, model in registry.tier_chain(tier):
            p = self.providers.get(prov_id)
            rec = {"provider": prov_id, "model": model, "tier": tier}
            if p is None or not p.configured():
                attempts.append({**rec, "status": "not_configured"})
                continue
            br = self.breakers[prov_id]
            if br.is_open():
                attempts.append({**rec, "status": "circuit_open"})
                continue
            t0 = time.monotonic()
            try:
                c = p.complete(model=model, system=system, prompt=prompt, schema=schema, effort=EFFORT_BY_TIER.get(tier, "medium"), max_tokens=max_tokens)
            except LLMRefused as e:
                br.ok()
                attempts.append({**rec, "status": "refused", "error": str(e)[:300], "latency_ms": int((time.monotonic() - t0) * 1000)})
                e.attempts = attempts  # type: ignore[attr-defined]
                raise
            except (ProviderUnavailable, RuntimeError) as e:
                br.fail(str(e))
                attempts.append({**rec, "status": "unavailable" if isinstance(e, ProviderUnavailable) else "error", "error": str(e)[:300],
                                 "latency_ms": int((time.monotonic() - t0) * 1000)})
                continue
            br.ok(c.latency_ms)
            attempts.append({**rec, "status": "ok", "model": c.model, "input_tokens": c.input_tokens, "output_tokens": c.output_tokens,
                             "cost_usd": c.cost_usd, "latency_ms": c.latency_ms})
            return RouterResult(c.text, c.data, c.model, c.input_tokens, c.output_tokens, c.cost_usd, c.provider, c.latency_ms, attempts)
        raise LLMUnavailable(f"no provider could serve tier '{tier}' "
                             f"({'; '.join(a['provider'] + ':' + a['status'] for a in attempts) or 'none configured'})", attempts)

    def stream(self, *, system: str, prompt: str, tier: str = "standard", max_tokens: int = 16000) -> Iterator[str]:
        for prov_id, model in registry.tier_chain(tier):
            p = self.providers.get(prov_id)
            if p is None or not p.configured() or self.breakers[prov_id].is_open():
                continue
            yield from p.stream(model=model, system=system, prompt=prompt, effort=EFFORT_BY_TIER.get(tier, "medium"), max_tokens=max_tokens)
            return
        raise LLMUnavailable(f"no provider configured for tier '{tier}'")

    def health(self) -> list[dict[str, Any]]:
        return [{"provider": k, **p.health(), **self.breakers[k].state()} for k, p in self.providers.items()]
