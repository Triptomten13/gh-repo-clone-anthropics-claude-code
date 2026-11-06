"""DAEMON CREATIVE INTELLIGENCE — acceptance criteria 1–18 (Creative Tournament Mode, provider intelligence, quality).

Fake models with known behaviour stand in for real providers: deterministic, so every assertion is reproducible.
  local:poet-good   — Swedish lyrics with verses, chorus and rhymes; a fair critic; a real synthesizer
  local:poet-weak   — repetitive English filler with AI boilerplate
  local:poet-flaky  — the provider fails (unavailable)
  local:paster      — "synthesizes" by pasting candidates together
  anthropic:*       — an external, paid API (registry prices) whose key must never appear anywhere
"""
from __future__ import annotations

import json
import re

import pytest

GOOD = """Vers 1
Den första snön föll tyst i natt
över taken, vit och glatt
vinterns andning mot mitt fönster
ritar frost i kalla mönster

Refräng
Snö, snö, kom och stanna kvar
lys upp byn som en stjärna klar
Snö, snö, kom och stanna kvar

Vers 2
Barnen springer ut i snön
vinterns första tysta bön"""
BETTER = GOOD + "\nlyktan lyser, byn blir ny\nsnön har kommit till vår by"
WEAK = "Sure! Here is a song:\nSnow is falling, snow is falling\nSnow is falling, snow is falling\nSnow is falling, snow is falling\nIt is a tapestry in the end"
BRIEF = "Skriv en låt om vinterns första snö i en liten by, med vers och refräng"
SECRET = "sk-ant-test-secret-DO-NOT-LEAK-123"


class FakeProvider:
    """One provider id serving several fake models; records every prompt it receives."""

    def __init__(self, pid: str, locality: str = "local") -> None:
        self.id, self.locality, self.calls = pid, locality, []
        self.rate_limit_models: set[str] = set()

    def configured(self) -> bool:
        return True

    def health(self) -> dict:
        return {"configured": True}

    def complete(self, *, model, system, prompt, schema, effort, max_tokens):
        from app.ai.providers import Completion, ProviderUnavailable

        self.calls.append({"model": model, "system": system, "prompt": prompt})
        if model in self.rate_limit_models:
            raise ProviderUnavailable("429 rate limit exceeded")
        if model == "poet-flaky":
            raise ProviderUnavailable("connection refused")
        if "=== CANDIDATE" in prompt:  # a critic
            labels = re.findall(r"=== CANDIDATE (\w) ===\n(.*?)(?=\n\n=== CANDIDATE|\n\nScore every)", prompt, re.S)
            out = {}
            for lab, text in labels:
                good = "Refräng" in text or "refräng" in text.lower()
                n = 9 if good else 2
                first = text.strip().splitlines()[1] if good and len(text.strip().splitlines()) > 1 else "invented praise line"
                out[lab] = {"scores": {"originality": n, "imagery": n, "structure": n, "language": n, "adherence": n},
                            "best_lines": [first], "weaknesses": ["vers 2 är kort"] if good else ["repetitive", "wrong language"]}
            return Completion(json.dumps(out), None, self.id, model, 300, 80, 0.0, 5)
        if "Several writers answered" in prompt:  # synthesis
            if model == "paster":
                blocks = re.findall(r"=== VERSION \w \(score [\d.]+\) ===\n(.*?)\nStrongest:", prompt, re.S)
                return Completion("\n\n".join(blocks), None, self.id, model, 400, 200, 0.0, 5)
            return Completion(BETTER, None, self.id, model, 400, 120, 0.0, 5)
        if "Fix ONLY these problems" in prompt:  # revision: no improvement (same text) → diminishing returns
            cur = prompt.split("CURRENT VERSION:\n", 1)[1].split("\n\nFix ONLY", 1)[0]
            return Completion(cur, None, self.id, model, 300, 100, 0.0, 5)
        text = {"poet-good": GOOD, "poet-weak": WEAK, "paster": GOOD.replace("Snö, snö", "Is, is")}.get(model, GOOD)
        if self.locality == "external":
            text = BETTER
        return Completion(text, None, self.id, model, 200, 120, 0.004 if self.locality == "external" else 0.0, 5)


def _install(db, keys: list[tuple[str, str, str]]) -> None:
    """LocalModel rows for fake local models: (key, family, version)."""
    from app.models import LocalModel

    for key, fam, ver in keys:
        db.add(LocalModel(key=key, display_name=key, family=fam, kind="chat", parameters="1.5B", status="installed",
                          sha256_actual=ver * 8, languages=["sv", "en"], capabilities=["text"], license="apache-2.0"))
    db.commit()


@pytest.fixture()
def world(fresh_db, monkeypatch):
    """A router with a fake local runtime + a fake external API; seeded registry; three local models."""
    from app.ai import llm
    from app.ai.router import LLMRouter
    from app.daemon import quota, registry_seed, state

    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    db = fresh_db.SessionLocal()
    registry_seed.seed(db)
    db.commit()
    _install(db, [("poet-good", "alpha", "a1"), ("poet-weak", "beta", "b1"), ("paster", "gamma", "c1")])
    local, ext = FakeProvider("local"), FakeProvider("anthropic", "external")
    router = LLMRouter({"local": local, "anthropic": ext})
    llm.set_provider(router)
    state.invalidate()
    quota.reset()
    yield {"db": db, "local": local, "ext": ext, "router": router}
    db.close()
    llm.set_provider(None)
    quota.reset()


def _profile(db, model_id: str, category: str, score: float, version: str, latency: int = 4000) -> None:
    from app.creative.perf import DATASET_VERSION
    from app.models import ModelProfile

    db.add(ModelProfile(model_id=model_id, model_version=version, category=category, score=score, metrics={"latency_ms": latency},
                        tasks=2, conditions={"dataset": DATASET_VERSION}))
    db.commit()


def _admin(db):
    from app.models import User

    u = db.query(User).filter(User.email == "creative-admin@example.com").first()
    if u is None:
        u = User(email="creative-admin@example.com", password_hash="x", role="admin")
        db.add(u)
        db.commit()
    return u


def _run(world, **kw):
    from app.creative import tournament as T

    db = world["db"]
    kw.setdefault("user", _admin(db))
    kw.setdefault("budget", {"max_calls": 12, "max_models": 2, "critics": 1, "max_rounds": 1})
    return T.run(db, kw.pop("brief", BRIEF), **kw)


def _entries(db, t):
    from app.models import CreativeEntry

    return db.query(CreativeEntry).filter(CreativeEntry.tournament_id == t.id).order_by(CreativeEntry.id).all()


# ------------------------------------------------------------------ 1 · autonomous selection by an agent
def test_01_an_agent_selects_providers_and_runs_a_tournament_without_a_human(world):
    from app.agents.catalog import build_orchestrator
    from app.models import Approval, CreativeTournament, Task

    db = world["db"]
    orch = build_orchestrator()
    orch.sync_agents(db)
    t = orch.submit(db, "creative.tournament", {"brief": BRIEF, "budget": {"max_calls": 8, "max_models": 2, "critics": 1}},
                    requested_by="user:creative-admin@example.com", force=True)
    db.commit()
    _admin(db)
    orch.drain(5)
    db.expire_all()
    task = db.get(Task, t.id)
    assert task.status == "succeeded", task.error
    ct = db.query(CreativeTournament).order_by(CreativeTournament.id.desc()).first()
    assert ct.agent_id == "creative_director" and ct.plan["contestants"] and ct.plan["selection"]
    assert db.query(Approval).count() == 0  # ordinary provider choice needs no human


# ------------------------------------------------------------------ 2 · free/local first when good enough
def test_02_free_and_local_models_are_preferred_when_they_are_good_enough(world):
    from app.creative import providers as P

    db = world["db"]
    _profile(db, "local:poet-good", "songwriting", 0.8, "a1" * 8)
    _profile(db, "anthropic:claude-sonnet-5-5", "songwriting", 0.9, "claude-sonnet-5-5")
    r = P.choose_models(db, BRIEF, mode="FREE_FIRST", n=1)
    assert r["chosen"] == ["local:poet-good"], r["ranked"][:3]
    assert "no API cost" in r["ranked"][0]["why"]


# ------------------------------------------------------------------ 3 · premium when it is clearly better and affordable
def test_03_a_premium_model_wins_when_its_quality_justifies_the_cost_and_the_budget_allows(world):
    from app.creative import providers as P

    db = world["db"]
    _profile(db, "local:poet-good", "songwriting", 0.3, "a1" * 8)
    _profile(db, "anthropic:claude-sonnet-5-5", "songwriting", 0.95, "claude-sonnet-5-5")
    r = P.choose_models(db, BRIEF, mode="FREE_FIRST", n=1)
    assert r["chosen"] == ["anthropic:claude-sonnet-5-5"], r["ranked"][:3]
    # …but not when the budget is free-only, and not when it cannot pay for one call
    r = P.choose_models(db, BRIEF, mode="BEST_QUALITY", n=1, allowed_cost_classes=["local", "free_tier", "open_endpoint"])
    assert r["chosen"][0].startswith("local:")
    r = P.choose_models(db, BRIEF, mode="BEST_QUALITY", n=1, max_usd_per_call=0.0001)
    assert not r["chosen"][0].startswith("anthropic:claude-sonnet")


# ------------------------------------------------------------------ 4 · several models generate independently
def test_04_several_models_independently_generate_candidates(world):
    t = _run(world, strategy="COMPARISON", budget={"max_calls": 6, "max_models": 3, "critics": 1})
    cands = [e for e in _entries(world["db"], t) if e.role == "candidate"]
    assert len({e.model_id for e in cands}) == 3
    assert all(e.status == "ok" and e.text for e in cands)


# ------------------------------------------------------------------ 5 · role specialists: generate / critique / synthesize
def test_05_specialist_roles_contribute_separate_components(world):
    t = _run(world, strategy="TOURNAMENT", budget={"max_calls": 10, "max_models": 2, "critics": 1, "max_rounds": 0}, quality_target=0.99)
    es = _entries(world["db"], t)
    gen = {e.model_id for e in es if e.role == "candidate"}
    critics = {c["critic"] for e in es for c in (e.critiques or [])}
    synth = [e for e in es if e.role == "synthesis"]
    assert gen and critics and synth
    assert len(synth[0].sources) == 2  # built from both candidates
    for e in es:
        assert all(c["critic"] != e.model_id for c in (e.critiques or [])), "a critic never grades its own work"


# ------------------------------------------------------------------ 6 · synthesis is never a paste-up
def test_06_synthesis_combines_instead_of_concatenating(world, monkeypatch):
    db = world["db"]
    # make the paster the strongest-looking model, so it is chosen as synthesizer
    _profile(db, "local:paster", "songwriting", 0.95, "c1" * 8)
    t = _run(world, strategy="TOURNAMENT", budget={"max_calls": 10, "max_models": 2, "critics": 1, "max_rounds": 0}, quality_target=0.99)
    synth = [e for e in _entries(db, t) if e.role == "synthesis"]
    assert synth and synth[0].status == "rejected" and "concatenation" in synth[0].error
    assert t.result_entry_id != synth[0].id
    # a real synthesizer is accepted and keeps its sources
    from app.models import ModelProfile

    db.query(ModelProfile).delete()
    db.commit()
    _profile(db, "local:poet-good", "songwriting", 0.95, "a1" * 8)
    t2 = _run(world, strategy="TOURNAMENT", budget={"max_calls": 10, "max_models": 2, "critics": 1, "max_rounds": 0}, quality_target=0.99,
              use_cache=False, brief=BRIEF + " (andra försöket)")
    s2 = [e for e in _entries(db, t2) if e.role == "synthesis"][0]
    assert s2.status == "ok" and s2.sources and "lyktan lyser" in s2.text


# ------------------------------------------------------------------ 7 · independent quality evaluation finds weak outputs
def test_07_independent_evaluation_identifies_the_weak_output(world):
    t = _run(world, strategy="COMPARISON", budget={"max_calls": 6, "max_models": 2, "critics": 1})
    es = {e.model_id: e for e in _entries(world["db"], t) if e.role == "candidate"}
    good, weak = es["local:poet-good"], es["local:poet-weak"]
    assert good.score > weak.score + 0.3
    assert any("clichés" in n for n in weak.deterministic["notes"]) and weak.deterministic["checks"]["language"] == 0.0
    assert t.result_entry_id == good.id


# ------------------------------------------------------------------ 8 · provider failure → authorised fallback
def test_08_a_failing_provider_is_replaced_by_an_authorised_alternative(world):
    db = world["db"]
    _install(db, [("poet-flaky", "delta", "d1")])
    _profile(db, "local:poet-flaky", "songwriting", 0.99, "d1" * 8)  # ranked first, then fails
    t = _run(world, strategy="COMPARISON", budget={"max_calls": 8, "max_models": 2, "critics": 1})
    es = _entries(db, t)
    assert any(e.model_id == "local:poet-flaky" and e.status == "failed" for e in es)
    assert t.plan["fallbacks"][0]["from"] == "local:poet-flaky"
    assert sum(1 for e in es if e.role == "candidate" and e.status == "ok") == 2
    assert t.status in ("completed", "stopped") and t.result_entry_id


# ------------------------------------------------------------------ 9 · sensitive data never reaches an unapproved provider
def test_09_restricted_briefs_never_reach_an_external_model(world):
    db = world["db"]
    _profile(db, "anthropic:claude-opus-5-5", "songwriting", 1.0, "claude-opus-5-5")
    t = _run(world, mode="BEST_QUALITY", classification="RESTRICTED", strategy="COMPARISON",
             budget={"max_calls": 6, "max_models": 3, "critics": 1, "max_usd": 0.4})
    assert world["ext"].calls == []
    assert all(not m.startswith("anthropic:") for m in t.plan["contestants"] + t.plan["critics"])
    assert any(x["model"].startswith("anthropic:") and "privacy" in x["why"] for x in t.plan["excluded"])


# ------------------------------------------------------------------ 10 · quotas and rate limits
def test_10_a_rate_limited_provider_is_paused_and_not_hammered(world):
    from app.creative import providers as P

    db = world["db"]
    world["ext"].rate_limit_models = {"claude-haiku-5-5"}
    with pytest.raises(Exception):
        P.call_model(db, "anthropic:claude-haiku-5-5", system="s", prompt="p", max_tokens=50)
    n = len(world["ext"].calls)
    r = P.choose_models(db, BRIEF, mode="BEST_VALUE", n=3)
    assert all(not m.startswith("anthropic:") for m in r["chosen"])
    assert any(x["model"].startswith("anthropic:") and "paused" in x["why"] for x in r["excluded"])
    with pytest.raises(Exception):
        P.call_model(db, "anthropic:claude-sonnet-5-5", system="s", prompt="p", max_tokens=50)
    assert len(world["ext"].calls) == n  # backing off: no new request reached the provider


# ------------------------------------------------------------------ 11 · hard budgets
def test_11_hard_budgets_cannot_be_bypassed(world):
    from app.creative import tournament as T
    from app.models import BudgetRule

    db = world["db"]
    before = len(world["local"].calls)
    t = _run(world, strategy="TOURNAMENT", budget={"max_calls": 3, "max_models": 6, "critics": 3, "max_rounds": 4}, quality_target=0.99)
    assert len(world["local"].calls) - before <= 3 and t.usage["calls"] <= 3
    assert "budget" in t.stop_reason or "exceeded" in t.stop_reason
    assert T.Budget.of({"max_models": 27, "critics": 9, "max_calls": 500}).max_models == 6  # 27 models is not a tournament
    # the platform's own budgets hold too: a global model-call limit stops the tournament's calls before they run
    db.add(BudgetRule(scope_kind="global", scope_id="*", metric="model_calls", period="day", limit=1, enabled=True, created_by="t"))
    db.commit()
    before = len(world["local"].calls)
    t2 = _run(world, strategy="COMPARISON", budget={"max_calls": 6, "max_models": 3, "critics": 1}, brief=BRIEF + " igen", use_cache=False)
    assert len(world["local"].calls) - before <= 1
    assert any("BudgetExceeded" in e.error for e in _entries(db, t2) if e.status == "failed")
    # paid spending above the autonomous limit waits for a human — and calls nothing meanwhile
    before = len(world["ext"].calls)
    t3 = _run(world, budget={"max_usd": 5.0}, brief=BRIEF + " med budget")
    assert t3.status == "pending_approval" and t3.approval_id and len(world["ext"].calls) == before


# ------------------------------------------------------------------ 12 · credentials stay protected
def test_12_provider_credentials_never_appear_in_prompts_results_or_api_responses(world, client):
    db = world["db"]
    _profile(db, "anthropic:claude-haiku-5-5", "songwriting", 0.99, "claude-haiku-5-5")
    r = client.post("/api/creative/tournaments", json={"brief": BRIEF, "strategy": "COMPARISON", "wait": True, "budget": {
        "max_calls": 6, "max_models": 2, "critics": 1, "max_usd": 0.2}})
    assert r.status_code == 200, r.text
    assert world["ext"].calls, "the external model took part"
    blob = json.dumps([c for p in (world["local"], world["ext"]) for c in p.calls])
    for path in (f"/api/creative/tournaments/{r.json()['id']}", "/api/creative/providers", "/api/creative/overview", "/api/creative/costs"):
        blob += client.get(path).text
    assert SECRET not in blob


# ------------------------------------------------------------------ 13 · model version change → re-evaluation
def test_13_a_model_version_change_marks_its_profile_stale_and_due(world):
    from app.creative import perf
    from app.creative import providers as P
    from app.models import LocalModel

    db = world["db"]
    _profile(db, "local:poet-good", "songwriting", 0.9, "a1" * 8)
    assert not any(d["model"] == "local:poet-good" for d in perf.due(db))
    m = db.query(LocalModel).filter(LocalModel.key == "poet-good").first()
    m.sha256_actual = "z9" * 8  # a new file behind the same name
    db.commit()
    assert any(d["model"] == "local:poet-good" and "version changed" in d["reason"] for d in perf.due(db))
    r = P.choose_models(db, BRIEF, mode="SPECIALIST", n=3)
    row = next(x for x in r["ranked"] if x["model"] == "local:poet-good")
    assert row["stale_profile"] and "re-benchmark" in row["why"]


# ------------------------------------------------------------------ 14 · diminishing returns stop the tournament
def test_14_refinement_stops_on_diminishing_returns(world):
    t = _run(world, strategy="ITERATIVE", budget={"max_calls": 12, "max_models": 1, "critics": 1, "max_rounds": 4}, quality_target=0.99)
    assert "diminishing returns" in t.stop_reason or "nothing specific left" in t.stop_reason
    assert t.usage["calls"] < 12  # it did not spend the budget just because it could


# ------------------------------------------------------------------ 15 · provenance
def test_15_every_output_keeps_its_provenance(world):
    from app.creative import tournament as T
    from app.governance import observability as obs
    from app.models import Document

    db = world["db"]
    t = _run(world, strategy="TOURNAMENT", budget={"max_calls": 10, "max_models": 2, "critics": 1, "max_rounds": 0}, quality_target=0.99)
    for e in _entries(db, t):
        assert e.model_id and e.provider and e.prompt_hash and e.role and e.model_version
        if e.role == "synthesis":
            assert e.sources
    rep = obs.replay(db, t.trace_run_id)
    types = [ev["type"] for ev in rep["events"]]
    assert types[0] == "plan" and "candidate" in types and "critique" in types and types[-1] == "stop"
    doc = db.get(Document, T.save_to_vault(db, t, _admin(db)))
    assert doc.evidence_class == "model_generated" and f"#{t.id}" in doc.description and "critics" in doc.description


# ------------------------------------------------------------------ 16 · authorised cache reuse
def test_16_a_repeated_brief_reuses_the_accepted_result_without_model_calls(world):
    db = world["db"]
    t1 = _run(world, strategy="COMPARISON", budget={"max_calls": 6, "max_models": 2, "critics": 1}, quality_target=0.6)
    assert t1.status == "completed"
    before = len(world["local"].calls)
    t2 = _run(world, strategy="COMPARISON", budget={"max_calls": 6, "max_models": 2, "critics": 1}, quality_target=0.6)
    assert len(world["local"].calls) == before and t2.usage["cache_hit"] == t1.id and t2.final_score == t1.final_score
    # a CONFIDENTIAL result is not served to somebody else
    from app.models import User

    other = User(email="someone@example.com", password_hash="x", role="operator")
    db.add(other)
    db.commit()
    t3 = _run(world, strategy="COMPARISON", budget={"max_calls": 6, "max_models": 2, "critics": 1}, quality_target=0.6,
              classification="CONFIDENTIAL", brief=BRIEF + " (konfidentiell)")
    t4 = _run(world, user=other, strategy="COMPARISON", budget={"max_calls": 6, "max_models": 2, "critics": 1}, quality_target=0.6,
              classification="CONFIDENTIAL", brief=BRIEF + " (konfidentiell)")
    assert t3.status == "completed" and "cache_hit" not in (t4.usage or {})


# ------------------------------------------------------------------ 17 · repeatable cross-provider quality comparison
def test_17_benchmarks_compare_models_reproducibly(world):
    from app.creative import perf

    db = world["db"]
    a = perf.run(db, ["local:poet-good", "local:poet-weak"], categories=["songwriting", "poetry"])
    b = perf.run(db, ["local:poet-good", "local:poet-weak"], categories=["songwriting", "poetry"])
    assert a["results"] == b["results"]  # deterministic scoring: same outputs, same scores
    g, w = a["results"]["local:poet-good"]["songwriting"]["score"], a["results"]["local:poet-weak"]["songwriting"]["score"]
    assert g > w
    tab = perf.table(db)
    assert {"songwriting", "poetry", "overall"} <= set(tab["categories"])


# ------------------------------------------------------------------ 18 · works when a provider is down
def test_18_the_workflow_keeps_working_when_a_provider_is_unavailable(world):
    world["router"].breakers["anthropic"].open_until = 9e18  # external API circuit open
    t = _run(world, mode="BEST_QUALITY", strategy="COMPARISON", budget={"max_calls": 6, "max_models": 2, "critics": 1, "max_usd": 0.4})
    assert t.result_entry_id and t.status in ("completed", "stopped")
    assert any(x["model"].startswith("anthropic:") and "circuit open" in x["why"] for x in t.plan["excluded"])


# ------------------------------------------------------------------ governance around the API
def test_api_permissions_and_agents_cannot_approve_providers(world, client):
    from app.governance.policy import Request, decide

    db = world["db"]
    d = decide(db, Request(action="providers.approve", agent_id="creative_director"))
    assert not d.allowed and d.category_name == "PROHIBITED"
    assert client.post("/api/creative/select", json={"brief": BRIEF, "mode": "FREE_FIRST"}).json()["chosen"]
    r = client.post("/api/creative/auth-check", json={})
    assert r.status_code in (404, 405)
    from fastapi.testclient import TestClient

    from app.main import app

    client.post("/api/auth/users", json={"email": "viewer@example.com", "password": "correct-horse-battery", "role": "viewer"})
    v = TestClient(app)
    v.headers["Authorization"] = "Bearer " + v.post("/api/auth/login", json={"email": "viewer@example.com", "password": "correct-horse-battery"}).json()["token"]
    assert v.post("/api/creative/tournaments", json={"brief": BRIEF, "wait": True}).status_code == 403
    assert v.get("/api/creative/models").status_code == 200
    assert client.get("/api/creative/discovery").json()["validation_path"]
