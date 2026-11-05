"""DAEMON CORE: admin access, routing policy (offline/privacy/spend/quota), cache, credentials, model library,
prompts, tools, internal AI API, benchmarks, optimisation, recovery. Uses stub providers — no model files needed."""
import hashlib
import io
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.ai import llm
from app.ai.llm import LLMResult
from app.ai.providers import Completion, ProviderUnavailable
from app.ai.router import LLMRouter, LLMUnavailable
from app.daemon import bench, catalog, credentials, hardware, policy, prompts, quota, state, tools


class Stub:
    def __init__(self, pid, text="ok", *, fail=None, cost=0.0, locality=None):
        self.id, self.text, self.fail, self.cost, self.calls = pid, text, fail, cost, []
        if locality:
            self.locality = locality

    def configured(self):
        return True

    def health(self):
        return {"configured": True}

    def complete(self, *, model, system, prompt, schema, effort, max_tokens):
        self.calls.append((model, max_tokens))
        if self.fail:
            raise ProviderUnavailable(self.fail)
        return Completion(self.text, None, self.id, model, 100, 20, self.cost, 5)

    def stream(self, **_):
        yield self.text


def _login(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    return r


# ------------------------------------------------------------------ admin access
def test_cli_create_admin_reset_and_last_admin_guard(fresh_db, monkeypatch, capsys):
    from app import cli
    from app.models import User

    monkeypatch.setattr("sys.stdin", io.StringIO("first-long-password\n"))
    assert cli.main(["create-admin", "--email", "Owner@Example.com", "--password-stdin"]) == 0
    s = fresh_db.SessionLocal()
    u = s.scalars(select(User)).one()
    assert u.email == "owner@example.com" and u.role == "admin"
    tv = u.token_version
    s.close()
    monkeypatch.setattr("sys.stdin", io.StringIO("second-long-password\n"))
    assert cli.main(["reset-password", "--email", "owner@example.com", "--password-stdin"]) == 0
    s = fresh_db.SessionLocal()
    assert s.scalars(select(User)).one().token_version == tv + 1  # old sessions revoked
    s.close()
    with pytest.raises(SystemExit, match="at least one active admin"):
        cli.main(["set-role", "--email", "owner@example.com", "--role", "viewer"])
    monkeypatch.setattr("sys.stdin", io.StringIO("short\n"))
    with pytest.raises(SystemExit, match="at least 10"):
        cli.main(["reset-password", "--email", "owner@example.com", "--password-stdin"])


def test_user_management_api_revokes_tokens(client):
    r = client.post("/api/auth/users", json={"email": "op@example.com", "password": "operator-password-1", "role": "operator"})
    assert r.status_code == 200
    users = client.get("/api/auth/users").json()
    op = next(u for u in users if u["email"] == "op@example.com")
    tok = _login(client, "op@example.com", "operator-password-1").json()["token"]
    hdr = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/auth/me", headers=hdr).status_code == 200
    assert client.patch(f"/api/auth/users/{op['id']}", json={"role": "viewer"}).json()["role"] == "viewer"
    assert client.get("/api/auth/me", headers=hdr).status_code == 401  # role change revokes existing tokens
    client.patch(f"/api/auth/users/{op['id']}", json={"disabled": True})
    assert _login(client, "op@example.com", "operator-password-1").status_code == 401
    me = next(u for u in users if u["email"] == "admin@example.com")
    assert client.patch(f"/api/auth/users/{me['id']}", json={"role": "viewer"}).status_code == 409  # cannot demote self
    r = client.post("/api/auth/password", json={"current_password": "correct-horse-battery", "new_password": "new-horse-battery-9"})
    assert r.status_code == 200 and r.json()["token"]
    assert client.get("/api/auth/me").status_code == 401  # the old admin token is revoked too


# ------------------------------------------------------------------ routing policy
def test_policy_offline_and_privacy_never_reach_external(fresh_db, monkeypatch):
    monkeypatch.delenv("MODEL_CHAIN_STANDARD", raising=False)
    provs = {"local": Stub("local"), "anthropic": Stub("anthropic", locality="external")}
    cands, _ = policy.plan("standard", provs)
    assert [c.provider for c in cands][0] == "local" and any(c.provider == "anthropic" for c in cands)
    s = fresh_db.SessionLocal()
    state.update(s, offline_mode=True)
    s.commit()
    cands, excluded = policy.plan("deep", provs)
    assert all(c.locality != "external" for c in cands)
    assert any(e["status"] == "excluded_offline" for e in excluded)
    state.update(s, offline_mode=False)
    s.commit()
    s.close()
    cands, excluded = policy.plan("deep", provs, sensitivity="private")
    assert all(c.locality != "external" for c in cands) and excluded[0]["status"] == "excluded_privacy"


def test_router_offline_does_not_fall_back_to_external(fresh_db, monkeypatch):
    monkeypatch.delenv("MODEL_CHAIN_STANDARD", raising=False)
    local, ext = Stub("local", fail="local model crashed"), Stub("anthropic", locality="external")
    s = fresh_db.SessionLocal()
    state.update(s, offline_mode=True)
    s.commit()
    s.close()
    with pytest.raises(LLMUnavailable) as e:
        LLMRouter({"local": local, "anthropic": ext}).complete(system="s", prompt="p", tier="standard")
    assert ext.calls == []  # never silently fell back to the external provider
    assert any(a["status"] == "excluded_offline" for a in e.value.attempts)


def test_spend_limit_blocks_paid_calls_and_profiles_cap_tokens(fresh_db, monkeypatch):
    monkeypatch.setenv("MODEL_CHAIN_DEEP", "anthropic:claude-opus-5-5")
    ext = Stub("anthropic", locality="external", cost=0.5)
    s = fresh_db.SessionLocal()
    state.update(s, limits={"monthly_usd": 0.0})
    s.commit()
    with pytest.raises(LLMUnavailable) as e:
        LLMRouter({"anthropic": ext}).complete(system="s", prompt="p", tier="deep")
    assert ext.calls == [] and e.value.attempts[0]["status"] == "spend_blocked"
    monkeypatch.delenv("MODEL_CHAIN_DEEP")
    state.update(s, limits={"monthly_usd": 50.0}, profile="EMERGENCY")
    s.commit()
    s.close()
    local = Stub("local")
    LLMRouter({"local": local}).complete(system="s", prompt="p", tier="deep", max_tokens=4000)
    assert local.calls[0] == ("eco", 256)  # EMERGENCY: smallest local model, short outputs


def test_rate_limit_backs_off_instead_of_hammering(fresh_db, monkeypatch):
    monkeypatch.setenv("MODEL_CHAIN_FAST", "anthropic:claude-haiku-5-5")
    ext = Stub("anthropic", locality="external", fail="anthropic: RateLimitError (429): slow down")
    r = LLMRouter({"anthropic": ext})
    with pytest.raises(LLMUnavailable) as e1:
        r.complete(system="s", prompt="p", tier="fast")
    assert e1.value.attempts[0]["status"] == "rate_limited"
    with pytest.raises(LLMUnavailable) as e2:
        r.complete(system="s", prompt="p", tier="fast")
    assert e2.value.attempts[0]["status"] == "paused" and len(ext.calls) == 1
    assert quota.snapshot()["anthropic"]["rate_limit_events"] == 1


# ------------------------------------------------------------------ gateway cache + costs
class CountingProvider:
    name = "stub"

    def __init__(self):
        self.calls = 0

    def complete(self, *, system, prompt, tier="standard", schema=None, max_tokens=1000):
        self.calls += 1
        return LLMResult('{"label": "negative", "confidence": 0.9}', {"label": "negative", "confidence": 0.9}, "claude-haiku-5-5",
                         120, 10, 0.01, "anthropic", 7,
                         [{"provider": "anthropic", "model": "claude-haiku-5-5", "tier": tier, "status": "ok", "input_tokens": 120,
                           "output_tokens": 10, "cost_usd": 0.01, "latency_ms": 7, "locality": "external"}])


def test_response_cache_and_cost_dashboard(client):
    stub = CountingProvider()
    llm.set_provider(stub)
    body = {"text": "Leveransen var sen.", "labels": ["positive", "negative", "neutral"]}
    a = client.post("/api/ai/classify", json=body).json()
    b = client.post("/api/ai/classify", json=body).json()
    assert a["label"] == b["label"] == "negative" and stub.calls == 1 and b["served_from_cache"]
    c = client.get("/api/daemon/costs").json()
    assert c["totals"]["cache_hits"] == 1 and c["savings"]["actual_usd"] == pytest.approx(0.01)
    assert c["totals"]["external_cost_usd"] == pytest.approx(0.01)
    assert "estimate" in c["note"].lower() or "authoritative" in c["note"].lower()


def test_classify_rejects_labels_outside_the_set(client):
    class Bad(CountingProvider):
        def complete(self, **kw):
            r = super().complete(**kw)
            r.data = {"label": "furious"}
            return r

    llm.set_provider(Bad())
    r = client.post("/api/ai/classify", json={"text": "x", "labels": ["a", "b"], "cache": False})
    assert r.status_code == 502


# ------------------------------------------------------------------ credentials
def test_credentials_encrypted_owner_attested_and_admin_only(client, fresh_db):
    bad = client.post("/api/daemon/credentials", json={"provider": "anthropic", "secret": "sk-test-1234567890", "attestation": "yes"})
    assert bad.status_code == 403
    r = client.post("/api/daemon/credentials", json={"provider": "anthropic", "secret": "sk-test-1234567890", "label": "main",
                                                     "attestation": credentials.ATTESTATION})
    assert r.status_code == 200
    body = r.json()
    assert "secret" not in body and "secret_enc" not in body and body["fingerprint"].startswith("…7890")
    from app.models import ProviderCredential

    s = fresh_db.SessionLocal()
    row = s.scalars(select(ProviderCredential)).one()
    assert "sk-test-1234567890" not in row.secret_enc  # encrypted at rest
    s.close()
    assert credentials.secret_for("anthropic") == "sk-test-1234567890"
    listing = client.get("/api/daemon/credentials").text
    assert "sk-test-1234567890" not in listing
    client.post(f"/api/daemon/credentials/{body['id']}/rotate", json={"secret": "sk-test-rotated-0000"})
    assert credentials.secret_for("anthropic") == "sk-test-rotated-0000"
    client.delete(f"/api/daemon/credentials/{body['id']}")
    assert credentials.secret_for("anthropic") is None
    client.post("/api/auth/users", json={"email": "op2@example.com", "password": "operator-password-2", "role": "operator"})
    tok = _login(client, "op2@example.com", "operator-password-2").json()["token"]
    assert client.get("/api/daemon/credentials", headers={"Authorization": f"Bearer {tok}"}).status_code == 403
    assert client.patch("/api/daemon/settings", json={"offline_mode": True}, headers={"Authorization": f"Bearer {tok}"}).status_code == 403


# ------------------------------------------------------------------ model library
def test_library_verifies_checksums_activates_and_rolls_back(client, fresh_db, tmp_path, monkeypatch):
    monkeypatch.setenv("MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setattr(hardware, "runtime_available", lambda: {"llama_cpp": True})
    blobs = {}
    for key in ("tiny-a", "tiny-b"):
        f = tmp_path / f"{key}.gguf"
        f.write_bytes(key.encode() * 1000)
        blobs[key] = f
        e = catalog.CatalogEntry(key, key, "test", "chat", "1M", "Q8_0", "example/repo", f"{key}.gguf", "apache-2.0",
                                 hashlib.sha256(f.read_bytes()).hexdigest(), f.stat().st_size, 2048, ("en",), ("text",), "chat")
        monkeypatch.setitem(catalog.BY_KEY, key, e)
        monkeypatch.setattr(catalog, "CATALOG", [*catalog.CATALOG, e])
    lib = client.get("/api/daemon/library").json()
    assert all(m["commercial_use"] in ("permitted", "review_required") for m in lib["models"])
    assert client.post("/api/daemon/library/activate", json={"slot": "chat", "key": "tiny-a"}).status_code == 409  # not installed
    wrong = tmp_path / "wrong.gguf"
    wrong.write_bytes(b"tampered")
    assert "checksum mismatch" in client.post("/api/daemon/library/tiny-a/import-file", json={"path": str(wrong)}).json()["detail"]
    for key, f in blobs.items():
        assert client.post(f"/api/daemon/library/{key}/import-file", json={"path": str(f)}).json()["status"] == "installed"
    assert client.post("/api/daemon/library/activate", json={"slot": "chat", "key": "tiny-a"}).status_code == 200
    assert client.post("/api/daemon/library/activate", json={"slot": "embedding", "key": "tiny-a"}).status_code == 409  # wrong kind
    client.post("/api/daemon/library/activate", json={"slot": "chat", "key": "tiny-b"})
    assert client.post("/api/daemon/library/rollback", json={"slot": "chat"}).json()["active"] == "tiny-a"
    assert client.delete("/api/daemon/library/tiny-a").status_code == 409  # active models cannot be removed
    assert client.delete("/api/daemon/library/tiny-b").json()["status"] == "removed"


def test_offline_mode_disables_downloads(client):
    client.patch("/api/daemon/settings", json={"offline_mode": True})
    assert client.post("/api/daemon/library/qwen2.5-0.5b-instruct-q4_k_m/install").status_code == 409


# ------------------------------------------------------------------ prompts, context, tools
def test_prompt_versions_and_rollback(fresh_db):
    s = fresh_db.SessionLocal()
    v1 = prompts.active(s, "ai.summarize")
    prompts.create_version(s, "ai.summarize", "Summarise in {max_words} words:\n{text}", "admin", activate=True)
    assert prompts.active(s, "ai.summarize").version == 2
    with pytest.raises(ValueError):
        prompts.render(s, "ai.summarize", text="x")
    prompts.activate_version(s, "ai.summarize", v1.version, "admin")
    assert prompts.active(s, "ai.summarize").version == 1
    s.close()


def test_context_assembly_keeps_evidence_and_drops_duplicates():
    items = [{"text": "Rule: cite sources.", "kind": "instruction"}, {"text": "Source A says X. " * 50, "kind": "evidence"},
             {"text": "Background chatter " * 200, "kind": "background", "score": 0.1},
             {"text": "Source A says X. " * 50, "kind": "evidence"}]
    out = prompts.assemble_context(items, budget_tokens=400)
    kinds = [i["kind"] for i in out["items"]]
    assert kinds.count("evidence") == 1 and "instruction" in kinds and "background" not in kinds
    assert {d["reason"] for d in out["dropped"]} == {"duplicate", "budget"}
    tight = prompts.assemble_context(items, budget_tokens=50)
    assert tight["over_budget"] and tight["note"]  # evidence is never silently cut


def test_tools_are_permissioned_and_code_execution_is_blocked(client):
    assert client.post("/api/daemon/tools/calc/invoke", json={"expression": "2*(3+4)"}).json()["result"] == 14
    assert client.post("/api/daemon/tools/calc/invoke", json={"expression": "__import__('os')"}).status_code == 422
    assert client.post("/api/daemon/tools/code.execute/invoke", json={"code": "print(1)"}).status_code == 403
    assert client.post("/api/daemon/tools/calc/invoke", json={"expression": "1", "x": 1}).status_code == 422
    with pytest.raises(ValueError):
        tools._calc("9**999")


# ------------------------------------------------------------------ internal AI API
def test_internal_ai_api_auth_and_honest_unavailability(client):
    from fastapi.testclient import TestClient

    from app.main import app

    anon = TestClient(app)
    for path in ("/api/ai/chat", "/api/ai/generate", "/api/ai/classify", "/api/ai/embeddings", "/api/ai/reason", "/api/ai/agents/execute"):
        assert anon.post(path, json={}).status_code == 401
    assert anon.get("/api/ai/status").status_code == 401
    r = client.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "Hej"}]})
    assert r.status_code == 503  # no provider: an honest error, never invented output
    st = client.get("/api/ai/status").json()
    assert st["independence"]["independent"] is False and st["independence"]["mandatory_external_runtime_dependencies"]
    e = client.post("/api/ai/embeddings", json={"texts": ["solar lantern"], "kind": "query"}).json()
    assert e["local"] and e["dims"] > 0


def test_chat_uses_gsus_identity_whatever_the_model(client):
    seen = {}

    class Echo(CountingProvider):
        def complete(self, *, system, prompt, **kw):
            seen["system"] = system
            return super().complete(system=system, prompt=prompt, **kw)

    llm.set_provider(Echo())
    r = client.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "Vem är du?"}]})
    assert r.status_code == 200 and r.json()["identity"] == "G-SUS"
    assert "G-SUS" in seen["system"] and "Never fabricate" in seen["system"]


def test_agents_execute_runs_through_orchestrator(client):
    r = client.post("/api/ai/agents/execute", json={"type": "compliance.check", "payload": {"title": "LED camping lantern", "category": "lighting"}})
    assert r.status_code in (200, 409)
    if r.status_code == 200:
        assert r.json()["status"] in ("succeeded", "blocked", "failed")


# ------------------------------------------------------------------ benchmark + optimiser + recovery + self-test
def test_benchmark_reports_cost_per_success(fresh_db):
    class Half:
        def complete(self, *, model, system, prompt, schema, effort, max_tokens):
            text = "positive" if "lamp" in prompt else "OK" if "exactly the word OK" in prompt else "nonsense"
            return Completion(text, None, "local", model, 50, 5, 0.0, 400)

    s = fresh_db.SessionLocal()
    br = bench.run(s, provider=Half(), provider_id="local", model="stub", actor="test")
    assert br.summary["passed"] >= 2 and 0 < br.summary["accuracy"] < 1
    assert br.summary["cost_per_success_usd"] is not None and br.summary["energy_wh_estimate"] > 0
    s.close()


def test_optimizer_proposes_cache_for_repeated_paid_prompts(client, fresh_db):
    from app.models import LLMCall

    s = fresh_db.SessionLocal()
    for _ in range(4):
        s.add(LLMCall(provider="anthropic", model="claude-sonnet-5-5", tier="standard", status="ok", input_tokens=900, output_tokens=50,
                      cost_usd=0.003, purpose="trend.summary", prompt_hash="abc", locality="external"))
    s.commit()
    s.close()
    created = client.post("/api/daemon/proposals/generate").json()
    kinds = {p["kind"] for p in created["proposals"]}
    assert "enable_cache" in kinds and "install_local" in kinds
    pid = next(p["id"] for p in created["proposals"] if p["kind"] == "enable_cache")
    assert client.post(f"/api/daemon/proposals/{pid}/decide", json={"approve": True}).json()["status"] == "approved"
    assert client.post("/api/daemon/proposals/generate").json()["created"] == 0  # deduplicated


def test_interrupted_tasks_are_requeued_after_restart(fresh_db):
    from app.agents.catalog import build_orchestrator
    from app.models import Task

    s = fresh_db.SessionLocal()
    t1 = Task(type="ceo.weekly_review", agent_id="ceo", status="running", attempts=1, max_attempts=3, payload={}, dedupe_key="r1")
    t2 = Task(type="ceo.weekly_review", agent_id="ceo", status="running", attempts=3, max_attempts=3, payload={}, dedupe_key="r2")
    s.add_all([t1, t2])
    s.commit()
    assert build_orchestrator().recover_interrupted(s) == {"requeued": 1, "failed": 1}
    assert s.get(Task, t1.id).status == "queued" and s.get(Task, t2.id).status == "failed"
    s.close()


def test_selftest_runs_real_checks(client):
    out = client.post("/api/daemon/selftest?generate=false").json()
    names = {c["check"] for c in out["checks"]}
    assert {"database", "local_chat_model", "local_embeddings", "no_external_fallback_in_offline", "agents"} <= names
    assert next(c for c in out["checks"] if c["check"] == "no_external_fallback_in_offline")["ok"]


def test_finetune_feasibility_is_honest(client):
    f = client.get("/api/daemon/finetune/feasibility").json()
    assert f["foundation_model_training"]["feasible"] is False
    d = client.post("/api/daemon/finetune/datasets", json={"name": "support-replies", "contains_private_data": True}).json()
    assert d["status"] == "blocked_no_consent"


def test_provider_registry_has_no_invented_quotas(client):
    provs = client.get("/api/daemon/providers").json()
    gem = next(p for p in provs if p["id"] == "google-gemini")
    assert gem["status"] == "unverified" and all("unknown" in str(v) for v in gem["facts"].values())
    anth = next(p for p in provs if p["id"] == "anthropic")
    assert "not assumed" in anth["facts"]["free_tier"]
    r = client.post("/api/daemon/providers/google-gemini/verify", json={"source_url": "https://ai.google.dev/pricing", "facts": {}})
    assert r.json()["last_verified_at"] and r.json()["verified_by"] == "admin@example.com"


def test_activation_history_is_audited(client, fresh_db):
    from app.models import AuditLog

    client.patch("/api/daemon/settings", json={"profile": "ECO"})
    s = fresh_db.SessionLocal()
    assert s.scalars(select(AuditLog).where(AuditLog.action == "daemon.settings")).first() is not None
    s.close()
    assert datetime.now(UTC)  # keep import used
