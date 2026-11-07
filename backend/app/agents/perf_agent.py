"""Performance Engineering Agent: turns real telemetry into measurable optimisation proposals.

It never changes code, configuration, security or spending. Each proposal carries the baseline measurement that
triggered it, the suggested change, expected benefit and risk, and how to verify (re-measure with
`scripts/perf_bench.py --compare`); a human approves or rejects it. No model call is needed for any of this.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from ..models import OptimizationProposal, Task
from .base import AgentContext, AgentOutput, BaseAgent


def _fp(*parts: Any) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:32]


VERIFY = "verify: python scripts/perf_bench.py --label after-<change> --compare <baseline>; keep only if the measurement improves"


def analyse(db: Any) -> list[dict[str, Any]]:
    from ..daemon import cache, telemetry
    from ..daemon.runtime import get_local

    props: list[dict[str, Any]] = []
    for r in telemetry.routes(60):
        if r["count"] >= 20 and (r["p95_ms"] or 0) > 500:
            props.append({"kind": "perf_slow_route", "title": f"{r['route']} is slow (p95 {r['p95_ms']} ms over {r['count']} calls)",
                          "detail": "Profile the handler; aggregate in SQL, cache stable results, paginate large responses. " + VERIFY,
                          "evidence": r, "fp": _fp("slow", r["route"], int((r["p95_ms"] or 0) // 250))})
        if r["count"] >= 10 and r["sql_per_request"] > 25:
            props.append({"kind": "perf_n_plus_one", "title": f"{r['route']} runs {r['sql_per_request']} SQL statements per request",
                          "detail": "Likely a per-row query in a loop (N+1): replace with a grouped/joined query. " + VERIFY,
                          "evidence": r, "fp": _fp("n1", r["route"])})
    for c in cache.stats():
        n = (c.get("hits") or 0) + (c.get("misses") or 0)
        if n >= 200 and (c.get("hit_rate") or 0) < 0.3:
            props.append({"kind": "perf_cache", "title": f"L1 cache '{c['name']}' hit rate {c['hit_rate']} over {n} lookups",
                          "detail": "TTL too short or keys too specific — or the cache is not worth its memory and should be removed. " + VERIFY,
                          "evidence": c, "fp": _fp("cache", c["name"])})
    p = get_local()
    loads = Counter(e.get("model") for e in telemetry.events(300) if e["kind"] == "model_load")
    for model, n in loads.items():
        if n >= 3:
            props.append({"kind": "perf_model_churn", "title": f"{model} was loaded {n}× recently",
                          "detail": "Residency churn: raise the idle-unload time or reserve RAM for this model; each reload costs seconds "
                                    "(page cache) to minutes (cold disk ≈14 MB/s here). " + VERIFY,
                          "evidence": {"loads": n, "total_loads": p.load_count, "load_ms_total": p.load_ms_total}, "fp": _fp("churn", model, n // 5)})
    over = Counter(e.get("agent") for e in telemetry.events(300) if e["kind"] == "context_over_budget")
    for agent, n in over.items():
        if n >= 5:
            props.append({"kind": "perf_context", "title": f"agent {agent} exceeded its context budget {n}×",
                          "detail": "Send retrieved passages instead of whole documents, or raise this agent's budget if the task needs it.",
                          "evidence": {"events": n}, "fp": _fp("ctx", agent, n // 10)})
    for h in telemetry.hosts():
        if h["requests"] >= 5 and (h["errors"] + h["status"].get("4xx", 0) + h["status"].get("5xx", 0)) / h["requests"] > 0.3:
            props.append({"kind": "perf_source", "title": f"external source {h['host']} fails {round(100 * (h['errors'] + h['status'].get('4xx', 0) + h['status'].get('5xx', 0)) / h['requests'])}% of requests",
                          "detail": "Lower its request rate, prefer another source for the same topic, or check its terms/rate limits.",
                          "evidence": h, "fp": _fp("src", h["host"])})
    since = datetime.now(UTC) - timedelta(days=1)
    rows = db.execute(select(Task.agent_id, Task.status, func.count(Task.id)).where(Task.created_at >= since).group_by(Task.agent_id, Task.status)).all()
    per: dict[str, Counter] = {}
    for a, st, n in rows:
        per.setdefault(a, Counter())[st] += n
    for a, c in per.items():
        tot = sum(c.values())
        if tot >= 5 and c["failed"] / tot > 0.2:
            props.append({"kind": "perf_agent_failures", "title": f"agent {a} failed {c['failed']} of {tot} tasks in 24 h",
                          "detail": "Read the task errors; failures waste the compute spent before them.", "evidence": dict(c),
                          "fp": _fp("fail", a, datetime.now(UTC).date())})
    return props


class PerformanceEngineerAgent(BaseAgent):
    id, name, division = "perf_engineer", "Performance Engineering Agent", "operations"
    description = "Reads telemetry (latency, SQL per request, cache hit rates, model churn, context budgets, source failures) and files measurable optimisation proposals. Never applies them."
    level, tier = 1, "fast"
    task_types = ("perf.analyze",)
    success_criterion = "every proposal cites the measurement that triggered it and how to verify the improvement"

    def handle(self, ctx: AgentContext, task: Task) -> AgentOutput:
        props = analyse(ctx.db)
        created = []
        for p in props:
            if ctx.db.scalars(select(OptimizationProposal).where(OptimizationProposal.fingerprint == p["fp"])).first():
                continue
            o = OptimizationProposal(kind=p["kind"], title=p["title"][:255], detail=p["detail"], evidence=p["evidence"], fingerprint=p["fp"])
            ctx.db.add(o)
            created.append(p["title"])
        ctx.db.flush()
        return AgentOutput(summary=f"Performance analysis: {len(props)} finding(s), {len(created)} new proposal(s)",
                           result={"findings": len(props), "new_proposals": created}, recommendations=created, epistemic="verified", confidence=0.9)
