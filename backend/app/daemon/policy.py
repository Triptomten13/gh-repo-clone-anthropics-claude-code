"""Routing policy: which (provider, model) may serve a request, in which order, and why others were excluded.

Principles (DAEMON COST INTELLIGENCE):
  * cheapest adequate first — routine tiers go to local models; premium models only where the tier needs them
  * offline mode / OFFLINE profile ⇒ no external provider is ever tried, not even as a fallback
  * private/sensitive data ⇒ local or LAN only
  * paid calls only within configured spend limits; never silently
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from ..ai import registry
from . import quota, state

PROFILE_INFO: dict[str, dict[str, Any]] = {
    "ECO": {"summary": "local small model first; external only for the fast tier and only if allowed", "max_tokens": 1024},
    "BALANCED": {"summary": "local for fast/standard work, strongest available for deep reasoning", "max_tokens": None},
    "DEEP": {"summary": "strongest available model first (external if permitted), local as fallback", "max_tokens": None},
    "SPECIALIST": {"summary": "operator-defined chains (MODEL_CHAIN_<TIER>), still subject to offline/privacy/spend rules", "max_tokens": None},
    "OFFLINE": {"summary": "local and LAN workers only — external providers are never called", "max_tokens": None},
    "EMERGENCY": {"summary": "smallest local model, short outputs, nothing external — for degraded hardware or incidents", "max_tokens": 256},
    "PERFORMANCE": {"summary": "routing as BALANCED; keeps models resident longer and prewarms the deep model for speed", "max_tokens": None},
    "LOW_MEMORY": {"summary": "one resident model, short context, small models first — entered automatically under memory pressure", "max_tokens": 512},
}
LOCAL_TIER_SLOTS = {"fast": ["eco", "chat"], "standard": ["chat", "eco"], "deep": ["deep", "chat"], "local": ["chat", "eco"]}
PRIVATE = {"private", "sensitive", "personal", "highly_sensitive"}  # never to an external provider
LOCAL_ONLY = {"highly_sensitive"}  # not even a self-hosted LAN worker: in-process models only


@dataclass
class Candidate:
    provider: str
    model: str
    locality: str  # local | lan | external
    paid: bool


def provider_locality(pid: str, prov: Any | None) -> str:
    if pid == "local":
        return "local"
    if prov is not None and getattr(prov, "locality", None):
        return prov.locality
    if pid == "ollama":
        from .runtime import locality_of_url

        return locality_of_url(os.getenv("OLLAMA_BASE_URL", "http://localhost"))
    return "external"


def _external_chain(tier: str) -> list[tuple[str, str]]:
    return [(p, m) for p, m in registry.tier_chain(tier) if p not in ("ollama", "local")]


def plan(tier: str, providers: dict[str, Any], *, sensitivity: str = "normal", profile: str | None = None) -> tuple[list[Candidate], list[dict]]:
    st = state.load()
    prof = (profile or st["profile"] or "BALANCED").upper()
    if profile is None:
        from . import residency

        prof = residency.effective_mode() if residency.effective_mode() in ("LOW_MEMORY", "EMERGENCY") else prof
    offline = bool(st["offline_mode"]) or prof == "OFFLINE"
    excluded: list[dict] = []

    local: list[tuple[str, str]] = [("local", slot) for slot in LOCAL_TIER_SLOTS.get(tier, ["chat"])]
    if prof == "EMERGENCY":
        local = [("local", "eco"), ("local", "chat")]
    ollama_models = [x.strip() for x in os.getenv("OLLAMA_MODELS", "").split(",") if x.strip()]
    if ollama_models:
        local.append(("ollama", ollama_models[0]))
    workers = [(pid, getattr(p, "default_model", "")) for pid, p in providers.items() if pid.startswith("worker:")]

    override = os.getenv(f"MODEL_CHAIN_{tier.upper()}")
    if override:
        order = registry.tier_chain(tier)  # explicit operator order
    else:
        ext = _external_chain(tier)
        if prof == "EMERGENCY":
            order = local
        elif prof in ("ECO", "OFFLINE", "LOW_MEMORY"):
            order = local + workers + (ext if tier == "fast" else [])
        elif prof == "DEEP" or (prof == "BALANCED" and tier == "deep"):
            order = ext + workers + local
        else:  # BALANCED fast/standard, SPECIALIST without override
            order = local + workers + ext

    seen: set[tuple[str, str]] = set()
    out: list[Candidate] = []
    for pid, model in order:
        if (pid, model) in seen:
            continue
        seen.add((pid, model))
        cand, why = check_candidate(pid, model, providers, sensitivity=sensitivity, tier=tier, offline=offline, st=st)
        if why:
            excluded.append(why)
        else:
            out.append(cand)
    return out, excluded


def check_candidate(pid: str, model: str, providers: dict[str, Any], *, sensitivity: str = "normal", tier: str = "standard",
                    offline: bool | None = None, st: dict[str, Any] | None = None) -> tuple[Candidate | None, dict | None]:
    """The policy for ONE (provider, model): offline mode, privacy/classification, the external master switch and quota.
    Used by tier routing (plan) and by agents that choose a specific model (DAEMON PROVIDER INTELLIGENCE) — the same
    rules whichever way a model is chosen. Returns (candidate, None) or (None, exclusion record)."""
    st = st or state.load()
    if offline is None:
        offline = bool(st["offline_mode"]) or (st.get("profile") or "").upper() == "OFFLINE"
    prov = providers.get(pid)
    loc = provider_locality(pid, prov)
    spec = registry.find(pid, model)
    paid = bool(spec and (spec.input_usd_per_mtok or spec.output_usd_per_mtok))
    rec = {"provider": pid, "model": model, "tier": tier, "locality": loc}
    if loc == "external":
        if offline:
            return None, {**rec, "status": "excluded_offline"}
        if sensitivity in PRIVATE:
            return None, {**rec, "status": "excluded_privacy"}
        if not st["external_allowed"]:
            return None, {**rec, "status": "excluded_external_disabled"}
    elif loc == "lan" and sensitivity == "sensitive":
        return None, {**rec, "status": "excluded_privacy"}
    if loc != "local" and sensitivity in LOCAL_ONLY:  # after the external/LAN rules, for every remaining non-local candidate
        return None, {**rec, "status": "excluded_classification"}
    reason = quota.blocked_reason(pid)
    if reason:
        return None, {**rec, "status": "paused", "error": reason}
    return Candidate(pid, model, loc, paid), None


def max_tokens_cap(profile: str | None = None) -> int | None:
    prof = (profile or state.load()["profile"] or "BALANCED").upper()
    return PROFILE_INFO.get(prof, {}).get("max_tokens")


def estimate_cost(provider: str, model: str, system: str, prompt: str, max_tokens: int) -> float:
    spec = registry.find(provider, model)
    if not spec:
        return 0.0
    est_in = (len(system) + len(prompt)) // 3 + 50  # conservative chars→tokens
    return spec.cost(est_in, min(max_tokens, 4000))
