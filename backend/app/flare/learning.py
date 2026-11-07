"""Style DNA memory, genre evolution, creative reuse and persona calibration (§12A–D).

Learning only ever uses recorded outcomes (campaign performance rows, approved
concepts, experiment results). With no evidence, adjustments are zero and the
reports say "insufficient evidence" — nothing is predicted from fashion guesses.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timedelta, UTC
from typing import Any

SHRINK_K = 3.0  # Bayesian shrinkage: n/(n+k) of the observed effect is trusted
MAX_ADJ = 10.0


def style_dna(campaigns: list[Any], performance: list[Any], concepts: list[Any], category_of: dict[int, str] | None = None) -> dict[str, Any]:
    """Return learned adjustments (points, ±10) per genre and per campaign identity, plus the evidence behind them."""
    camp = {c.id: c for c in campaigns}
    feats: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in performance:
        c = camp.get(r.campaign_id)
        if not c:
            continue
        profit = (r.contribution if r.contribution is not None else 0.0) - r.spend
        keys = [f"identity:{c.identity}", f"platform:{c.platform}"] + [f"genre:{g}" for g in (c.genre or "").split("+") if g]
        for k in keys:
            feats[k]["spend"] += r.spend
            feats[k]["profit"] += profit
            feats[k]["n"] += 1
            feats[k]["engagements"] += r.engagements
    total_spend = sum(v["spend"] for k, v in feats.items() if k.startswith("identity:")) or 0.0
    total_profit = sum(v["profit"] for k, v in feats.items() if k.startswith("identity:"))
    base = total_profit / total_spend if total_spend else 0.0
    adjustments: dict[str, float] = {}
    evidence = {}
    for k, v in feats.items():
        if not v["spend"]:
            continue
        roi = v["profit"] / v["spend"]
        trust = v["n"] / (v["n"] + SHRINK_K)
        adj = max(-MAX_ADJ, min(MAX_ADJ, (roi - base) * 20 * trust))
        adjustments[k] = round(adj, 2)
        evidence[k] = {"observations": int(v["n"]), "spend": round(v["spend"], 2), "profit": round(v["profit"], 2),
                       "roi": round(roi, 3), "trust": round(trust, 2)}
    approved = defaultdict(int)
    for c in concepts:
        if c.status == "approved":
            approved[c.primary_genre] += 1
            approved[c.secondary_genre] += 1
    return {
        "genre": {k.split(":", 1)[1]: v for k, v in adjustments.items() if k.startswith("genre:")},
        "identity": {k.split(":", 1)[1]: v for k, v in adjustments.items() if k.startswith("identity:")},
        "platform": {k.split(":", 1)[1]: v for k, v in adjustments.items() if k.startswith("platform:")},
        "evidence": evidence, "approved_concept_genres": dict(approved), "baseline_roi": round(base, 3),
        "status": "learning" if evidence else "insufficient evidence",
    }


def genre_evolution(performance: list[Any], campaigns: list[Any], observations: list[Any], now: datetime | None = None,
                    window_days: int = 60) -> dict[str, Any]:
    """Emerging/declining aesthetics from evidence: campaign ROI by period and imported aesthetic-trend observations."""
    now = now or datetime.now(UTC)
    mid = now - timedelta(days=window_days)
    camp = {c.id: c for c in campaigns}
    periods: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"early": [], "late": []})
    for r in performance:
        c = camp.get(r.campaign_id)
        if not c or not r.spend:
            continue
        at = r.period_start if r.period_start.tzinfo else r.period_start.replace(tzinfo=UTC)
        roi = ((r.contribution or 0) - r.spend) / r.spend
        for g in (c.genre or "").split("+"):
            if g:
                periods[g]["late" if at >= mid else "early"].append(roi)
    perf_trends = []
    for g, d in periods.items():
        if len(d["early"]) >= 2 and len(d["late"]) >= 2:
            delta = statistics.mean(d["late"]) - statistics.mean(d["early"])
            perf_trends.append({"genre": g, "direction": "emerging" if delta > 0.1 else "declining" if delta < -0.1 else "stable",
                                "roi_change": round(delta, 3), "observations": len(d["early"]) + len(d["late"])})
    from ..engines import trends as T

    obs_by: dict[str, list[T.Obs]] = defaultdict(list)
    for o in observations:
        if o.keyword.startswith("aesthetic:"):
            at = o.observed_at if o.observed_at.tzinfo else o.observed_at.replace(tzinfo=UTC)
            obs_by[o.keyword.split(":", 1)[1]].append(T.Obs(f"{o.platform}:{o.metric}", o.value, at))
    cultural = []
    for g, obs in obs_by.items():
        a = T.analyze(g, obs)
        cultural.append({"aesthetic": g, "stage": a.stage, "velocity": a.velocity_score, "platforms": a.platforms, "observations": a.observations})
    status = "evidence-based" if perf_trends or cultural else "insufficient evidence"
    return {"performance_trends": sorted(perf_trends, key=lambda x: x["roi_change"], reverse=True),
            "cultural_trends": sorted(cultural, key=lambda x: x["velocity"], reverse=True), "status": status,
            "how_to_feed": "Record campaign performance, or import observations with keyword 'aesthetic:<genre_id>' from licensed trend data."}


def creative_reuse(target_genres: list[str], target_brand_id: int | None, assets: list[Any], campaigns: list[Any]) -> list[dict[str, Any]]:
    """Reusable *infrastructure* (templates, formats, workflows) from other brands — never identity assets."""
    identity_kinds = {"wordmark", "sigil", "logo", "palette_board"}
    tg = set(target_genres)
    out = []
    for a in assets:
        if a.brand_id == target_brand_id or a.kind in identity_kinds or a.status != "approved":
            continue
        overlap = tg & set(a.tags or [])
        if overlap:
            out.append({"type": "asset_template", "asset_id": a.id, "kind": a.kind, "title": a.title, "shared_genres": sorted(overlap),
                        "reuse": "adapt the structure/format; regenerate all brand-specific visuals and copy"})
    for c in campaigns:
        if c.brand_id == target_brand_id or c.status not in ("completed", "running"):
            continue
        overlap = tg & set((c.genre or "").split("+"))
        if overlap:
            out.append({"type": "campaign_format", "campaign_id": c.id, "identity": c.identity, "video_format": c.video_format,
                        "shared_genres": sorted(overlap), "reuse": "reuse the format and test design, not the creative"})
    return out


def persona_calibration(memory: list[Any]) -> dict[str, Any]:
    by: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for m in memory:
        if m.kind == "calibration" and m.predicted is not None and m.actual is not None:
            by[m.persona_id].append((m.predicted, m.actual))
    out = {}
    for pid, pts in by.items():
        if len(pts) >= 3 and len({p for p, _ in pts}) > 1 and len({a for _, a in pts}) > 1:
            out[pid] = {"points": len(pts), "correlation": round(statistics.correlation([p for p, _ in pts], [a for _, a in pts]), 3)}
        else:
            out[pid] = {"points": len(pts), "correlation": None}
    return out
