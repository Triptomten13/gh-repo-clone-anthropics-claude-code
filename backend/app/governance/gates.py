"""DAEMON EVALUATION LAB — release gates.

Before a change of a given kind goes live (prompt version, model in a slot, retrieval configuration …) the gates for
that kind run their evaluation suites and compare scores with stored thresholds. A failed MANDATORY gate blocks the
release; advisory gates are reported. Every check is stored (gate_runs) and audited, so regressions are visible over
time. Changing a gate is itself governed (gates.* is RESTRICTED: a second person approves).

What the built-in suites measure (honestly): the platform's offline guards and retrieval — prompt-injection
detection, intent routing, planning, retrieval grounding — not a model's free-text quality. Model gates use the
recorded benchmark of that model (run it first); without a benchmark a mandatory model gate fails closed.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import BenchmarkRun, GateRun, ReleaseGate
from . import core as gov

DEFAULT_GATES = [  # (target kind, suite, minimum score, mandatory)
    ("prompt", "injection_detection", 1.0, True),
    ("prompt", "retrieval_grounding", 0.9, True),
    ("retrieval", "retrieval_grounding", 0.9, True),
    ("model", "benchmark_accuracy", 0.5, False),
]


class GateFailed(Exception):
    def __init__(self, run: GateRun):
        super().__init__("; ".join(run.blocking))
        self.run = run


def suites() -> dict[str, Any]:
    from ..evals import runner

    return {"injection_detection": runner.injection_suite, "retrieval_grounding": runner.retrieval_suite,
            "intel_routing": runner.intel_routing_suite, "planner_intents": runner.planner_suite}


def ensure_defaults(db: Session) -> None:
    if db.scalar(select(ReleaseGate.id).limit(1)) is None:
        for kind, suite, score, mandatory in DEFAULT_GATES:
            db.add(ReleaseGate(target_kind=kind, suite=suite, min_score=score, mandatory=mandatory, created_by="system-defaults"))
        db.flush()


def _benchmark_accuracy(db: Session, model_key: str) -> float | None:
    for b in db.scalars(select(BenchmarkRun).where(BenchmarkRun.status == "completed").order_by(BenchmarkRun.id.desc())):
        if model_key and model_key in f"{b.provider}:{b.model}":
            return (b.summary or {}).get("accuracy")
    return None


def check(db: Session, target_kind: str, target_ref: str, actor: str) -> GateRun:
    ensure_defaults(db)
    gates = db.scalars(select(ReleaseGate).where(ReleaseGate.target_kind == target_kind, ReleaseGate.enabled.is_(True))).all()
    available, cache, results, blocking = suites(), {}, {}, []
    for g in gates:
        if g.suite == "benchmark_accuracy":
            score = _benchmark_accuracy(db, target_ref.split("@")[-1])
            detail = "latest completed benchmark of this model" if score is not None else "no benchmark recorded for this model"
        elif g.suite in available:
            if g.suite not in cache:
                cache[g.suite] = available[g.suite]()
            score, detail = cache[g.suite].get("score"), cache[g.suite].get("metric", "")
        else:
            score, detail = None, f"unknown suite {g.suite}"
        ok = score is not None and score >= g.min_score
        results[g.suite] = {"score": score, "min": g.min_score, "mandatory": g.mandatory, "passed": ok, "detail": detail}
        if not ok and g.mandatory:
            blocking.append(f"{g.suite}: {score if score is not None else 'not measured'} < required {g.min_score}")
    run = GateRun(target_kind=target_kind, target_ref=target_ref, results=results, passed=not blocking, blocking=blocking, created_by=actor)
    db.add(run)
    db.flush()
    gov.audit(db, actor, "gate.check", f"{target_kind}:{target_ref}", gate_run=run.id, passed=run.passed, blocking=blocking)
    if blocking:
        raise GateFailed(run)
    return run
