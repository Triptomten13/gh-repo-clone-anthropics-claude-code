---
name: agent-builder
description: Add or change an orchestrated agent or persona (task types, permissions, persona, tests, docs). Use when a new capability should be delegated to an agent.
---
1. Logic first: put the capability in a pure engine module (`backend/app/engines|flare|knowledge`) with unit tests.
2. Agent: subclass `BaseAgent` in `agents/catalog.py` or `agents/flare_agents.py` — `id`, `division`, `level` (lowest that works), `task_types`.
   Use `ctx.check(action)` for every permissioned action; LEVEL ≥4 actions call `ctx.request_approval` instead of acting.
   Return `AgentOutput` with an epistemic label; raise `Blocked` for missing data/credentials/approval.
3. Persona: add a `P(...)` seed in `flare/personas.py` (lens, affinities, novelty, risk) — personas never carry permissions.
4. If G-sus should plan it: add an intent regex + step in `gsus/engine.py` and a case in `evals/datasets/planner.json`.
5. Tests: unit test for the engine + an API test through `/api/tasks` or `/api/flare/run`. Update `docs/AGENTS.md`.
