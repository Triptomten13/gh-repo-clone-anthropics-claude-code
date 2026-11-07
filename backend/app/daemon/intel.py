"""DAEMON Intelligence Orchestrator: decide HOW a request should be solved before spending anything on it.

Order of preference (cheapest reliable first):
  1. deterministic solver (no model)          5. small local model (fast tier)
  2. exact / semantic cache of a verified answer 6. standard local model
  3. internal knowledge (Archive, grounded)    7. local reasoning model (deep tier, optional self-consistency)
  4. internet research at the needed depth     8. multi-agent G-sus run (only when the work really needs several agents)
Capabilities that do not exist here (vision, speech) are reported as unavailable — never imitated.
The classifier is rule-based (no model call), evaluated by evals/datasets/intel_routing.json.
"""
from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

CATEGORIES = ("simple_fact", "calculation", "data_transformation", "classification", "summarization", "research", "programming",
              "creative", "complex_reasoning", "planning", "document_analysis", "image_understanding", "audio_processing",
              "long_running_workflow")

R = lambda p: re.compile(p, re.I)  # noqa: E731
CURRENT = R(r"\b(latest|newest|current(?:ly)?|today|right now|this (?:week|month|year)|recent(?:ly)?|news|nyheter|senaste|price of|"
            r"stock price|exchange rate|weather|released?|release notes|new version|cve-\d{4}|vulnerabilit|20(?:2[5-9]|3\d))\b")
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("image_understanding", R(r"\b(image|photo|picture|screenshot|diagram)\b.*\b(describe|what|analy[sz]e|read|ocr)|\.(png|jpe?g|webp|gif)\b")),
    ("audio_processing", R(r"\b(transcribe|transcription|audio|podcast|voice ?memo|speech[- ]to[- ]text)\b|\.(mp3|wav|m4a|ogg)\b")),
    ("long_running_workflow", R(r"\b(monitor|keep (?:an eye|track)|watch for|every (?:day|week|morning|hour)|notify me when|"
                                r"convene (?:a )?council|evaluate the pipeline|launch|run the (?:pipeline|workflow))\b")),
    ("programming", R(r"```|\b(python|javascript|typescript|sql|regex|bash|rust|golang|java|function|stack ?trace|traceback|bug|refactor|"
                      r"compile|unit test|api endpoint|class \w+|def \w+)\b")),
    ("data_transformation", R(r"\b(convert|transform|reformat|format) (?:this|the following|it|these)?\s*(?:to|into|as)?\s*(json|csv|yaml|xml|"
                              r"markdown|table)|\bto (json|csv|yaml)\b|\b(sort|deduplicate|uppercase|lowercase) (?:this|these|the following)\b")),
    ("classification", R(r"\b(classify|categori[sz]e|label|sentiment|is (?:this|it) (?:spam|positive|negative)|which category)\b")),
    ("summarization", R(r"\b(summari[sz]e|summary of|tl;?dr|sammanfatta|key points|condense)\b")),
    ("document_analysis", R(r"\b(this|the|my|our|uploaded|attached) (document|pdf|file|report|contract|archive|notes|records)s?\b|"
                            r"\bin (?:the|our) (?:archive|documents)\b")),
    ("research", R(r"\b(research|investigate|find (?:sources|papers|evidence)|literature|papers? on|studies on|compare sources|"
                   r"what does the (?:evidence|research) say|state of the art|survey of)\b")),
    ("creative", R(r"\b(poem|story|lyrics|slogan|tagline|brand (?:name|concept)s?|names? for|creative|jingle|haiku|write a (?:song|tale))\b")),
    ("planning", R(r"\b(plan|roadmap|schedule|itinerary|steps to|how (?:do|should) (?:i|we) (?:get|go about)|strategy for|checklist)\b")),
    ("complex_reasoning", R(r"\b(why|prove|explain how|trade-?offs?|should (?:we|i)|pros and cons|step by step|puzzle|riddle|logic|"
                            r"what would happen|which is cheaper|how much (?:more|less|cheaper)|profit|margin|break[- ]even)\b")),
    ("simple_fact", R(r"^\s*(who|what|when|where|which|how (?:many|much|old|tall|far|long))\b|\b(capital of|population of|definition of|meaning of)\b")),
]


@dataclass
class Classification:
    category: str
    needs_current_info: bool
    complexity: str  # low | medium | high
    signals: list[str] = field(default_factory=list)
    confidence: float = 0.6


@dataclass
class Plan:
    strategy: str  # deterministic | cache | archive | research | model_fast | model_standard | model_deep | gsus | unavailable
    tier: str | None = None
    research_depth: str | None = None
    samples: int = 1
    reason: str = ""
    rejected: list[str] = field(default_factory=list)


DEEP_WORDS = R(r"\b(in[- ]depth|comprehensive|thorough|deep research|literature review|systematic|survey of)\b")


def classify(q: str) -> Classification:
    from .deterministic import solve

    text = q.strip()
    sig: list[str] = []
    current = bool(CURRENT.search(text))
    if current:
        sig.append("time-sensitive wording")
    if solve(text):
        return Classification("calculation", False, "low", ["deterministic solver matched"], 0.95)
    cat = None
    for name, pat in PATTERNS:
        if pat.search(text):
            cat = name
            sig.append(f"pattern:{name}")
            break
    nums = re.findall(r"\d+(?:[.,]\d+)?", text)
    if cat in (None, "simple_fact") and len(nums) >= 2 and re.search(r"\?|how much|what is the|calculate", text, re.I):
        cat, sig = "complex_reasoning", sig + ["multi-number word problem"]
    if cat is None:
        cat = "research" if current else ("simple_fact" if len(text) < 120 and text.endswith("?") else "complex_reasoning")
        sig.append("fallback")
    words = len(text.split())
    if DEEP_WORDS.search(text) and cat in ("simple_fact", "complex_reasoning", "research", "summarization"):
        sig.append("deep research wording")
        return Classification("research", current, "deep", sig, 0.8)
    complexity = "high" if cat in ("complex_reasoning", "planning", "research", "programming", "long_running_workflow") or words > 120 else \
        ("low" if cat in ("simple_fact", "classification", "calculation", "data_transformation") and words < 60 else "medium")
    return Classification(cat, current, complexity, sig, 0.8 if "fallback" not in sig else 0.5)


def plan(c: Classification, *, offline: bool, has_local: dict[str, bool], research_depth: str | None = None) -> Plan:
    cat = c.category
    if cat == "calculation":
        return Plan("deterministic", reason="a deterministic solver answers this exactly; no model needed")
    if cat in ("image_understanding", "audio_processing"):
        return Plan("unavailable", reason=f"no local {'vision' if cat.startswith('image') else 'speech'} model is installed; "
                                          "this request is not imitated with a text model")
    if cat == "long_running_workflow":
        return Plan("gsus", reason="needs planning, several agents or scheduling — G-sus orchestrates it with approvals")
    if c.needs_current_info or cat == "research":
        depth = research_depth or ("deep" if DEEP_WORDS.search(" ".join(c.signals) + " " + c.category) or c.complexity == "deep" else
                                   "standard" if cat == "research" else "quick")
        if offline:
            return Plan("archive", reason="current information requested but offline mode is on — answering from the Archive only and saying so",
                        rejected=["research: offline mode"])
        return Plan("research", research_depth=depth, reason=f"current or external facts matter — search before guessing ({depth})")
    if cat == "document_analysis":
        return Plan("archive", reason="the answer lives in internal documents; grounded retrieval with citations")
    if cat == "simple_fact":
        return Plan("archive", reason="check internal knowledge first; escalate to a QUICK lookup only if the Archive has nothing",
                    rejected=["model-only: a small model's recall of facts is unreliable"])
    if cat in ("classification", "data_transformation", "summarization"):
        tier = "fast" if c.complexity == "low" else "standard"
        return Plan(f"model_{tier}", tier=tier, reason=f"{cat.replace('_', ' ')} is routine work for a small local model",
                    rejected=["deep model: unnecessary for this task"])
    if cat in ("creative", "programming"):
        return Plan("model_standard", tier="standard", reason=f"{cat} needs fluent generation; the standard local model is adequate",
                    rejected=["deep model: slower, no reasoning benefit expected"])
    if cat in ("complex_reasoning", "planning"):
        if has_local.get("deep"):
            return Plan("model_deep", tier="deep", samples=1, reason="multi-step reasoning: the local reasoning model solves 7/7 benchmark problems "
                                                                    "vs 1–2/7 for the small models", rejected=["small models: fail most multi-step problems"])
        return Plan("model_standard", tier="standard", reason="no reasoning model active — standard model, lower confidence")
    return Plan("model_standard", tier="standard", reason="default")


def answer(db: Any, user: Any, question: str, *, research_depth: str | None = None, samples: int = 1, force_strategy: str | None = None,
           sensitivity: str = "normal") -> dict[str, Any]:
    from . import gateway, library, prompts, semantic_cache, state
    from .deterministic import solve

    t0 = time.monotonic()
    st = state.load(db)
    c = classify(question)
    has_local = {s: library.resolve(db, s) is not None for s in ("eco", "chat", "deep")}
    p = plan(c, offline=st["offline_mode"], has_local=has_local, research_depth=research_depth)
    if force_strategy:
        p = Plan(force_strategy, tier={"model_fast": "fast", "model_standard": "standard", "model_deep": "deep"}.get(force_strategy),
                 research_depth=research_depth or "quick", reason="strategy forced by the caller")
    if samples > 1 and p.strategy == "model_deep":
        p.samples = samples
    trace: list[dict[str, Any]] = [{"step": "classify", **asdict(c)}, {"step": "plan", **asdict(p)}]
    out: dict[str, Any] = {"question": question, "classification": asdict(c), "plan": asdict(p), "trace": trace}

    def done(**kw: Any) -> dict[str, Any]:
        out.update(kw)
        out["latency_ms"] = int((time.monotonic() - t0) * 1000)
        return out

    if p.strategy == "deterministic":
        r = solve(question)
        return done(answer=r["answer"], method=r["method"], model_calls=0, cost_usd=0.0, evidence_class="computed")
    if p.strategy == "unavailable":
        return done(answer=None, status="unavailable", note=p.reason, model_calls=0, cost_usd=0.0)

    # L2/L3: a previously verified answer to the same (or a near-identical) stable question
    if not c.needs_current_info and sensitivity == "normal" and p.strategy in ("archive", "model_fast", "model_standard"):
        hit = semantic_cache.lookup(db, question, category=c.category, scope="global")
        trace.append({"step": "cache", "hit": bool(hit), **({"similarity": hit["similarity"], "layer": hit["layer"]} if hit else {})})
        if hit:
            return done(answer=hit["answer"], sources=hit.get("sources", []), cached=True, cache_layer=hit["layer"], model_calls=0, cost_usd=0.0)

    if p.strategy == "archive":
        from ..knowledge.search import grounded_answer

        g = grounded_answer(db, question, k=6, llm=None, user=user)
        cites = g.get("citations") or []
        trace.append({"step": "archive", "citations": len(cites), "supported": g.get("grounding", {}).get("supported")})
        if cites and g.get("answer") and g.get("grounding", {}).get("supported", True):
            from ..knowledge.vault import readable_ids

            ids = {x["document_id"] for x in cites}
            if readable_ids(db, None, list(ids)) == ids:  # shared cache only for answers anyone may read
                semantic_cache.store(db, question, g["answer"], category=c.category, sources=cites, verified=True, ttl_days=7)
            return done(answer=g["answer"], sources=cites, evidence="internal Archive (grounded, extractive)", model_calls=0, cost_usd=0.0)
        if not st["offline_mode"] and c.category == "simple_fact":
            p = Plan("research", research_depth="quick", reason="nothing in the Archive — QUICK external lookup")
            trace.append({"step": "escalate", "to": "research:quick", "why": "no supported Archive answer"})
        else:
            return done(answer=None, status="unknown", note="No supporting evidence in the Archive" +
                        (" and offline mode prevents an external lookup." if st["offline_mode"] else "."), model_calls=0, cost_usd=0.0)

    if p.strategy == "research":
        from ..internet import research

        r = research.run(db, question, depth=p.research_depth or "quick", actor=getattr(user, "email", "system"))
        trace.append({"step": "research", "run_id": r.get("run_id"), "sources": len(r.get("sources", [])), "cached": r.get("cached")})
        return done(answer=r.get("answer"), sources=r.get("sources", []), research=r, model_calls=r.get("model_calls", 0),
                    cost_usd=r.get("cost_usd", 0.0), status=r.get("status"))

    if p.strategy == "gsus":
        from ..gsus import engine as gsus

        run = gsus.start(db, question, "gsus", {}, getattr(user, "email", "system"))
        return done(answer=run.answer if getattr(run, "answer", None) else None, gsus_run_id=run.id, status=run.status,
                    note="multi-agent run — see the G-sus Chamber for steps and approvals")

    system = prompts.active(db, "gsus.identity").text
    tier = p.tier or "standard"
    if tier == "deep":
        from . import consistency

        runs = []
        for _ in range(max(1, p.samples)):
            runs.append(gateway.complete(db, system=system, prompt=question, tier="deep", max_tokens=1200, sensitivity=sensitivity,
                                         purpose="ai.ask", workflow=c.category))
            if p.samples > 1 and consistency.settled([x["text"] for x in runs], p.samples):
                break
        chosen = runs[consistency.vote([x["text"] for x in runs])["index"]] if len(runs) > 1 else runs[0]
        return done(answer=chosen["text"], model=chosen["model"], provider=chosen["provider"], model_calls=len(runs),
                    cost_usd=round(sum(x["cost_usd"] for x in runs), 6), reasoning_complete=not chosen.get("reasoning_truncated"),
                    self_consistency=consistency.vote([x["text"] for x in runs]) if len(runs) > 1 else None)
    r = gateway.complete(db, system=system, prompt=question, tier=tier, max_tokens=900, sensitivity=sensitivity, purpose="ai.ask",
                         workflow=c.category, cacheable=not c.needs_current_info)
    return done(answer=r["text"], model=r["model"], provider=r["provider"], model_calls=0 if r.get("served_from_cache") else 1,
                cost_usd=r["cost_usd"], cached=r.get("served_from_cache", False), evidence_class="model output — unverified")
