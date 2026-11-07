"""Experiment evaluation (spec section 14) and prediction-accuracy tracking (section 22)."""
from __future__ import annotations

import math
from typing import Any


def two_proportion_z(conv_a: int, n_a: int, conv_b: int, n_b: int) -> dict[str, Any]:
    if min(n_a, n_b) <= 0:
        return {"available": False, "reason": "no traffic"}
    pa, pb = conv_a / n_a, conv_b / n_b
    p = (conv_a + conv_b) / (n_a + n_b)
    se = math.sqrt(p * (1 - p) * (1 / n_a + 1 / n_b)) if 0 < p < 1 else 0.0
    if se == 0:
        return {"available": False, "reason": "zero variance"}
    z = (pb - pa) / se
    p_value = math.erfc(abs(z) / math.sqrt(2))
    return {"available": True, "rate_a": round(pa, 5), "rate_b": round(pb, 5), "lift": round((pb - pa) / pa, 4) if pa else None,
            "z": round(z, 3), "p_value": round(p_value, 5), "significant_95": p_value < 0.05}


def decide(success_metrics: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    """Scale / iterate / abandon. Deliberately unsentimental.

    success_metrics: {"min_roas": 2.0, "min_contribution_margin": 0, "min_orders": 20, "kill_roas": 1.0}
    actual: {"roas": .., "contribution_margin": .., "orders": .., "spend": ..}
    """
    reasons: list[str] = []
    min_orders = success_metrics.get("min_orders", 20)
    orders = actual.get("orders", 0) or 0
    roas = actual.get("roas")
    cm = actual.get("contribution_margin")
    kill_roas = success_metrics.get("kill_roas", 1.0)
    if orders < min_orders and (actual.get("spend") or 0) < success_metrics.get("max_spend", float("inf")):
        if roas is not None and roas < kill_roas * 0.5 and (actual.get("spend") or 0) > 0:
            return {"decision": "abandon", "reasons": [f"ROAS {roas} far below kill threshold {kill_roas} even at low volume"]}
        return {"decision": "continue", "reasons": [f"insufficient sample: {orders}/{min_orders} orders"]}
    ok_roas = roas is not None and roas >= success_metrics.get("min_roas", 2.0)
    ok_cm = cm is not None and cm >= success_metrics.get("min_contribution_margin", 0)
    if ok_roas and ok_cm:
        return {"decision": "scale", "reasons": ["met ROAS and contribution margin targets"]}
    if roas is not None and roas < kill_roas:
        reasons.append(f"ROAS {roas} below kill threshold {kill_roas}")
        return {"decision": "abandon", "reasons": reasons}
    if not ok_roas:
        reasons.append("ROAS below target but above kill threshold")
    if not ok_cm:
        reasons.append("contribution margin below target")
    return {"decision": "iterate", "reasons": reasons}


def prediction_error(predicted: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    errs = {}
    for k, p in predicted.items():
        a = actual.get(k)
        if isinstance(p, (int, float)) and isinstance(a, (int, float)) and a != 0:
            errs[k] = round(abs(p - a) / abs(a), 4)
    return {"per_metric_ape": errs, "mape": round(sum(errs.values()) / len(errs), 4) if errs else None}
