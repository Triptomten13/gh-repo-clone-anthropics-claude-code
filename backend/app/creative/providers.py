"""DAEMON PROVIDER INTELLIGENCE — which model should do this task, and why.

Built on the existing pieces, not beside them: candidates come from the model library (installed local models), LAN
workers, Ollama and the model registry (external APIs); every candidate passes the SAME per-model policy as tier
routing (`daemon.policy.check_candidate`: offline, privacy/classification, external switch, quota) and runs through the
SAME router (`LLMRouter.complete_on`: breakers, rate-limit backoff, spend limits). Budgets are reserved before every
call and settled after (governance.budgets); every attempt is traced (ai.tracing → llm_calls, run events).

Cost classes, preferred in this order by FREE-FIRST (a preference, not a rule — quality decides within it):
  local      — runs on this machine/network, no API cost (electricity is estimated elsewhere)
  free_tier  — an official free tier VERIFIED in the provider registry (none is assumed; today none is verified)
  open_endpoint — open-weight model on an authorised inference endpoint
  low_cost   — paid API ≤ $1 per million output tokens
  premium    — any other paid API
Unverified (discovered) providers are never routable.
"""
from __future__ import annotations

import logging
import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)
COST_CLASSES = ["local", "free_tier", "open_endpoint", "low_cost", "premium"]
MODES = ["FREE_FIRST", "BEST_QUALITY", "BEST_VALUE", "FASTEST", "LOCAL_FIRST", "PRIVACY_FIRST", "CREATIVE_ENSEMBLE",
         "DEEP_RESEARCH", "SPECIALIST", "BALANCED"]
MODE_INFO = {
    "FREE_FIRST": "free and local models first; a paid model only when it is clearly better and the budget allows",
    "BEST_QUALITY": "highest measured quality for the task within policy and budget",
    "BEST_VALUE": "highest quality per unit of cost and time",
    "FASTEST": "lowest measured latency with acceptable quality",
    "LOCAL_FIRST": "models on this machine first, then the private network, external last",
    "PRIVACY_FIRST": "only models on this machine — nothing leaves it",
    "CREATIVE_ENSEMBLE": "several different model families for diverse candidates",
    "DEEP_RESEARCH": "strongest reasoning and long context",
    "SPECIALIST": "models with a measured profile for this exact task category first",
    "BALANCED": "quality, cost and speed weighted evenly",
}
CATEGORIES = ["songwriting", "poetry", "storytelling", "brainstorming", "business", "design", "research", "summarization",
              "reasoning", "programming", "translation", "general"]
CREATIVE = {"songwriting", "poetry", "storytelling", "brainstorming", "business", "design"}


@dataclass
class ModelCandidate:
    id: str  # provider:model
    provider: str
    model: str
    display: str
    locality: str  # local | lan | external
    cost_class: str
    family: str = ""
    parameters_b: float | None = None
    context: int | None = None
    languages: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    usd_in_per_mtok: float = 0.0
    usd_out_per_mtok: float = 0.0
    version: str = ""
    licence: str = ""
    approved: bool = True
    notes: str = ""

    def est_cost(self, in_tokens: int, out_tokens: int) -> float:
        return round(in_tokens / 1e6 * self.usd_in_per_mtok + out_tokens / 1e6 * self.usd_out_per_mtok, 6)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _params(s: str) -> float | None:
    m = re.match(r"([\d.]+)\s*([bm])", (s or "").lower())
    if not m:
        return None
    v = float(m.group(1))
    return v / 1000 if m.group(2) == "m" else v


def _cost_class(out_price: float, *, local: bool, free_tier: bool, open_endpoint: bool) -> str:
    if local:
        return "local"
    if free_tier:
        return "free_tier"
    if open_endpoint:
        return "open_endpoint"
    return "low_cost" if out_price <= 1.0 else "premium"


def available_models(db: Session) -> list[ModelCandidate]:
    """Every model this deployment could call — installed local chat models, LAN workers, Ollama, registry APIs."""
    import os

    from ..ai import registry
    from ..models import LocalModel, ProviderRecord

    out: list[ModelCandidate] = []
    for m in db.scalars(select(LocalModel).where(LocalModel.status == "installed", LocalModel.kind == "chat")).all():
        out.append(ModelCandidate(f"local:{m.key}", "local", m.key, m.display_name, "local", "local", m.family, _params(m.parameters),
                                  m.context_length, list(m.languages or []), list(m.capabilities or ["text"]),
                                  version=(m.sha256_actual or m.sha256_expected or "")[:16], licence=m.license,
                                  notes=f"{m.parameters} {m.quantization}".strip()))
    try:
        from ..daemon.workers import active_worker_providers

        for pid, p in active_worker_providers().items():
            model = getattr(p, "default_model", "") or "default"
            out.append(ModelCandidate(f"{pid}:{model}", pid, model, f"{model} (LAN worker)", getattr(p, "locality", "lan"), "local",
                                      capabilities=["text"], notes="self-hosted worker"))
    except Exception as e:  # noqa: BLE001 — workers table may be absent in minimal setups
        log.debug("LAN workers unavailable: %s", e)
    for m in [x.strip() for x in os.getenv("OLLAMA_MODELS", "").split(",") if x.strip()]:
        out.append(ModelCandidate(f"ollama:{m}", "ollama", m, f"{m} (Ollama)", "local", "local", capabilities=["text", "structured_output"]))
    recs = {r.id: r for r in db.scalars(select(ProviderRecord))}
    for spec in registry.ANTHROPIC:
        rec = recs.get(spec.provider)
        ft = str((rec.facts or {}).get("free_tier", "")) if rec else ""
        verified_free = bool(rec and rec.status == "operational" and ft and not ft.startswith(("none", "unknown")))
        out.append(ModelCandidate(f"{spec.provider}:{spec.model_id}", spec.provider, spec.model_id, spec.display_name, "external",
                                  _cost_class(spec.output_usd_per_mtok or 0, local=False, free_tier=verified_free, open_endpoint=False),
                                  "claude", None, spec.context_window, ["multilingual", "en", "sv"], list(spec.capabilities),
                                  spec.input_usd_per_mtok or 0.0, spec.output_usd_per_mtok or 0.0, version=spec.model_id,
                                  approved=bool(rec and rec.adapter and rec.status == "operational"), notes=spec.intended_use))
    return out


# ------------------------------------------------------------------ task analysis
_CAT_PATTERNS = [
    ("songwriting", r"\b(song|lyrics?|chorus|verse|refr[äa]ng|l[åa]t(text)?|vers|visa|sångtext)\b"),
    ("poetry", r"\b(poem|poetry|haiku|sonnet|dikt|poesi)\b"),
    ("storytelling", r"\b(story|tale|narrative|fable|ber[äa]ttelse|saga|novell)\b"),
    ("programming", r"\b(code|function|bug|api|python|typescript|sql|refactor|kod|funktion)\b"),
    ("translation", r"\b(translate|translation|översätt|översättning)\b"),
    ("summarization", r"\b(summari[sz]e|summary|tl;?dr|sammanfatta|sammanfattning)\b"),
    ("research", r"\b(research|sources?|evidence|studies|forskning|källor)\b"),
    ("business", r"\b(business idea|business model|startup|pricing|affärsid[eé]|affärsmodell|prissättning)\b"),
    ("design", r"\b(design|logo|brand identity|ux|ui|layout|formgivning)\b"),
    ("brainstorming", r"\b(ideas?|brainstorm|names?|slogans?|taglines?|id[eé]er|namnförslag)\b"),
    ("reasoning", r"\b(why|prove|calculate|plan|step by step|varför|beräkna|resonera)\b"),
]
_SV = re.compile(r"\b(och|jag|det|att|en|är|på|som|för|med|inte|om|till|av|vi|du|skriv|en låt|om)\b", re.I)


def language_of(text: str) -> str:
    words = re.findall(r"[A-Za-zÅÄÖåäö]+", text or "")
    if not words:
        return "en"
    sv = len(_SV.findall(text)) + 2 * len(re.findall(r"[åäöÅÄÖ]", text))
    return "sv" if sv / max(1, len(words)) > 0.18 else "en"


def analyze(brief: str) -> dict[str, Any]:
    b = (brief or "").lower()
    category = next((c for c, pat in _CAT_PATTERNS if re.search(pat, b)), "general")
    words = len(b.split())
    complexity = "high" if words > 80 or category in ("programming", "research") else "medium" if words > 15 or category in CREATIVE else "low"
    needs = ["text"]
    if re.search(r"\b(image|picture|photo|bild|foto)\b.*\b(generate|create|draw|skapa|rita)\b|\b(generate|create|draw|skapa|rita)\b.*\b(image|picture|bild)\b", b):
        needs.append("image_generation")
    if re.search(r"\b(music|melody|audio|sound|musik|melodi|ljud)\b.*\b(generate|produce|create|skapa)\b", b):
        needs.append("audio_generation")
    if words > 3000:
        needs.append("long_context")
    max_tokens = {"songwriting": 420, "poetry": 260, "storytelling": 700, "brainstorming": 350, "summarization": 300,
                  "programming": 900, "research": 700, "business": 500, "design": 450}.get(category, 400)
    return {"category": category, "language": language_of(brief), "complexity": complexity, "needs": needs, "max_tokens": max_tokens}


# ------------------------------------------------------------------ performance profiles
def profiles(db: Session, model_ids: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """Latest measured profile per (model, category): {model_id: {category: {...}}}."""
    from ..models import ModelProfile

    q = select(ModelProfile).order_by(ModelProfile.measured_at.desc())
    if model_ids is not None:
        q = q.where(ModelProfile.model_id.in_(model_ids or ["-"]))
    out: dict[str, dict[str, Any]] = {}
    for p in db.scalars(q):
        out.setdefault(p.model_id, {}).setdefault(p.category, {"score": p.score, "metrics": p.metrics or {}, "tasks": p.tasks,
                                                               "version": p.model_version, "measured_at": p.measured_at, "source": p.source})
    return out


def _prior(c: ModelCandidate) -> float:
    """Quality guess for a model never measured on this category — clearly labelled as a prior, from size/class only."""
    if c.cost_class in ("low_cost", "premium", "free_tier"):
        return 0.75 if c.cost_class == "premium" else 0.6
    p = c.parameters_b or 1.0
    return round(min(0.65, 0.25 + 0.12 * math.log2(1 + p)), 3)


def quality_for(c: ModelCandidate, category: str, profs: dict[str, dict[str, Any]]) -> tuple[float, str, bool]:
    """(quality 0..1, explanation, stale?) — measured for this category if possible, then general, else a prior."""
    p = profs.get(c.id, {})
    for cat in dict.fromkeys((category, "general", "overall")):
        if cat in p:
            stale = bool(c.version and p[cat]["version"] and p[cat]["version"] != c.version)
            note = f"{cat} {p[cat]['score']:.2f} measured on {p[cat]['tasks']} task(s)" + (" — model changed since: re-benchmark" if stale else "")
            return float(p[cat]["score"]) * (0.85 if stale else 1.0), note, stale
    return _prior(c), f"prior {_prior(c):.2f} (no {category} measurement yet)", False


def _latency(c: ModelCandidate, profs: dict[str, dict[str, Any]]) -> tuple[float, bool]:
    """(latency ms, measured?) — measured average, else a rough size-based estimate (labelled as such)."""
    vals = [v["metrics"].get("latency_ms") for v in profs.get(c.id, {}).values() if v["metrics"].get("latency_ms")]
    if vals:
        return sum(vals) / len(vals), True
    if c.locality == "external":
        return 4000.0, False
    return 2000.0 + 4000.0 * (c.parameters_b or 1.5), False  # CPU inference grows with model size


def active_router() -> Any:
    """The router to use: an installed override that is itself a router (tests, alternative setups), else the default."""
    from ..ai.llm import get_provider, get_router
    from ..ai.router import LLMRouter

    p = get_provider()
    return p if isinstance(p, LLMRouter) else get_router()


# ------------------------------------------------------------------ selection
def choose_models(db: Session, brief: str, *, mode: str = "FREE_FIRST", n: int = 1, sensitivity: str = "normal", category: str | None = None,
           exclude: set[str] | None = None, max_usd_per_call: float | None = None, allowed_cost_classes: list[str] | None = None,
           router: Any | None = None) -> dict[str, Any]:
    """Rank the models allowed to do this task. Every candidate passes the same per-model policy as tier routing.
    Returns {task, mode, ranked: [{candidate, score, quality, est_cost_usd, latency_ms, why}], excluded: [...]}."""
    from ..daemon import policy

    mode = (mode or "FREE_FIRST").upper().replace("-", "_")
    if mode not in MODES:
        raise ValueError(f"routing mode must be one of {MODES}")
    task = analyze(brief)
    if category:
        task["category"] = category
    router = router or active_router()
    providers = router._all_providers()  # noqa: SLF001 — the router's own view of configured providers + workers
    cands = available_models(db)
    profs = profiles(db, [c.id for c in cands])
    ranked: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    in_tok = len(brief) // 3 + 200
    for c in cands:
        why_not = None
        if exclude and c.id in exclude:
            continue
        if not c.approved:
            why_not = "provider not approved for routing (unverified)"
        elif any(need not in c.capabilities and need != "text" for need in task["needs"]):
            why_not = f"lacks capability: {', '.join(n_ for n_ in task['needs'] if n_ not in c.capabilities)}"
        elif mode == "PRIVACY_FIRST" and c.locality != "local":
            why_not = "PRIVACY_FIRST keeps everything on this machine"
        elif allowed_cost_classes and c.cost_class not in allowed_cost_classes:
            why_not = f"cost class {c.cost_class} not allowed for this task"
        else:
            prov = providers.get(c.provider)
            if prov is None or not prov.configured():
                why_not = "not configured (no key / runtime)"
            else:
                _cand, ex = policy.check_candidate(c.provider, c.model, providers, sensitivity=sensitivity)
                if ex:
                    why_not = ex["status"].replace("_", " ")
                elif hasattr(router, "breakers") and router.breakers.get(c.provider) and router.breakers[c.provider].is_open():
                    why_not = "circuit open (provider failing)"
        est = c.est_cost(in_tok, task["max_tokens"])
        if why_not is None and max_usd_per_call is not None and est > max_usd_per_call:
            why_not = f"estimated ${est:.4f} per call exceeds the budget"
        if why_not:
            excluded.append({"model": c.id, "why": why_not})
            continue
        q, qnote, stale = quality_for(c, task["category"], profs)
        lat, lat_measured = _latency(c, profs)
        speed = 1 / (1 + lat / 10000)
        cost_units = est / 0.01
        locality = {"local": 1.0, "lan": 0.7}.get(c.locality, 0.0)
        tier_bonus = {"local": 0.15, "free_tier": 0.15, "open_endpoint": 0.1, "low_cost": 0.05, "premium": 0.0}[c.cost_class]
        score = {
            "FREE_FIRST": q * 0.7 + tier_bonus + speed * 0.1 - min(0.3, cost_units * 0.02),
            "BEST_QUALITY": q * 0.95 + speed * 0.05,
            "BEST_VALUE": q / (1 + cost_units + lat / 60000),
            "FASTEST": speed * 0.7 + q * 0.3,
            "LOCAL_FIRST": locality * 0.5 + q * 0.5,
            "PRIVACY_FIRST": q,
            "CREATIVE_ENSEMBLE": q / (1 + cost_units),
            "DEEP_RESEARCH": q * 0.8 + (0.2 if (c.context or 0) >= 32000 else 0.0),
            "SPECIALIST": q + (0.3 if task["category"] in profs.get(c.id, {}) else 0.0),
            "BALANCED": q * 0.5 + (1 - min(1.0, cost_units * 0.05)) * 0.25 + speed * 0.25,
        }[mode]
        why = [qnote, f"{c.cost_class.replace('_', ' ')} ({c.locality})", f"~${est:.4f}/call" if est else "no API cost",
               f"~{lat / 1000:.1f} s {'measured' if lat_measured else 'estimated from size'}"]
        ranked.append({"model": c.id, "candidate": c.as_dict(), "score": round(score, 4), "quality": round(q, 3), "stale_profile": stale,
                       "est_cost_usd": est, "latency_ms": round(lat), "latency_measured": lat_measured, "why": "; ".join(why)})
    ranked.sort(key=lambda r: r["score"], reverse=True)
    if mode == "CREATIVE_ENSEMBLE" and n > 1:  # diversity: different families first
        picked, fams = [], set()
        for r in ranked:
            fam = r["candidate"]["family"] or r["model"]
            if fam not in fams:
                picked.append(r)
                fams.add(fam)
        ranked = picked + [r for r in ranked if r not in picked]
    return {"task": task, "mode": mode, "mode_info": MODE_INFO[mode], "ranked": ranked, "excluded": excluded,
            "chosen": [r["model"] for r in ranked[:n]],
            "explanation": (f"{ranked[0]['model']} first for {task['category']} under {mode}: {ranked[0]['why']}" if ranked
                            else "no permitted model can do this task here")}


# ------------------------------------------------------------------ governed call
def call_model(db: Session, model_id: str, *, system: str, prompt: str, max_tokens: int, sensitivity: str = "normal",
               user_email: str | None = None, agent_id: str | None = None, workflow: str = "creative", purpose: str = "creative",
               router: Any | None = None) -> dict[str, Any]:
    """One call to one chosen model: budgets reserved before (refused → BudgetExceeded), settled after; every attempt traced."""
    from ..ai import tracing
    from ..ai.router import LLMUnavailable
    from ..governance import budgets

    provider, _, model = model_id.partition(":")
    router = router or active_router()
    hold = budgets.reserve(db, user_email=user_email, agent_id=agent_id, workflow=workflow,
                           est_tokens=(len(system) + len(prompt)) // 4 + max_tokens)
    db.commit()  # the reservation is committed before the (slow) call: concurrent callers see it
    try:
        r = router.complete_on(provider, model, system=system, prompt=prompt, max_tokens=max_tokens, sensitivity=sensitivity)
    except LLMUnavailable as e:
        budgets.release(db, hold)
        tracing.record(db, e.attempts, agent_id=agent_id or "", purpose=purpose, workflow=workflow)
        db.commit()
        raise
    except Exception as e:
        budgets.release(db, hold)
        tracing.record(db, getattr(e, "attempts", []) or [], agent_id=agent_id or "", purpose=purpose, workflow=workflow)
        db.commit()
        raise
    budgets.settle(db, hold, tokens=r.input_tokens + r.output_tokens, usd=r.cost_usd)
    tracing.record(db, r.attempts, agent_id=agent_id or "", purpose=purpose, workflow=workflow)
    db.commit()
    return {"text": r.text or "", "model": r.model, "provider": r.provider or provider, "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens, "cost_usd": r.cost_usd, "latency_ms": r.latency_ms}
