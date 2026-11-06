"""DAEMON MODEL PERFORMANCE INTELLIGENCE — how good is each model at the work Demonkoncernen actually does?

Profiles are measured, per model VERSION and per task category, on a fixed, versioned dataset of realistic tasks
(Swedish and English songwriting, poetry, product-name brainstorming, storytelling, summaries, business ideas, code,
translation). Scores are deterministic (quality.deterministic) so a run is reproducible; the conditions (dataset
version, token limit, hardware, scoring method) are stored with every profile. A profile whose model file or API
model id changed is STALE: the selector discounts it and `due()` lists the model for re-benchmarking.
Marketing claims and parameter counts are not scores — an unmeasured model gets an explicitly labelled prior.
"""
from __future__ import annotations

import platform
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import quality
from .providers import available_models, profiles

DATASET_VERSION = "creative-bench-2026-11-06"
SYSTEM = "You are a skilled writer and engineer. Follow the brief exactly. Output only the requested work, no preamble."

TASKS: list[dict[str, Any]] = [
    {"id": "song-sv", "category": "songwriting", "max_tokens": 360,
     "prompt": "Skriv en kort låttext på svenska om vinterns första snö i en liten norrländsk by. Två verser och en refräng, "
               "markera dem med Vers 1, Refräng, Vers 2. Gärna rim."},
    {"id": "song-en", "category": "songwriting", "max_tokens": 360,
     "prompt": "Write short song lyrics in English about a night-shift bus driver who loves the empty city. Two verses and a "
               "chorus, labelled Verse 1, Chorus, Verse 2. Use rhyme."},
    {"id": "poem-sv", "category": "poetry", "max_tokens": 200,
     "prompt": "Skriv en dikt på svenska, högst åtta rader, om en gammal fyr vid Kattegatt. Undvik klichéer."},
    {"id": "poem-en", "category": "poetry", "max_tokens": 200,
     "prompt": "Write a poem in English, at most eight lines, about a reflective bicycle pannier in autumn rain. Avoid clichés."},
    {"id": "names-en", "category": "brainstorming", "max_tokens": 220,
     "prompt": "Give 8 distinct brand names for a waterproof commuter pannier with reflective panels. A numbered list, names only."},
    {"id": "names-sv", "category": "brainstorming", "max_tokens": 220,
     "prompt": "Ge 6 olika namnförslag på svenska för en handvevad nödradio för friluftsliv. Numrerad lista, bara namnen."},
    {"id": "story-en", "category": "storytelling", "max_tokens": 360,
     "prompt": "Write a 120-word story in English about a lighthouse keeper who finds a radio that only receives tomorrow's weather."},
    {"id": "biz-en", "category": "business", "max_tokens": 320,
     "prompt": "List 5 business ideas for selling refurbished e-scooter batteries in Sweden. Numbered list, one sentence each."},
    {"id": "sum-en", "category": "general", "max_tokens": 160,
     "prompt": "Summarize in two sentences: The magnetic LED reading lamp sold 1,200 units in October. Returns were 3 %, "
               "mostly because the clip broke. Reviews praise the warm light but ask for a longer battery."},
    {"id": "code-py", "category": "programming", "max_tokens": 300,
     "prompt": "Write a Python function slugify(title: str) -> str that lowercases, replaces spaces with hyphens and removes "
               "characters other than a-z, 0-9 and hyphens. Return the code in a ```python block."},
]


def run(db: Session, model_ids: list[str], *, categories: list[str] | None = None, actor: str = "system",
        router: Any | None = None) -> dict[str, Any]:
    """Benchmark models on the dataset (governed calls: budgets + tracing). Writes one profile per (model, category)."""
    from ..governance import core as gov
    from ..models import ModelProfile
    from .providers import call_model

    cands = {c.id: c for c in available_models(db)}
    tasks = [t for t in TASKS if not categories or t["category"] in categories]
    summary: dict[str, Any] = {}
    for mid in model_ids:
        c = cands.get(mid)
        if c is None:
            summary[mid] = {"error": "not an available model"}
            continue
        per_cat: dict[str, list[dict[str, Any]]] = {}
        for t in tasks:
            t0 = time.monotonic()
            try:
                r = call_model(db, mid, system=SYSTEM, prompt=t["prompt"], max_tokens=t["max_tokens"], user_email=None,
                               agent_id="model_benchmark", workflow="creative.benchmark", purpose="creative.benchmark", router=router)
                det = quality.deterministic(r["text"], t["prompt"], t["category"])
                per_cat.setdefault(t["category"], []).append({"ok": True, "score": det["score"], "checks": det["checks"],
                                                               "latency_ms": r["latency_ms"] or int((time.monotonic() - t0) * 1000),
                                                               "tokens": r["input_tokens"] + r["output_tokens"], "cost_usd": r["cost_usd"]})
            except Exception as e:  # noqa: BLE001 — a failing model is a result (reliability), not a crash
                per_cat.setdefault(t["category"], []).append({"ok": False, "score": 0.0, "error": str(e)[:200],
                                                               "latency_ms": int((time.monotonic() - t0) * 1000), "tokens": 0, "cost_usd": 0.0})
        out = {}
        for cat, rs in per_cat.items():
            ok = [r for r in rs if r["ok"]]
            metrics = {"reliability": round(len(ok) / len(rs), 3),
                       "latency_ms": round(sum(r["latency_ms"] for r in ok) / len(ok)) if ok else None,
                       "tokens": sum(r["tokens"] for r in rs), "cost_usd": round(sum(r["cost_usd"] for r in rs), 6)}
            for k in {k for r in ok for k in r["checks"]}:
                vals = [r["checks"][k] for r in ok if k in r["checks"]]
                metrics[k] = round(sum(vals) / len(vals), 3)
            score = round(sum(r["score"] for r in rs) / len(rs), 4)
            db.add(ModelProfile(model_id=mid, model_version=c.version, category=cat, score=score, metrics=metrics, tasks=len(rs),
                                conditions={"dataset": DATASET_VERSION, "scoring": "deterministic rules (quality.deterministic)",
                                            "max_tokens": {t["id"]: t["max_tokens"] for t in tasks if t["category"] == cat},
                                            "hardware": platform.processor() or platform.machine(), "at": datetime.now(UTC).isoformat()}))
            out[cat] = {"score": score, **metrics}
        overall = [v["score"] for v in out.values()]
        if overall:
            db.add(ModelProfile(model_id=mid, model_version=c.version, category="overall",
                                score=round(sum(overall) / len(overall), 4), metrics={"categories": len(out)}, tasks=len(tasks),
                                conditions={"dataset": DATASET_VERSION, "scoring": "mean of category scores"}))
        summary[mid] = out
        gov.audit(db, actor, "creative.benchmark", f"model:{mid}", dataset=DATASET_VERSION, categories=sorted(out))
        db.commit()
    return {"dataset": DATASET_VERSION, "results": summary}


def due(db: Session) -> list[dict[str, Any]]:
    """Models that need (re-)benchmarking: never measured, or their version changed since the last measurement."""
    from ..models import ModelProfile

    latest: dict[str, ModelProfile] = {}
    for p in db.scalars(select(ModelProfile).order_by(ModelProfile.measured_at.desc())):
        latest.setdefault(p.model_id, p)
    out = []
    for c in available_models(db):
        p = latest.get(c.id)
        if p is None:
            out.append({"model": c.id, "reason": "never benchmarked"})
        elif c.version and p.model_version and p.model_version != c.version:
            out.append({"model": c.id, "reason": f"model version changed ({p.model_version} → {c.version})"})
        elif p.conditions.get("dataset") not in (None, DATASET_VERSION):
            out.append({"model": c.id, "reason": f"dataset changed ({p.conditions.get('dataset')} → {DATASET_VERSION})"})
    return out


def table(db: Session) -> dict[str, Any]:
    """Model × category matrix of the latest scores (for comparison views)."""
    cands = available_models(db)
    profs = profiles(db, [c.id for c in cands])
    cats = sorted({cat for p in profs.values() for cat in p})
    return {"categories": cats, "dataset": DATASET_VERSION,
            "models": [{"model": c.id, "display": c.display, "cost_class": c.cost_class, "locality": c.locality, "version": c.version,
                        "scores": {cat: {"score": profs[c.id][cat]["score"], "tasks": profs[c.id][cat]["tasks"],
                                         "latency_ms": profs[c.id][cat]["metrics"].get("latency_ms"),
                                         "stale": bool(c.version and profs[c.id][cat]["version"] and profs[c.id][cat]["version"] != c.version),
                                         "measured_at": profs[c.id][cat]["measured_at"]}
                                   for cat in profs.get(c.id, {})}} for c in cands]}
