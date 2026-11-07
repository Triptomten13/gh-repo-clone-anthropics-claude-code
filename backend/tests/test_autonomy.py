"""Model Hunter, Model Championship, Devil's Advocate and Account Vault — with a fake Hugging Face Hub (httpx.MockTransport),
fake models and fake service endpoints. No network: the real runs are in docs/AUTONOMY.md."""
from __future__ import annotations

import hashlib
import json

import httpx
import pytest

WEIGHTS = b"GGUF" + b"\x00" * 4096  # a tiny stand-in file; only its checksum matters to the installer
SHA = hashlib.sha256(WEIGHTS).hexdigest()


def _hub(calls: list[str], size_good: int = len(WEIGHTS)) -> httpx.Client:
    repos = {
        "Qwen/Qwen3-0.6B-GGUF": {"sha": "r1", "license": "apache-2.0", "gated": False, "tags": ["gguf"], "files": [("Qwen3-0.6B-Q4_K_M.gguf", size_good, SHA), ("Qwen3-0.6B-Q8_0.gguf", 900_000_000, "x" * 64)]},
        "big/Model-70B-GGUF": {"sha": "r2", "license": "apache-2.0", "gated": False, "tags": ["gguf"], "files": [("Model-70B-Q4_K_M.gguf", 42_000_000_000, "y" * 64)]},
        "someone/Qwen3-4B-abliterated-GGUF": {"sha": "r3", "license": "apache-2.0", "gated": False, "tags": ["gguf", "abliterated"], "files": [("q-Q4_K_M.gguf", 2_000_000_000, "z" * 64)]},
        "corp/Gated-1B-GGUF": {"sha": "r4", "license": "other", "gated": True, "tags": ["gguf"], "files": [("g-Q4_K_M.gguf", 700_000_000, "w" * 64)]},
        "old/pickle-model": {"sha": "r5", "license": "mit", "gated": False, "tags": ["pytorch"], "files": [("pytorch_model.bin", 500_000_000, "v" * 64)]},
        "speech/asr-0.6b-GGUF": {"sha": "r6", "license": "apache-2.0", "gated": False, "tags": ["gguf"], "pipeline": "automatic-speech-recognition",
                                 "files": [("asr-Q4_K_M.gguf", 400_000_000, "u" * 64)]},
    }

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.path)
        p = req.url.path
        if p == "/api/models":
            return httpx.Response(200, json=[{"id": k, "sha": v["sha"], "downloads": 100, "likes": 5, "tags": v["tags"], "gated": v["gated"]} for k, v in repos.items()])
        for k, v in repos.items():
            if p == f"/api/models/{k}":
                return httpx.Response(200, json={"id": k, "sha": v["sha"], "gated": v["gated"], "tags": v["tags"] + [f"license:{v['license']}"],
                                                 "pipeline_tag": v.get("pipeline", "text-generation"),
                                                 "cardData": {"license": v["license"]}, "downloads": 100, "likes": 5,
                                                 "gguf": {"total": 600_000_000, "context_length": 40960}})
            if p == f"/api/models/{k}/tree/main":
                return httpx.Response(200, json=[{"path": f, "size": s, "lfs": {"oid": o, "size": s}} for f, s, o in v["files"]])
            if p.startswith(f"/{k}/resolve/"):
                return httpx.Response(200, content=WEIGHTS)
        return httpx.Response(404, json={})

    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://huggingface.co")


@pytest.fixture()
def db(fresh_db, monkeypatch, tmp_path):
    monkeypatch.setenv("MODELS_DIR", str(tmp_path / "models"))
    s = fresh_db.SessionLocal()
    yield s
    s.close()


def _approve(db, approval_id: int, by: str = "approver@example.com") -> None:
    from app.governance import core as gov
    from app.models import Approval

    gov.decide_approval(db, db.get(Approval, approval_id), True, by)
    db.commit()


# ================================================================== Devil's Advocate
def test_the_advocate_flags_bad_decisions_and_passes_good_ones():
    from app.autonomy import advocate

    cal = advocate.calibrate()
    assert cal["correct"] == cal["total"], [r for r in cal["cases"] if not r["ok"]]
    assert cal["good_passed"] == cal["good_total"] >= 2 and cal["bad_flagged"] == cal["bad_total"] >= 6


def test_it_blocks_only_on_policy_and_security_and_says_so_when_sound(db):
    from app.autonomy import advocate

    good = advocate.review(db, advocate._good_acq())
    assert good.verdict == "sound" and "checks passed" in good.summary and len(good.checks) >= 10
    board = advocate.review(db, {**advocate._good_acq(), "measured": False, "evidence": ["#1 on a public leaderboard"]})
    assert board.verdict == "concerns" and not any(f["blocking"] for f in board.findings)
    f = next(f for f in board.findings if f["code"] == "evidence.not_measured")
    assert f["alternative"] and f["evidence"] and f["confidence"] > 0  # every finding: evidence, consequence, alternative, confidence
    pickle = advocate.review(db, {**advocate._good_acq(), "format": "pytorch_model.bin"})
    assert pickle.verdict == "block" and pickle.status == "escalated"


def test_it_challenges_g_sus_plans_too(db):
    from app.autonomy import advocate

    plan = {"kind": "plan", "ref": "gsus:1", "proposer": "agent:gsus", "summary": "launch the product", "objective": "launch",
            "evidence": ["evaluation 0.82"], "alternatives": ["wait a week"], "risks": ["returns"], "verification": "sales after 7 days",
            "steps": [{"action": "product.launch", "level": 4}, {"action": "research", "level": 0}]}
    c = advocate.review(db, plan)
    assert c.verdict == "block" and any(f["code"] == "plan.unapproved_step" for f in c.findings)
    approved = advocate.review(db, {**plan, "steps": [{"action": "product.launch", "level": 4, "approval_id": 7}]})
    assert approved.verdict != "block"


def test_the_model_review_is_independent_and_cannot_rubber_stamp_or_block(db, monkeypatch):
    from app.autonomy import advocate
    from app.creative import providers as P

    seen = {}
    fams = [P.ModelCandidate(id="local:qwen2.5-1.5b", provider="local", model="qwen2.5-1.5b", display="Q", locality="local", cost_class="local",
                             family="qwen2.5", capabilities=["text"]),
            P.ModelCandidate(id="local:smollm2-360m", provider="local", model="smollm2-360m", display="S", locality="local", cost_class="local",
                             family="smollm2", capabilities=["text"])]
    monkeypatch.setattr(P, "available_models", lambda db: fams)
    monkeypatch.setattr(P, "profiles", lambda db, ids=None: {})

    def fake_call(db, model_id, **kw):
        seen["reviewer"] = model_id
        return {"text": json.dumps({"findings": [
            {"weakness": "the gain is within noise", "evidence": "0.71 vs 0.66 on 2 tasks", "consequence": "a wasted download", "alternative": "run 3 more tasks", "severity": "important"},
            {"weakness": "I just feel it is wrong", "evidence": "", "alternative": "", "severity": "important"}]})}

    monkeypatch.setattr(P, "call_model", fake_call)
    c = advocate.review(db, {**advocate._good_acq(), "proposer_model": "local:qwen2.5-1.5b"}, use_model=True)
    assert seen["reviewer"] == "local:smollm2-360m"  # never the proposer's family
    model_findings = [f for f in c.findings if f["source"] != "rules"]
    assert len(model_findings) == 1 and model_findings[0]["evidence"]  # the evidence-free objection was dropped
    assert c.verdict == "concerns" and not any(f["blocking"] for f in model_findings)


def test_agreement_monitor_warns_about_a_rubber_stamp(db):
    from app.autonomy import advocate

    for _ in range(21):
        advocate.review(db, advocate._good_acq())
    db.commit()
    a = advocate.agreement(db)
    assert a["sound_share"] > 0.9 and "rubber-stamp" in a["warning"]


# ================================================================== Model Hunter
def test_discovery_screens_before_any_download_and_skips_unchanged_repositories(db):
    from app.autonomy import hunter
    from app.models import ModelCandidate

    calls: list[str] = []
    r = hunter.discover(db, "small", client=_hub(calls))
    assert not any("/resolve/" in c for c in calls)  # nothing downloaded during discovery
    rows = {c.repo: c for c in db.query(ModelCandidate)}
    assert rows["Qwen/Qwen3-0.6B-GGUF"].status == "shortlisted" and rows["Qwen/Qwen3-0.6B-GGUF"].quantization == "Q4_K_M"
    assert rows["Qwen/Qwen3-0.6B-GGUF"].parameters_b == 0.6  # from the GGUF header, not guessed from the name
    assert "measured" in " ".join(rows["Qwen/Qwen3-0.6B-GGUF"].reasons)
    assert rows["big/Model-70B-GGUF"].status == "screened_out" and "storage budget" in rows["big/Model-70B-GGUF"].reasons[0]
    assert rows["someone/Qwen3-4B-abliterated-GGUF"].status == "screened_out" and "safety" in rows["someone/Qwen3-4B-abliterated-GGUF"].reasons[0]
    assert rows["corp/Gated-1B-GGUF"].status == "screened_out" and "gated" in rows["corp/Gated-1B-GGUF"].reasons[0]
    assert rows["old/pickle-model"].status == "screened_out" and "pickle" in rows["old/pickle-model"].reasons[0]
    assert rows["speech/asr-0.6b-GGUF"].status == "screened_out" and "automatic-speech-recognition" in rows["speech/asr-0.6b-GGUF"].reasons[0]
    assert r["shortlisted"] == 1 and r["screened_out"] == 5
    calls.clear()
    again = hunter.discover(db, "small", client=_hub(calls))
    assert again["unchanged"] == 6 and calls == ["/api/models"]  # change detection: one search request, no details


def test_acquisition_is_reviewed_approved_by_someone_else_then_verified(db):
    from app.autonomy import hunter
    from app.models import Critique, LocalModel, ModelCandidate

    hunter.discover(db, "small", client=_hub([]))
    c = db.query(ModelCandidate).filter_by(repo="Qwen/Qwen3-0.6B-GGUF").one()
    with pytest.raises(ValueError, match="only shortlisted"):
        hunter.request_acquisition(db, db.query(ModelCandidate).filter_by(repo="big/Model-70B-GGUF").one().id, actor="admin@example.com")
    c = hunter.request_acquisition(db, c.id, actor="admin@example.com", user_email="admin@example.com")
    crit = db.get(Critique, c.critique_id)
    assert crit.verdict == "concerns" and any(f["code"] == "evidence.not_measured" for f in crit.findings)  # popularity is not evidence
    assert c.status == "pending_approval" and c.approval_id
    with pytest.raises(PermissionError):
        hunter.acquire(db, c.id, actor="admin@example.com", client=_hub([]))
    _approve(db, c.approval_id)
    c = hunter.acquire(db, c.id, actor="admin@example.com", client=_hub([]))
    assert c.status == "installed", c.reasons
    m = db.query(LocalModel).filter_by(key=c.local_key).one()
    assert m.status == "installed" and m.sha256_actual == SHA and m.license == "apache-2.0"
    assert "Qwen/Qwen3-0.6B-GGUF@r1" in m.license_evidence and "Model Hunter" in m.notes  # licence re-checked live at install time


def test_a_changed_upstream_file_is_refused(db):
    from app.autonomy import hunter
    from app.models import ModelCandidate

    hunter.discover(db, "small", client=_hub([]))
    c = db.query(ModelCandidate).filter_by(repo="Qwen/Qwen3-0.6B-GGUF").one()
    c = hunter.request_acquisition(db, c.id, actor="admin@example.com", user_email="admin@example.com")
    _approve(db, c.approval_id)
    c = hunter.acquire(db, c.id, actor="admin@example.com", client=_hub([], size_good=len(WEIGHTS) + 1))  # upstream size changed
    assert c.status == "failed" and "changed" in c.reasons[-1]


def test_agents_cannot_grant_themselves_a_download(db):
    from app.governance.policy import Request, decide

    d = decide(db, Request(action="models.acquire", agent_id="model_hunter"))
    assert not d.allowed and d.category_name in ("APPROVAL_REQUIRED", "RESTRICTED")


# ================================================================== Model Championship
def _result(acc: float, tps: float, cost: float, song: float) -> dict:
    return {"accuracy": acc, "by_skill": {"reasoning": acc}, "tokens_per_s": tps, "latency_p50_ms": 1000 / tps, "cost_per_success_usd": cost,
            "creative": {"songwriting": song}}


def test_championship_compares_like_for_like_and_shows_what_improved(db, monkeypatch):
    from app.autonomy import championship as C
    from app.models import LocalModel

    for key in ("old-small", "old-big"):
        db.add(LocalModel(key=key, display_name=key, family="x", kind="chat", status="installed", file_path=__file__, size_bytes=1))
    db.commit()
    first = {"old-small": _result(0.64, 20, 0.0002, 0.43), "old-big": _result(0.82, 6, 0.0009, 0.75)}
    monkeypatch.setattr(C, "_measure", lambda db, m, actor, provider: first[m.key])
    a = C.run(db, actor="t", provider=object())
    assert a.status == "completed" and "first championship" in a.deltas["verdict"]
    assert a.standings["accuracy (17 tasks)"][0]["model"] == "old-big" and a.standings["speed (tokens/s)"][0]["model"] == "old-small"
    assert a.standings["latency p50 (ms)"][0]["model"] == "old-small"  # lower is better
    # a new contender joins: better songwriting, same accuracy as the best
    db.add(LocalModel(key="new-mid", display_name="new", family="y", kind="chat", status="installed", file_path=__file__, size_bytes=1))
    db.commit()
    second = {**first, "new-mid": _result(0.82, 12, 0.0004, 0.83)}
    monkeypatch.setattr(C, "_measure", lambda db, m, actor, provider: second[m.key])
    b = C.run(db, actor="t", provider=object())
    ch = {c["category"]: c for c in b.deltas["changes"]}
    assert b.deltas["previous"] == a.id and ch["creative: songwriting"]["kind"] == "smarter" and ch["creative: songwriting"]["new_leader"]
    assert "accuracy (17 tasks)" not in ch  # no change in the best accuracy → not claimed
    assert "smarter" in b.deltas["verdict"]
    # a different machine is never compared with this one
    monkeypatch.setattr(C, "fingerprint", lambda: {"cpu": "other", "cores": 64})
    c = C.run(db, actor="t", provider=object())
    assert c.deltas["previous"] is None


def test_championship_respects_its_time_budget(db, monkeypatch):
    from app.autonomy import championship as C
    from app.models import LocalModel

    for key in ("a", "b"):
        db.add(LocalModel(key=key, display_name=key, family="x", kind="chat", status="installed", file_path=__file__, size_bytes=1))
    db.commit()
    monkeypatch.setattr(C, "_measure", lambda db, m, actor, provider: _result(0.5, 10, 0.001, 0.5))
    ch = C.run(db, actor="t", provider=object(), max_seconds=-1)
    assert all("time budget" in r["error"] for r in ch.results.values())


# ================================================================== Account Vault
JUST = {k: "answered" for k in ("service", "usefulness", "existing", "capabilities", "terms", "ownership", "permissions", "costs",
                               "alternative_integration", "decision")}
TOKEN = "hf_secret_TOKEN_must_never_leak_123456"


def _services(seen: list[httpx.Request]) -> httpx.Client:
    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.headers.get("authorization") == f"Bearer {TOKEN}":
            return httpx.Response(200, json={"name": "rocky-org", "login": "rocky-org"})
        return httpx.Response(401, json={"error": "bad token"})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_vault_connects_only_after_four_eyes_and_never_exposes_the_secret(client, fresh_db, approver, monkeypatch):
    from app.autonomy import accounts as A
    from app.daemon.credentials import ATTESTATION
    from app.governance import tool_gateway as G
    from app.models import AuditLog, LLMCall, ToolGrant, ToolInvocation

    db = fresh_db.SessionLocal()
    a = A.propose(db, service="huggingface", identity="rocky-org", purpose="higher rate limits for the Model Hunter", scopes=["read-repos"],
                  justification=JUST, level=2, requested_by="user:admin@example.com")
    assert a.status == "pending_approval" and a.approval_id
    with pytest.raises(PermissionError):
        A.connect(db, a.id, TOKEN, attestation=ATTESTATION, actor="admin@example.com", client=_services([]))
    assert approver.post(f"/api/approvals/{a.approval_id}/decide", json={"approve": True}).status_code == 200
    db.expire_all()
    seen: list[httpx.Request] = []
    a = A.connect(db, a.id, TOKEN, attestation=ATTESTATION, actor="admin@example.com", client=_services(seen))
    assert a.status == "connected" and a.health["ok"] and a.health["identity"] == "rocky-org"
    # an agent gets a GRANT with the account's scope — the tool function sees the token, the agent sees the account name
    db.add(ToolGrant(subject_kind="agent", subject_id="model_hunter", tool="hf.whoami", operations=["READ"], credential_scope=A.scope_of(a), created_by="t"))
    db.commit()
    monkeypatch.setattr(httpx, "get", lambda url, headers, timeout: _services(seen).get(url, headers=headers))
    out = G.invoke(db, "hf.whoami", {}, agent_id="model_hunter")
    db.commit()
    assert out["status"] == "ok" and out["result"]["identity"] == "rocky-org"
    blob = json.dumps([out, client.get("/api/accounts").json(), client.get(f"/api/accounts/{a.id}/uses").json()], default=str)
    for rows in (db.query(AuditLog).all(), db.query(LLMCall).all(), db.query(ToolInvocation).all()):
        blob += json.dumps([{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in rows], default=str)
    assert TOKEN not in blob  # not in results, API responses, audit, model calls or tool records
    assert any(u["action"] == "vault.use" and u["actor"] == "agent:model_hunter" for u in client.get(f"/api/accounts/{a.id}/uses").json())
    # revoke: grants removed, credential disabled, the tool no longer works
    A.revoke(db, a.id, actor="admin@example.com", reason="test")
    assert db.query(ToolGrant).filter_by(credential_scope=A.scope_of(a)).count() == 0
    denied = None
    try:
        G.invoke(db, "hf.whoami", {}, agent_id="model_hunter")
    except G.GatewayDenied as e:
        denied = e
    assert denied is not None
    db.close()


def test_agents_get_least_privilege_and_no_duplicates(db):
    from app.autonomy import accounts as A
    from app.models import Critique

    bad = A.propose(db, service="github", identity="demonkoncernen", purpose="let agents manage everything", scopes=["admin:org", "delete_repo"],
                    justification=JUST, level=2, requested_by="agent:dev_division")
    assert bad.status == "rejected" and db.get(Critique, bad.critique_id).verdict == "block"
    ok = A.propose(db, service="github", identity="demonkoncernen", purpose="open pull requests on project repositories",
                   scopes=["contents:read", "pull_requests:write"], justification=JUST, level=2, requested_by="user:admin@example.com")
    assert ok.status == "pending_approval"
    dup = A.propose(db, service="github", identity="demonkoncernen", purpose="again", scopes=["contents:read"], justification=JUST,
                    level=2, requested_by="user:admin@example.com")
    assert any(f["code"] == "account.duplicate" for f in db.get(Critique, dup.critique_id).findings)
    prepared = A.propose(db, service="gitlab", identity="dk", purpose="prepare only", scopes=["read_api"], justification=JUST, level=1,
                         requested_by="agent:dev_division")
    assert prepared.status == "proposed" and prepared.approval_id is None  # levels 0–1 prepare; nothing is connected


def test_api_routes_are_permissioned_and_honest(client, fresh_db):
    r = client.get("/api/advocate").json()
    assert r["calibration"]["correct"] == r["calibration"]["total"] and len(r["protocol"]) == 12
    assert client.get("/api/hunter").status_code == 200
    ch = client.post("/api/championships", json={})
    assert ch.status_code == 409 and "no installed chat model" in ch.json()["detail"]
    acc = client.get("/api/accounts").json()
    assert "a person signs up" in acc["services"]["huggingface"]["signup"] and "CAPTCHA" in acc["services"]["github"]["signup"]
    assert all("secret" not in k for a in acc["accounts"] for k in a)


# ================================================================== the Devil's Advocate challenges G-SUS itself
def test_g_sus_consequential_plans_are_challenged_before_anything_runs(client, fresh_db, monkeypatch):
    from app.agents.catalog import build_orchestrator
    from app.autonomy import advocate
    from app.models import Critique, GsusRun, Task

    client.post("/api/demo")
    orch = build_orchestrator()
    ceo = orch.agents[orch.routes["ceo.evaluate_product"]]
    monkeypatch.setattr(ceo, "level", 0)
    low = client.post("/api/gsus/runs", json={"objective": "Evaluate the winter commuter pannier and create brand concepts"}).json()
    db = fresh_db.SessionLocal()
    levels = [getattr(orch.agents[orch.routes[s["task_type"]]], "level", 0) for s in low["steps"] if s["task_type"]]
    if max(levels) < 3:
        assert "critique_id" not in (db.get(GsusRun, low["id"]).settings or {})  # routine plans are not interrogated
    monkeypatch.setattr(ceo, "level", 4)  # make the plan consequential
    r = client.post("/api/gsus/runs", json={"objective": "Evaluate the magnetic LED reading lamp"}).json()
    s = db.get(GsusRun, r["id"]).settings
    crit = db.get(Critique, s["critique_id"])
    assert crit.subject_ref == f"gsus:{r['id']}" and crit.proposer == "agent:gsus" and crit.verdict == "concerns"
    assert any(f["code"] == "protocol.alternatives" for f in crit.findings)  # G-SUS did not say what else it considered
    assert r["status"] != "blocked"  # the level-4 step is gated by an approval already — not blocked twice
    # when the Devil's Advocate blocks, nothing is executed
    before = db.query(Task).count()
    real = advocate.review
    monkeypatch.setattr(advocate, "review", lambda db_, d, **kw: real(db_, {**d, "cost_usd": 9.0, "budget_usd": 1.0}, **kw))
    b = client.post("/api/gsus/runs", json={"objective": "Evaluate the magnetic LED reading lamp"}).json()
    assert b["status"] == "blocked" and "Devil's Advocate stopped this plan" in b["answer"]
    db.expire_all()
    assert db.query(Task).count() == before  # no task was submitted
    db.close()


def test_an_unchanged_model_scoring_differently_is_variance_not_progress(db, monkeypatch):
    """Found in the first real championships: unchanged models moved by up to 0.29 between two runs (sampling at
    temperature 0.2, random seed), and the comparison called it 'smarter'. Now: controls set a noise floor, only a new or
    changed model leading by more than that floor counts — and championships decode greedily."""
    from app.autonomy import championship as C
    from app.models import LocalModel

    for key in ("inc-a", "inc-b"):
        db.add(LocalModel(key=key, display_name=key, family="x", kind="chat", status="installed", file_path=__file__, size_bytes=1))
    db.commit()
    seen = {}

    def measure(db_, m, actor, provider):
        from app.daemon.runtime import _DETERMINISTIC

        seen[m.key] = _DETERMINISTIC.get()
        return runs[m.key]

    monkeypatch.setattr(C, "_measure", measure)
    runs = {"inc-a": {**_result(0.60, 10, 0.001, 0.50), "version": "v1"}, "inc-b": {**_result(0.70, 5, 0.002, 0.70), "version": "v1"}}
    C.run(db, actor="t", provider=object())
    assert all(seen.values())  # every contender measured with greedy decoding
    # same models, same versions, different luck: inc-a's songwriting jumps 0.50 → 0.80 and takes the lead
    runs = {"inc-a": {**_result(0.60, 10, 0.001, 0.80), "version": "v1"}, "inc-b": {**_result(0.70, 5, 0.002, 0.70), "version": "v1"}}
    b = C.run(db, actor="t", provider=object())
    assert not b.deltas["changes"] and b.deltas["variance"][0]["category"] == "creative: songwriting"
    assert "no attributable improvement" in b.deltas["verdict"] and "variance" in b.deltas["verdict"]
    # a newcomer that leads by MORE than the noise floor is progress; one that leads by less is not
    db.add(LocalModel(key="new", display_name="new", family="y", kind="chat", status="installed", file_path=__file__, size_bytes=1))
    db.commit()
    runs = {"inc-a": {**_result(0.60, 10, 0.001, 0.50), "version": "v1"}, "inc-b": {**_result(0.70, 5, 0.002, 0.70), "version": "v1"},
            "new": {**_result(0.95, 6, 0.002, 0.85), "version": "n1"}}
    c = C.run(db, actor="t", provider=object())
    acc = next(x for x in c.deltas["changes"] if x["category"] == "accuracy (17 tasks)")
    assert acc["kind"] == "smarter" and acc["attributed_to"] == "new"
    assert not any(x["category"] == "creative: songwriting" for x in c.deltas["changes"])  # 0.85 vs 0.80: within inc-a's 0.30 noise


def test_thin_evidence_is_challenged_even_when_every_question_is_answered(db):
    """Real review 2026-11-07: switching the chat model on a one-task margin (17 tasks) passed as sound."""
    from app.autonomy import advocate

    base = {"kind": "model_selection", "ref": "chat", "summary": "switch the chat model", "objective": "better answers", "evidence": ["0.706 vs 0.588"],
            "alternatives": ["keep it"], "assumptions": ["tasks are representative"], "risks": ["small sample"], "verification": "next championship",
            "would_change_if": "no gain next time", "permissions": ["daemon.slot.activate"], "cost_usd": 0, "measured": True}
    assert advocate.review(db, base).verdict == "sound"
    thin = advocate.review(db, {**base, "sample_size": 17, "margin_tasks": 1, "conditions_note": "thinking off for all; the incumbent is a thinking model"})
    codes = {f["code"] for f in thin.findings}
    assert thin.verdict == "concerns" and {"evidence.small_sample", "evidence.conditions"} <= codes
