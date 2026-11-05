"""Provider-independent router: tier → ordered (provider, model) chain, with
per-provider circuit breakers, fallback on unavailability (never on refusal),
and a record of every attempt for tracing and cost accounting."""
from __future__ import annotations

import os
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

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
    reasoning: str = ""
    reasoning_truncated: bool = False


def default_providers() -> dict[str, Provider]:
    from ..daemon.runtime import get_local

    return {"local": get_local(), "anthropic": AnthropicProvider(), "ollama": OllamaProvider()}  # type: ignore[dict-item]


class LLMRouter:
    """Routes by tier through the DAEMON policy (offline mode, privacy, profile, quota, spend limits)."""

    def __init__(self, providers: dict[str, Provider] | None = None) -> None:
        self.providers: dict[str, Provider] = providers or default_providers()
        self.breakers: dict[str, Breaker] = {k: Breaker() for k in self.providers}

    def _all_providers(self) -> dict[str, Provider]:
        try:
            from ..daemon.workers import active_worker_providers

            extra = active_worker_providers()
        except Exception:
            extra = {}
        for k in extra:
            self.breakers.setdefault(k, Breaker())
        return {**self.providers, **extra}

    @property
    def name(self) -> str:
        on = [k for k, p in self._all_providers().items() if p.configured()]
        return "+".join(on) if on else "none"

    def configured(self) -> bool:
        return any(p.configured() for p in self._all_providers().values())

    def complete(self, *, system: str, prompt: str, tier: str = "standard", schema: dict | None = None, max_tokens: int = 16000,
                 sensitivity: str = "normal", profile: str | None = None) -> RouterResult:
        from ..daemon import policy, quota

        providers = self._all_providers()
        cands, excluded = policy.plan(tier, providers, sensitivity=sensitivity, profile=profile)
        cap = policy.max_tokens_cap(profile)
        if cap:
            max_tokens = min(max_tokens, cap)
        attempts: list[dict] = list(excluded)
        for c_ in cands:
            prov_id, model = c_.provider, c_.model
            p = providers.get(prov_id)
            rec = {"provider": prov_id, "model": model, "tier": tier, "locality": c_.locality}
            if p is None or not p.configured():
                attempts.append({**rec, "status": "not_configured"})
                continue
            br = self.breakers.setdefault(prov_id, Breaker())
            if br.is_open():
                attempts.append({**rec, "status": "circuit_open"})
                continue
            if c_.paid:
                blocked = quota.spend_check(prov_id, policy.estimate_cost(prov_id, model, system, prompt, max_tokens))
                if blocked:
                    attempts.append({**rec, "status": "spend_blocked", "error": blocked})
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
                if quota.is_rate_limit(str(e)):
                    wait = quota.note_rate_limited(prov_id)
                    attempts.append({**rec, "status": "rate_limited", "error": f"{str(e)[:200]} — backing off {int(wait)}s",
                                     "latency_ms": int((time.monotonic() - t0) * 1000)})
                    continue
                br.fail(str(e))
                attempts.append({**rec, "status": "unavailable" if isinstance(e, ProviderUnavailable) else "error", "error": str(e)[:300],
                                 "latency_ms": int((time.monotonic() - t0) * 1000)})
                continue
            br.ok(c.latency_ms)
            quota.note_success(prov_id, c.input_tokens + c.output_tokens)
            attempts.append({**rec, "status": "ok", "model": c.model, "input_tokens": c.input_tokens, "output_tokens": c.output_tokens,
                             "cost_usd": c.cost_usd, "latency_ms": c.latency_ms})
            return RouterResult(c.text, c.data, c.model, c.input_tokens, c.output_tokens, c.cost_usd, c.provider, c.latency_ms, attempts,
                                getattr(c, "reasoning", ""), getattr(c, "reasoning_truncated", False))
        raise LLMUnavailable(f"no provider could serve tier '{tier}' "
                             f"({'; '.join(a['provider'] + ':' + a['status'] for a in attempts) or 'none configured'})", attempts)

    def stream(self, *, system: str, prompt: str, tier: str = "standard", max_tokens: int = 16000, sensitivity: str = "normal",
               profile: str | None = None) -> Iterator[str]:
        from ..daemon import policy, quota

        providers = self._all_providers()
        cands, _excluded = policy.plan(tier, providers, sensitivity=sensitivity, profile=profile)
        cap = policy.max_tokens_cap(profile)
        if cap:
            max_tokens = min(max_tokens, cap)
        for c_ in cands:
            p = providers.get(c_.provider)
            if p is None or not p.configured() or self.breakers.setdefault(c_.provider, Breaker()).is_open():
                continue
            if c_.paid and quota.spend_check(c_.provider, policy.estimate_cost(c_.provider, c_.model, system, prompt, max_tokens)):
                continue
            yield from p.stream(model=c_.model, system=system, prompt=prompt, effort=EFFORT_BY_TIER.get(tier, "medium"), max_tokens=max_tokens)
            return
        raise LLMUnavailable(f"no permitted provider available for tier '{tier}'")

    def health(self) -> list[dict[str, Any]]:
        from ..daemon.policy import provider_locality

        return [{"provider": k, "locality": provider_locality(k, p), **p.health(), **self.breakers.setdefault(k, Breaker()).state()}
                for k, p in self._all_providers().items()]
