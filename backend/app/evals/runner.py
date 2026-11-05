"""AI evaluation harness. Deterministic suites always run; LLM suites run only when a provider is
configured (and are reported as skipped otherwise — never as passed)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

DATA = Path(__file__).parent / "datasets"


def _load(name: str) -> Any:
    return json.loads((DATA / name).read_text())


def planner_suite() -> dict[str, Any]:
    from ..gsus.engine import detect_intents

    cases = _load("planner.json")
    fails = []
    for c in cases:
        got = set(detect_intents(c["objective"]))
        if not set(c["expect"]) <= got:
            fails.append({"objective": c["objective"], "expected": c["expect"], "got": sorted(got)})
    return {"suite": "planner_intents", "cases": len(cases), "score": round(1 - len(fails) / len(cases), 3), "failures": fails,
            "metric": "expected intents ⊆ detected intents", "requires_llm": False}


def intel_routing_suite() -> dict[str, Any]:
    """Does the orchestrator pick the cheapest reliable strategy? (category, time-sensitivity, strategy, research depth)"""
    from ..daemon import intel

    cases = _load("intel_routing.json")
    fails = []
    for c in cases:
        cl = intel.classify(c["q"])
        pl = intel.plan(cl, offline=False, has_local={"eco": True, "chat": True, "deep": True})
        got = {"category": cl.category, "current": cl.needs_current_info, "strategy": pl.strategy, "depth": pl.research_depth}
        want = {k: c[k] for k in ("category", "current", "strategy", "depth") if k in c}
        if any(got[k] != v for k, v in want.items()):
            fails.append({"q": c["q"], "expected": want, "got": {k: got[k] for k in want}})
    return {"suite": "intel_routing", "cases": len(cases), "score": round(1 - len(fails) / len(cases), 3), "failures": fails,
            "metric": "classification + chosen strategy match the expected cheapest reliable route", "requires_llm": False}


def injection_suite() -> dict[str, Any]:
    from ..security.untrusted import detect

    cases = _load("injection.json")
    tp = fp = fn = tn = 0
    misses = []
    for c in cases:
        hit = bool(detect(c["text"]))
        tp += hit and c["flag"]
        fp += hit and not c["flag"]
        fn += (not hit) and c["flag"]
        tn += (not hit) and not c["flag"]
        if hit != c["flag"]:
            misses.append(c["text"])
    prec = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / (tp + fn) if tp + fn else 1.0
    return {"suite": "injection_detection", "cases": len(cases), "precision": round(prec, 3), "recall": round(rec, 3),
            "score": round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0.0, "failures": misses, "metric": "F1", "requires_llm": False}


def originality_suite() -> dict[str, Any]:
    from ..flare.originality import score_concept

    cases = _load("originality.json")
    fails = [c["concept"]["name"] for c in cases if score_concept(c["concept"], novel_hybrid=True).requires_revision != c["revise"]]
    return {"suite": "anti_generic_gate", "cases": len(cases), "score": round(1 - len(fails) / len(cases), 3), "failures": fails,
            "metric": "gate decision accuracy", "requires_llm": False}


def _isolated_archive():
    from .. import models  # noqa: F401
    from ..db import Base
    from ..knowledge import process
    from ..knowledge.extract import Extracted

    eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    data = _load("retrieval.json")
    for d in data["corpus"]:
        process.ingest(db, Extracted("txt", "text/plain", d["text"]), {"title": d["title"], "evidence_class": d["evidence_class"]})
    db.commit()
    return db, data


def retrieval_suite() -> dict[str, Any]:
    from ..knowledge import search

    db, data = _isolated_archive()
    hits3 = label_ok = 0
    fails = []
    t0 = time.monotonic()
    for q in data["questions"]:
        res = search.search(db, q["q"], k=3)
        titles = [r["title"] for r in res]
        if q["expect_title"] in titles:
            hits3 += 1
            if next(r for r in res if r["title"] == q["expect_title"])["evidence_class"] == q["expect_class"]:
                label_ok += 1
        else:
            fails.append({"q": q["q"], "got": titles})
    abstain = sum(1 for q in data["unanswerable"] if not search.search(db, q, k=3))
    latency = (time.monotonic() - t0) * 1000 / max(1, len(data["questions"]))
    n = len(data["questions"])
    db.close()
    return {"suite": "retrieval_grounding", "cases": n, "recall_at_3": round(hits3 / n, 3), "evidence_label_accuracy": round(label_ok / n, 3),
            "abstention_on_unanswerable": f"{abstain}/{len(data['unanswerable'])}", "avg_latency_ms": round(latency, 1),
            "score": round((hits3 / n + abstain / len(data["unanswerable"])) / 2, 3), "failures": fails,
            "metric": "mean of recall@3 and abstention rate (extractive answers cite only retrieved passages by construction)",
            "requires_llm": False}


def llm_grounding_suite() -> dict[str, Any]:
    from ..ai.llm import LLMRefused, LLMUnavailable, get_provider
    from ..knowledge import search

    provider = get_provider()
    if getattr(provider, "name", "none") == "none":
        return {"suite": "llm_grounding", "skipped": True, "reason": "no AI provider configured", "requires_llm": True}
    db, data = _isolated_archive()
    valid = cited = refused_unknown = 0
    cost = 0.0
    model = None
    for q in data["questions"]:
        try:
            ans = search.grounded_answer(db, q["q"], llm=lambda s, p: provider.complete(system=s, prompt=p, tier="fast"))
        except (LLMUnavailable, LLMRefused) as e:
            db.close()
            return {"suite": "llm_grounding", "skipped": True, "reason": str(e), "requires_llm": True}
        r = ans.get("llm_result")
        cost += getattr(r, "cost_usd", 0.0)
        model = getattr(r, "model", model)
        g = ans["grounding"]
        cited += not g.get("uncited_answer", True)
        valid += not g.get("invalid_citations")
    for q in data["unanswerable"]:
        ans = search.grounded_answer(db, q, llm=lambda s, p: provider.complete(system=s, prompt=p, tier="fast"))
        refused_unknown += ans["method"] == "extractive" or "not" in ans["answer"].lower()
    n = len(data["questions"])
    db.close()
    return {"suite": "llm_grounding", "model": model, "cases": n, "citation_rate": round(cited / n, 3), "citation_validity": round(valid / n, 3),
            "abstention": f"{refused_unknown}/{len(data['unanswerable'])}", "cost_usd": round(cost, 6), "score": round(valid / n, 3),
            "requires_llm": True}


def run_all(include_llm: bool = False) -> dict[str, Any]:
    t0 = time.time()
    suites = [planner_suite(), intel_routing_suite(), injection_suite(), originality_suite(), retrieval_suite()]
    if include_llm:
        suites.append(llm_grounding_suite())
    return {"ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "duration_s": round(time.time() - t0, 2), "suites": suites}
