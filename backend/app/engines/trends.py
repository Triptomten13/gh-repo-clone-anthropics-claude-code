"""Trend detection engine (spec section 3).

Input: time-stamped observations per keyword (possibly from several platforms).
Each platform series is normalised to its own mean so platforms with different
units (views vs. search index) can be combined. Velocity is the weekly log-growth
estimated by least squares; acceleration compares recent vs. earlier growth.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable

STAGES = ("emerging", "exploding", "established", "saturated", "declining", "seasonal", "evergreen", "insufficient_data")


@dataclass
class Obs:
    platform: str
    value: float
    at: datetime


@dataclass
class TrendAnalysis:
    keyword: str
    stage: str
    velocity_score: float  # 0-100
    growth_rate: float  # weekly log growth
    acceleration: float
    platforms: list[str]
    cross_platform_growth: int  # number of platforms independently growing
    observations: int
    confidence: float
    notes: list[str] = field(default_factory=list)


def _slope(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


def _weekly_log_growth(points: list[tuple[datetime, float]]) -> float:
    if len(points) < 2:
        return 0.0
    t0 = points[0][0]
    xs = [(t - t0).total_seconds() / (7 * 86400) for t, _ in points]
    ys = [math.log(max(v, 1e-6)) for _, v in points]
    return _slope(xs, ys)


def _cv(vals: list[float]) -> float:
    if not vals:
        return 0.0
    m = sum(vals) / len(vals)
    if m == 0:
        return 0.0
    return math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals)) / m


def analyze(keyword: str, observations: Iterable[Obs], now: datetime | None = None) -> TrendAnalysis:
    obs = sorted(observations, key=lambda o: o.at)
    by_platform: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    for o in obs:
        by_platform[o.platform].append((o.at, o.value))
    platforms = sorted(by_platform)

    if len(obs) < 4:
        return TrendAnalysis(keyword, "insufficient_data", 0.0, 0.0, 0.0, platforms, 0, len(obs), 0.1,
                             ["fewer than 4 observations"])

    # Normalise each platform to its own mean and merge.
    merged: list[tuple[datetime, float]] = []
    growing = 0
    for _, pts in by_platform.items():
        mean = sum(v for _, v in pts) / len(pts) or 1.0
        merged.extend((t, v / mean) for t, v in pts)
        if len(pts) >= 3 and _weekly_log_growth(pts) > 0.05:
            growing += 1
    merged.sort()

    growth = _weekly_log_growth(merged)
    half = len(merged) // 2
    early = _weekly_log_growth(merged[: max(half, 2)])
    late = _weekly_log_growth(merged[half:]) if len(merged) - half >= 2 else growth
    accel = late - early

    span_days = (merged[-1][0] - merged[0][0]).days
    vals = [v for _, v in merged]
    cv = _cv(vals)
    notes: list[str] = []

    # Seasonality: needs > 1 year of history. Compare the same 4-week window last year.
    seasonal = False
    if span_days >= 400:
        last = merged[-1][0]
        recent = [v for t, v in merged if t >= last - timedelta(days=28)]
        prior = [v for t, v in merged if last - timedelta(days=365 + 28) <= t <= last - timedelta(days=365)]
        middle = [v for t, v in merged if last - timedelta(days=300) <= t <= last - timedelta(days=60)]
        if recent and prior and middle:
            r, p, m = (sum(x) / len(x) for x in (recent, prior, middle))
            if m > 0 and r / m > 1.5 and p / m > 1.5:
                seasonal = True
                notes.append("peak recurs at the same time last year")

    if seasonal:
        stage = "seasonal"
    elif growth > 0.25 and accel > 0:
        stage = "exploding"
    elif growth > 0.08:
        stage = "emerging" if vals[-1] < 1.5 * (sum(vals) / len(vals)) or len(platforms) < 2 else "exploding"
    elif growth < -0.06:
        stage = "declining"
    elif span_days >= 180 and cv < 0.25:
        stage = "evergreen"
    elif abs(growth) <= 0.03 and accel < 0:
        stage = "saturated"
    else:
        stage = "established"

    # Velocity score: logistic on growth, boosted by cross-platform confirmation and acceleration.
    base = 100 / (1 + math.exp(-growth * 12))
    boost = min(15.0, 6.0 * max(0, growing - 1)) + max(-10.0, min(10.0, accel * 40))
    velocity = max(0.0, min(100.0, base + boost))

    confidence = min(1.0, 0.25 + 0.05 * min(len(merged), 10) + 0.15 * min(len(platforms), 3) - (0.2 if span_days < 21 else 0))
    if growing >= 2:
        notes.append(f"independently growing on {growing} platforms")

    return TrendAnalysis(
        keyword=keyword,
        stage=stage,
        velocity_score=round(velocity, 1),
        growth_rate=round(growth, 4),
        acceleration=round(accel, 4),
        platforms=platforms,
        cross_platform_growth=growing,
        observations=len(merged),
        confidence=round(max(0.05, confidence), 2),
        notes=notes,
    )
