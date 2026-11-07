"""MODEL CHAMPIONSHIP — every contender on the SAME tasks, the SAME hardware, in the SAME run.

New models (from the Model Hunter) compete against the installed ones on Demonkoncernen's own suites:
* DAEMON CORE benchmark (17 tasks, deterministic graders: accuracy, instruction adherence, reasoning, coding — never
  executed —, hallucination/abstention, tool-call format, structured output, context retention), and
* the creative dataset (Swedish/English lyrics and poems, product names, story, business ideas, summary, code; rule-based
  scoring with the brief-echo check).
Every contender is called by its model key with the same token limits (reasoning models therefore run WITHOUT their
thinking phase — the same condition for all, stated in the result). The hardware fingerprint and suite versions are
stored, and the result is compared with the previous championship on the same hardware and suites, so the organisation
can SHOW when it became smarter, faster or cheaper — or that it did not.
"""
from __future__ import annotations

import statistics
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..governance import core as gov

HIGHER_IS_BETTER = "higher"
LOWER_IS_BETTER = "lower"


def fingerprint() -> dict[str, Any]:
    from ..daemon import hardware

    s = hardware.snapshot()
    cpu = s.get("cpu") or {}
    return {"cpu": cpu.get("model", ""), "cores": cpu.get("usable_cores") or cpu.get("logical_cores"),
            "ram_gb": round((s.get("ram_total_bytes") or 0) / 1e9), "gpus": [g.get("name", "") for g in s.get("gpus") or []],
            "accelerator": s.get("accelerator", ""), "runtime": (s.get("runtime") or {}).get("llama_cpp_version", "")}


def suites() -> dict[str, Any]:
    from ..creative.perf import DATASET_VERSION
    from ..daemon import bench

    return {"daemon": f"daemon-core-v1 ({len(bench.TASKS)} tasks)", "creative": DATASET_VERSION, "call": "by model key, thinking off, same token limits"}


def contenders(db: Session) -> list[Any]:
    from pathlib import Path

    from ..models import LocalModel

    return [m for m in db.scalars(select(LocalModel).where(LocalModel.status == "installed", LocalModel.kind == "chat").order_by(LocalModel.size_bytes))
            if m.file_path and Path(m.file_path).exists()]


def _measure(db: Session, m: Any, actor: str, provider: Any) -> dict[str, Any]:
    from ..creative import perf
    from ..daemon import bench

    t0 = time.monotonic()
    br = bench.run(db, provider=provider, provider_id="local", model=m.key, actor=actor, call_model=m.key)
    rs = [r for r in br.results or [] if not r.get("error")]
    out_tok = sum(r.get("output_tokens") or 0 for r in rs)
    gen_s = sum((r.get("latency_ms") or 0) for r in rs) / 1000
    cr = perf.run(db, [f"local:{m.key}"], actor=actor)["results"].get(f"local:{m.key}", {})
    s = br.summary or {}
    return {"benchmark_run": br.id, "accuracy": s.get("accuracy"), "by_skill": s.get("by_skill", {}),
            "latency_p50_ms": statistics.median([r["latency_ms"] for r in rs]) if rs else None,
            "tokens_per_s": round(out_tok / gen_s, 2) if gen_s else None,
            "cost_per_success_usd": s.get("cost_per_success_usd"), "energy_wh": s.get("energy_wh_estimate"),
            "creative": {cat: v.get("score") for cat, v in cr.items() if isinstance(v, dict) and "score" in v},
            "seconds": round(time.monotonic() - t0, 1), "size_gb": round((m.size_bytes or 0) / 1e9, 2), "version": (m.sha256_actual or "")[:16]}


def _metrics(r: dict[str, Any]) -> dict[str, tuple[float | None, str]]:
    out: dict[str, tuple[float | None, str]] = {"accuracy (17 tasks)": (r.get("accuracy"), HIGHER_IS_BETTER),
                                                "speed (tokens/s)": (r.get("tokens_per_s"), HIGHER_IS_BETTER),
                                                "latency p50 (ms)": (r.get("latency_p50_ms"), LOWER_IS_BETTER),
                                                "cost per success (USD)": (r.get("cost_per_success_usd"), LOWER_IS_BETTER)}
    for k, v in (r.get("by_skill") or {}).items():
        out[f"skill: {k}"] = (v, HIGHER_IS_BETTER)
    for k, v in (r.get("creative") or {}).items():
        out[f"creative: {k}"] = (v, HIGHER_IS_BETTER)
    return out


def standings(results: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    cats: dict[str, list[dict[str, Any]]] = {}
    for model, r in results.items():
        if r.get("error"):
            continue
        for cat, (val, direction) in _metrics(r).items():
            if val is not None:
                cats.setdefault(cat, []).append({"model": model, "value": val, "direction": direction})
    for rows in cats.values():
        rows.sort(key=lambda x: x["value"], reverse=rows[0]["direction"] == HIGHER_IS_BETTER)
    return cats


def compare(now: dict[str, list[dict[str, Any]]], before: dict[str, list[dict[str, Any]]] | None) -> dict[str, Any]:
    """Best-of-organisation per category, now vs the previous championship. Smarter = quality up, faster = speed up or
    latency down, cheaper = cost per success down. Ties and regressions are reported too."""
    if not before:
        return {"previous": None, "changes": [], "verdict": "first championship on this hardware — the baseline"}
    changes = []
    for cat, rows in now.items():
        if not rows or not before.get(cat):
            continue
        b, a = before[cat][0], rows[0]
        direction = a["direction"]
        diff = (a["value"] - b["value"]) if direction == HIGHER_IS_BETTER else (b["value"] - a["value"])
        rel = diff / abs(b["value"]) if b["value"] else None
        kind = ("faster" if "speed" in cat or "latency" in cat else "cheaper" if "cost" in cat else "smarter")
        if abs(diff) < 1e-9 or (rel is not None and abs(rel) < 0.02):
            continue
        changes.append({"category": cat, "kind": kind if diff > 0 else "regressed", "before": b, "after": a,
                        "change": round(diff, 4), "relative": round(rel, 3) if rel is not None else None,
                        "new_leader": a["model"] != b["model"]})
    up = [c for c in changes if c["kind"] != "regressed"]
    verdict = (", ".join(sorted({c["kind"] for c in up})) + f" in {len(up)} categor{'y' if len(up) == 1 else 'ies'}" if up else "no improvement") + \
        (f"; {sum(1 for c in changes if c['kind'] == 'regressed')} regression(s)" if any(c["kind"] == "regressed" for c in changes) else "")
    return {"changes": changes, "verdict": verdict}


def run(db: Session, *, actor: str, models: list[str] | None = None, max_seconds: int = 2700, provider: Any = None) -> Any:
    """Run a championship (blocking — call from a background thread or an agent task)."""
    from ..models import Championship

    if provider is None:
        from ..ai.llm import get_provider

        provider = get_provider()._all_providers()["local"]
    field = [m for m in contenders(db) if not models or m.key in models]
    ch = Championship(created_by=actor, hardware=fingerprint(), suites=suites(), participants=[m.key for m in field], status="running")
    db.add(ch)
    db.commit()
    t0 = time.monotonic()
    results: dict[str, dict[str, Any]] = {}
    try:
        for m in field:
            if time.monotonic() - t0 > max_seconds:
                results[m.key] = {"error": f"not run: the championship's time budget ({max_seconds} s) was used up"}
                continue
            try:
                results[m.key] = _measure(db, m, actor, provider)
            except Exception as e:  # noqa: BLE001 — a contender that fails is a result
                results[m.key] = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
            ch.results = dict(results)
            db.commit()
        st = standings(results)
        prev = db.scalars(select(Championship).where(Championship.status == "completed", Championship.id != ch.id)
                          .order_by(Championship.id.desc())).all()
        prev = next((p for p in prev if p.hardware == ch.hardware and p.suites == ch.suites), None)
        d = compare(st, prev.standings if prev else None)
        d["previous"] = prev.id if prev else None
        lead = {cat: rows[0]["model"] for cat, rows in st.items() if rows}
        ch.results, ch.standings, ch.deltas = results, st, d
        ch.summary = (f"{len([r for r in results.values() if not r.get('error')])} of {len(field)} contenders measured on "
                      f"{ch.hardware.get('cpu', '?')} ({ch.hardware.get('cores')} cores, {ch.hardware.get('ram_gb')} GB). "
                      f"Leaders: accuracy {lead.get('accuracy (17 tasks)', '—')}, speed {lead.get('speed (tokens/s)', '—')}, "
                      f"songwriting {lead.get('creative: songwriting', '—')}. Versus #{d['previous']}: {d['verdict']}." if prev else
                      f"Baseline: {len(results)} contenders on {ch.hardware.get('cpu', '?')}.")
        ch.status = "completed"
    except Exception as e:  # noqa: BLE001
        ch.status, ch.error = "failed", f"{type(e).__name__}: {str(e)[:300]}"
    ch.finished_at = datetime.now(UTC)
    gov.audit(db, actor, "models.championship", f"championship:{ch.id}", participants=ch.participants, status=ch.status)
    db.commit()
    return ch
