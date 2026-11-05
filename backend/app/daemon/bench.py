"""Model benchmark: representative tasks with deterministic graders.

Measures accuracy, instruction adherence, reasoning, coding (static check only — generated code is never executed),
hallucination/abstention, tool-call formatting, Swedish, context retention and latency, and reports
COST PER SUCCESSFUL TASK (API cost + estimated local electricity) — a cheap model that fails is not cheap.
"""
from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from ..models import BenchmarkRun
from . import state

SYSTEM = "You are a careful assistant. Follow the output instructions exactly."


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").strip().lower())


def _json(t: str) -> Any:
    m = re.search(r"\{.*\}", t or "", re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None


TASKS: list[dict[str, Any]] = [
    {"id": "cls-en", "skill": "classification", "prompt": "Classify the sentiment of: 'I love this lamp, it is perfect.' Answer with one word: positive, negative or neutral.",
     "check": lambda t: _norm(t).strip(".") == "positive"},
    {"id": "cls-sv", "skill": "swedish", "prompt": "Klassificera känslan i: 'Leveransen var sen och produkten trasig.' Svara med ett ord: positive, negative eller neutral.",
     "check": lambda t: "negative" in _norm(t)},
    {"id": "extract-json", "skill": "structured_output", "prompt": "Extract the product name and price from: 'The Aurora lamp costs 49 EUR.' Reply with JSON only: {\"product\": string, \"price\": number}.",
     "check": lambda t: (lambda d: isinstance(d, dict) and "aurora" in str(d.get("product", "")).lower() and float(d.get("price", 0)) == 49)(_json(t))},
    {"id": "exact-ok", "skill": "instruction_adherence", "prompt": "Reply with exactly the word OK and nothing else.",
     "check": lambda t: (t or "").strip().strip(".") == "OK"},
    {"id": "list-three", "skill": "instruction_adherence", "prompt": "Name three primary colours as a comma-separated list on one line, nothing else.",
     "check": lambda t: len([x for x in (t or "").strip().splitlines()[0].split(",") if x.strip()]) == 3 if (t or "").strip() else False},
    {"id": "math-boxes", "skill": "reasoning", "prompt": "A box holds 12 items. How many boxes are needed for 50 items? Answer with the number only.",
     "check": lambda t: re.sub(r"[^0-9]", "", (t or "").strip().split()[0] if (t or "").strip() else "") == "5"},
    {"id": "syllogism", "skill": "reasoning", "prompt": "All lamps in the warehouse are tested. Item X is a lamp in the warehouse. Is item X tested? Answer yes or no.",
     "check": lambda t: _norm(t).startswith("yes")},
    {"id": "abstain", "skill": "hallucination", "prompt": "What was the exact closing share price of Demonkoncernen AB on 3 March 2025? If you do not know, answer exactly UNKNOWN.",
     "check": lambda t: "unknown" in _norm(t) and not re.search(r"\d+[.,]\d+", t or "")},
    {"id": "translate-sv", "skill": "swedish", "prompt": "Översätt till svenska, svara bara med översättningen: 'The battery is charged.'",
     "check": lambda t: "batteri" in _norm(t) and re.search(r"laddat|laddad|uppladdat", _norm(t)) is not None},
    {"id": "context", "skill": "context_retention", "prompt": "Remember this code word: OBSIDIAN-7. Here is some unrelated text about warehouse shelving, pallet sizes and forklift charging schedules. Now: what was the code word? Reply with the code word only.",
     "check": lambda t: "obsidian-7" in _norm(t)},
    {"id": "code-add", "skill": "coding", "prompt": "Write a Python function named add that returns the sum of a and b. Reply with code only.",
     "check": lambda t: re.search(r"def\s+add\s*\(\s*a\s*,\s*b\s*\)", t or "") is not None and re.search(r"return\s+a\s*\+\s*b", t or "") is not None},
    {"id": "tool-call", "skill": "tool_use", "prompt": "You can call the tool archive.search(query). The user asks: 'find our notes on solar lanterns'. Reply with JSON only: {\"tool\": \"archive.search\", \"query\": <string>}.",
     "check": lambda t: (lambda d: isinstance(d, dict) and d.get("tool") == "archive.search" and "solar" in str(d.get("query", "")).lower())(_json(t))},
]


def run(db: Session, *, provider: Any, provider_id: str, model: str, actor: str, call: Callable[..., Any] | None = None) -> BenchmarkRun:
    """`provider` must expose .complete(model=…, system=…, prompt=…, schema=None, effort=…, max_tokens=…) → Completion."""
    st = state.load(db)
    watts, price = float(st["energy"]["watts"]), float(st["energy"]["usd_per_kwh"])
    br = BenchmarkRun(provider=provider_id, model=model, created_by=actor, status="running")
    db.add(br)
    db.commit()
    results = []
    for t in TASKS:
        t0 = time.monotonic()
        try:
            c = provider.complete(model=model, system=SYSTEM, prompt=t["prompt"], schema=None, effort="low", max_tokens=96)
            ok = bool(t["check"](c.text))
            results.append({"id": t["id"], "skill": t["skill"], "passed": ok, "output": (c.text or "")[:200], "latency_ms": c.latency_ms,
                            "input_tokens": c.input_tokens, "output_tokens": c.output_tokens, "cost_usd": c.cost_usd})
        except Exception as e:
            results.append({"id": t["id"], "skill": t["skill"], "passed": False, "error": f"{type(e).__name__}: {e}"[:200],
                            "latency_ms": int((time.monotonic() - t0) * 1000), "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})
    n_ok = sum(r["passed"] for r in results)
    api_cost = sum(r["cost_usd"] for r in results)
    local = provider_id in ("local", "ollama") or provider_id.startswith("worker:")
    energy_wh = sum(r["latency_ms"] for r in results) / 1000 / 3600 * watts if local else 0.0
    energy_usd = energy_wh / 1000 * price
    by_skill: dict[str, list[bool]] = {}
    for r in results:
        by_skill.setdefault(r["skill"], []).append(r["passed"])
    br.results = results
    br.summary = {"tasks": len(results), "passed": n_ok, "accuracy": round(n_ok / len(results), 3),
                  "by_skill": {k: round(sum(v) / len(v), 2) for k, v in by_skill.items()},
                  "avg_latency_ms": round(sum(r["latency_ms"] for r in results) / len(results)),
                  "api_cost_usd": round(api_cost, 6), "energy_wh_estimate": round(energy_wh, 4), "energy_cost_usd_estimate": round(energy_usd, 6),
                  "cost_per_success_usd": round((api_cost + energy_usd) / n_ok, 6) if n_ok else None,
                  "note": "energy figures are estimates from configured watts × wall-clock time"}
    br.status, br.finished_at = "completed", datetime.now(UTC)
    db.commit()
    return br
