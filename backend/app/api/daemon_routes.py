"""DAEMON CORE API.

Internal AI API (model-independent; agents and apps call these, never a vendor SDK):
  POST /api/ai/chat · /generate · /embeddings · /classify · /reason · /agents/execute   GET /api/ai/health · /status
Administration (/api/daemon/*): hardware, settings (offline mode, profile, limits), model library, self-test, prompts,
tools, provider registry, credentials, costs, benchmarks, optimisation proposals, workers, fine-tuning lab.
Every state change is audited; settings, models, credentials and providers are admin-only.
"""
from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.llm import get_router
from ..ai.router import LLMRefused, LLMUnavailable
from ..daemon import (bench, catalog, consistency, costs, credentials, finetune, gateway, hardware, library, optimizer, policy, prompts,
                      quota, registry_seed, selftest, state, tools, workers)
from ..db import SessionLocal, get_db
from ..governance import core as gov
from ..models import (BenchmarkRun, ModelWorker, OptimizationProposal, PromptVersion, ProviderCredential, ProviderRecord, Task,
                      TrainingDataset, User)
from ..security.auth import current_user, require_role
from ..security.untrusted import wrap

router = APIRouter(prefix="/api")
operator = require_role("admin", "operator")
admin = require_role("admin")
Sensitivity = Literal["normal", "private", "sensitive"]


def _cols(o: Any, exclude: set[str] | None = None) -> dict[str, Any]:
    ex = exclude or set()
    return {c.key: getattr(o, c.key) for c in o.__table__.columns if c.key not in ex}


def _ai_error(e: Exception) -> HTTPException:
    if isinstance(e, LLMRefused):
        return HTTPException(422, f"model declined: {e}")
    if isinstance(e, LLMUnavailable):
        return HTTPException(503, {"error": str(e), "attempts": getattr(e, "attempts", [])})
    return HTTPException(500, f"{type(e).__name__}: {e}")


# =================================================================== internal AI API
class ChatMsg(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=60_000)


class ChatIn(BaseModel):
    messages: list[ChatMsg] = Field(min_length=1, max_length=40)
    tier: Literal["fast", "standard", "deep"] = "standard"
    profile: str | None = None
    sensitivity: Sensitivity = "normal"
    max_tokens: int = Field(1024, ge=1, le=16000)
    workflow: str = ""
    project: str = ""


@router.post("/ai/chat")
def ai_chat(c: ChatIn, db: Session = Depends(get_db), user: User = Depends(operator)):
    """Conversation through the G-SUS identity layer — the same identity whichever model serves it."""
    system = prompts.active(db, "gsus.identity").text
    transcript, ctx_info = _chat_context(db, c.messages[:-1])
    prompt = (f"Conversation so far:\n{transcript}\n\n" if transcript else "") + f"USER: {c.messages[-1].content}"
    try:
        out = gateway.complete(db, system=system, prompt=prompt, tier=c.tier, max_tokens=c.max_tokens, sensitivity=c.sensitivity,
                               profile=c.profile, agent_id="gsus", purpose="ai.chat", workflow=c.workflow or "chat", project=c.project)
    except Exception as e:
        raise _ai_error(e) from e
    return {"reply": out["text"], "identity": "G-SUS", "context": ctx_info, **{k: v for k, v in out.items() if k != "text"}}


CHAT_HISTORY_BUDGET = 1200  # estimated tokens of history sent with each turn
KEEP_RECENT = 4


def _chat_context(db: Session, history: list[ChatMsg]) -> tuple[str, dict[str, Any]]:
    """Hierarchical context: recent turns verbatim; older turns summarised once by the small model (cached), so long
    conversations do not resend everything every turn. If no model can summarise, the oldest turns are dropped and that
    is reported — never silently."""
    lines = [f"{m.role.upper()}: {m.content}" for m in history]
    full = "\n".join(lines)
    est = prompts.estimate_tokens(full)
    info: dict[str, Any] = {"history_turns": len(history), "history_tokens_est": est, "budget": CHAT_HISTORY_BUDGET, "summarized": False, "dropped_turns": 0}
    if est <= CHAT_HISTORY_BUDGET:
        info["sent_tokens_est"] = est
        return full, info
    old, recent = lines[:-KEEP_RECENT], lines[-KEEP_RECENT:]
    try:
        r = gateway.complete(db, system="You compress conversations faithfully. Keep names, numbers, decisions and open questions.",
                             prompt=prompts.render(db, "ai.summarize", max_words=150, text="\n".join(old)), tier="fast", max_tokens=300,
                             cacheable=True, purpose="chat.summarize", workflow="chat")
        text = f"[Summary of {len(old)} earlier turns — generated]\n{r['text']}\n" + "\n".join(recent)
        info["summarized"] = True
    except Exception:
        keep: list[str] = []
        for ln in reversed(lines):
            if prompts.estimate_tokens("\n".join([ln, *keep])) > CHAT_HISTORY_BUDGET:
                break
            keep.insert(0, ln)
        info["dropped_turns"] = len(lines) - len(keep)
        text = "\n".join(keep)
    info["sent_tokens_est"] = prompts.estimate_tokens(text)
    return text, info


class GenerateIn(BaseModel):
    prompt: str | None = Field(None, max_length=120_000)
    prompt_name: str | None = None
    variables: dict[str, Any] = {}
    system: str | None = Field(None, max_length=20_000)
    tier: Literal["fast", "standard", "deep"] = "standard"
    profile: str | None = None
    sensitivity: Sensitivity = "normal"
    json_schema: dict[str, Any] | None = None
    max_tokens: int = Field(1024, ge=1, le=16000)
    cache: bool = False
    workflow: str = ""
    project: str = ""


@router.post("/ai/generate")
def ai_generate(g: GenerateIn, db: Session = Depends(get_db), user: User = Depends(operator)):
    if not g.prompt and not g.prompt_name:
        raise HTTPException(422, "prompt or prompt_name required")
    try:
        text = prompts.render(db, g.prompt_name, **g.variables) if g.prompt_name else g.prompt
    except (LookupError, ValueError) as e:
        raise HTTPException(422, str(e)) from e
    system = g.system or prompts.active(db, "gsus.identity").text
    try:
        return gateway.complete(db, system=system, prompt=text or "", tier=g.tier, schema=g.json_schema, max_tokens=g.max_tokens,
                                sensitivity=g.sensitivity, profile=g.profile, cacheable=g.cache, agent_id=f"user:{user.id}",
                                purpose=g.prompt_name or "ai.generate", workflow=g.workflow, project=g.project)
    except Exception as e:
        raise _ai_error(e) from e


class EmbedIn(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=64)
    kind: Literal["document", "query"] = "document"


@router.post("/ai/embeddings")
def ai_embeddings(e: EmbedIn, _: User = Depends(operator)):
    from ..knowledge.process import embedder

    mid, fn = embedder()
    vecs = fn([t[:8000] for t in e.texts], kind=e.kind)
    return {"model": mid, "dims": len(vecs[0]) if vecs else 0, "vectors": vecs, "local": True,
            "semantic": mid.startswith(("gguf:", "ollama:"))}


class ClassifyIn(BaseModel):
    text: str = Field(max_length=20_000)
    labels: list[str] = Field(min_length=2, max_length=30)
    sensitivity: Sensitivity = "normal"
    cache: bool = True


@router.post("/ai/classify")
def ai_classify(c: ClassifyIn, db: Session = Depends(get_db), _: User = Depends(operator)):
    """Small-model task: routed to the fast tier (local eco model first)."""
    schema = {"type": "object", "properties": {"label": {"type": "string", "enum": c.labels}, "confidence": {"type": "number"}},
              "required": ["label"]}
    prompt = prompts.render(db, "ai.classify", labels=", ".join(c.labels), text=wrap(c.text, source_id="classify-input"))
    try:
        out = gateway.complete(db, system="You are a precise classifier. Output JSON only.", prompt=prompt, tier="fast", schema=schema,
                               max_tokens=64, sensitivity=c.sensitivity, cacheable=c.cache, purpose="ai.classify", workflow="classify")
    except Exception as e:
        raise _ai_error(e) from e
    label = (out.get("data") or {}).get("label")
    if label not in c.labels:
        raise HTTPException(502, {"error": "model returned a label outside the allowed set", "raw": out.get("text", "")[:200]})
    return {"label": label, "confidence": (out.get("data") or {}).get("confidence"), "confidence_note": "self-reported by the model",
            **{k: v for k, v in out.items() if k not in ("text", "data")}}


class ReasonIn(BaseModel):
    question: str = Field(max_length=20_000)
    context: str = Field("", max_length=60_000)
    verify: bool = False
    samples: int = Field(1, ge=1, le=5)  # >1 = self-consistency: majority vote over independent reasoning samples
    sensitivity: Sensitivity = "normal"


@router.post("/ai/reason")
def ai_reason(r: ReasonIn, db: Session = Depends(get_db), _: User = Depends(operator)):
    """Deep tier. samples>1 = self-consistency (majority vote, early stop once a majority is reached);
    verify=true asks a second, different model for an independent answer (critical decisions)."""
    ctx = wrap(r.context, source_id="reason-context") if r.context else "(none)"
    prompt = prompts.render(db, "ai.reason", question=r.question, context=ctx)
    system = prompts.active(db, "gsus.identity").text
    try:
        first = gateway.complete(db, system=system, prompt=prompt, tier="deep", max_tokens=1500, sensitivity=r.sensitivity,
                                 purpose="ai.reason", workflow="reason")
    except Exception as e:
        raise _ai_error(e) from e
    runs = [first]
    while r.samples > 1 and len(runs) < r.samples and not consistency.settled([x["text"] for x in runs], r.samples):
        try:
            runs.append(gateway.complete(db, system=system, prompt=prompt, tier="deep", max_tokens=1500, sensitivity=r.sensitivity,
                                         purpose="ai.reason.sample", workflow="reason"))
        except Exception as e:  # a failed extra sample is reported; the vote uses what exists
            runs.append({"text": "", "error": str(e)[:200], "model": "", "provider": ""})
    sc = None
    if r.samples > 1:
        v = consistency.vote([x["text"] for x in runs])
        first = runs[v["index"]]
        sc = {"samples": len(runs), "planned": r.samples, "finals": v["finals"], "agreement": v["agreement"], "majority": v["majority"],
              "note": "majority of independent samples of the same model — raises confidence, does not prove correctness"
                      + ("" if v["majority"] else "; NO majority: treat the answer as unreliable")}
    out: dict[str, Any] = {"answer": first["text"], "model": first["model"], "provider": first["provider"], "attempts": first.get("attempts", []),
                           "reasoning": (first.get("reasoning") or "")[:8000], "reasoning_complete": not first.get("reasoning_truncated"),
                           "reasoning_note": ("the model's own working notes — unverified, shown for transparency"
                                              + (". The thinking budget ran out: the answer was concluded from incomplete reasoning — treat it "
                                                 "as lower confidence (raise local.thinking_tokens or use verify=true)" if first.get("reasoning_truncated") else ""))
                           if first.get("reasoning") else ""}
    if sc:
        out["self_consistency"] = sc
    if r.verify:
        second_tier = "standard"  # a different model from the deep one (local chat model, or the standard external tier)
        try:
            second = gateway.complete(db, system=system, prompt=prompt + "\n\nAnswer independently and briefly.", tier=second_tier,
                                      max_tokens=800, sensitivity=r.sensitivity, purpose="ai.reason.verify", workflow="reason")
            out["verification"] = {"model": second["model"], "provider": second["provider"], "answer": second["text"],
                                   "independent": (second["provider"], second["model"]) != (first["provider"], first["model"]),
                                   "note": "compare both answers; agreement between different models raises confidence, it does not prove correctness"}
        except Exception as e:
            out["verification"] = {"error": str(e)[:300], "independent": False}
    return out


class ExecIn(BaseModel):
    type: str
    payload: dict[str, Any] = {}
    wait: bool = True


@router.post("/ai/agents/execute")
def ai_agents_execute(x: ExecIn, db: Session = Depends(get_db), user: User = Depends(operator)):
    """Run an agent task through the local orchestrator (budgets, permissions, approvals, kill switch all apply)."""
    from .routes import orch

    try:
        task = orch.submit(db, x.type, x.payload, requested_by=f"user:{user.email}")
    except Exception as e:
        raise HTTPException(409, str(e)) from e
    gov.audit(db, user.email, "task.submit", f"task:{task.id}", type=x.type, via="ai.agents.execute")
    db.commit()
    if x.wait:
        orch.drain(50)
    s = SessionLocal()
    try:
        t = s.get(Task, task.id)
        return {"task_id": t.id, "agent_id": t.agent_id, "status": t.status, "result": t.result, "error": t.error}
    finally:
        s.close()


@router.get("/ai/health")
def ai_health(_: User = Depends(current_user)):
    from ..knowledge.process import embedder

    return {"providers": get_router().health(), "embeddings": embedder()[0], "quota": quota.snapshot()}


@router.get("/ai/status")
def ai_status(db: Session = Depends(get_db), _: User = Depends(current_user)):
    """Fetched on every page view by the shell header — cached 3 s (L1), invalidated on settings/model changes."""
    from ..daemon import cache

    return cache.get("ai-status", 3, maxsize=4).get_or_set("status", lambda: _ai_status(db))


def _ai_status(db: Session) -> dict[str, Any]:
    st = state.load(db)
    snap = hardware.snapshot()
    router_ = get_router()
    provs = router_._all_providers()
    chains = {}
    for tier in ("fast", "standard", "deep"):
        c, ex = policy.plan(tier, provs)
        chains[tier] = {"order": [f"{x.provider}:{x.model} ({x.locality}{'' if provs.get(x.provider) is not None and provs[x.provider].configured() else ' · not configured'})"
                                  for x in c],
                        "excluded": [f"{e['provider']}:{e['model']} — {e['status']}" for e in ex]}
    chat, eco, deep, emb = (library.resolve(db, s) for s in ("chat", "eco", "deep", "embedding"))
    return {
        "offline_mode": st["offline_mode"], "profile": st["profile"], "profiles": policy.PROFILE_INFO, "external_allowed": st["external_allowed"],
        "active_models": {"chat": chat.key if chat else None, "eco": eco.key if eco else None, "deep": deep.key if deep else None,
                          "embedding": emb.key if emb else None},
        "chains": chains, "hardware": {"cpu": snap["cpu"]["model"], "cores": snap["cpu"]["usable_cores"],
                                       "ram_total_gb": round(snap["ram_total_bytes"] / 1e9, 1), "accelerator": snap["accelerator"],
                                       "runtime": snap["runtime"]},
        "independence": selftest.independence(db),
    }


# =================================================================== DAEMON administration
@router.get("/daemon/hardware")
def d_hardware(_: User = Depends(current_user)):
    return hardware.snapshot()


class SettingsPatch(BaseModel):
    offline_mode: bool | None = None
    profile: Literal["ECO", "BALANCED", "PERFORMANCE", "DEEP", "LOW_MEMORY", "SPECIALIST", "OFFLINE", "EMERGENCY"] | None = None
    external_allowed: bool | None = None
    limits: dict[str, Any] | None = None
    cache: dict[str, Any] | None = None
    energy: dict[str, float] | None = None
    local: dict[str, Any] | None = None
    paused_providers: list[str] | None = None


@router.get("/daemon/settings")
def d_settings(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return state.load(db)


@router.patch("/daemon/settings")
def d_settings_patch(p: SettingsPatch, db: Session = Depends(get_db), user: User = Depends(admin)):
    changes = p.model_dump(exclude_none=True)
    for k in ("daily_usd", "monthly_usd"):
        v = (changes.get("limits") or {}).get(k)
        if v is not None and (not isinstance(v, (int, float)) or v < 0):
            raise HTTPException(422, f"limits.{k} must be a non-negative number or null")
    tt = (changes.get("local") or {}).get("thinking_tokens")
    if tt is not None and (not isinstance(tt, int) or not 128 <= tt <= 32768):
        raise HTTPException(422, "local.thinking_tokens must be an integer between 128 and 32768")
    new = state.update(db, **changes)
    gov.audit(db, user.email, "daemon.settings", "daemon", **changes)
    db.commit()
    return new


@router.get("/daemon/library")
def d_library(db: Session = Depends(get_db), _: User = Depends(current_user)):
    out = library.listing(db)
    db.commit()
    return {"models": out, "catalog_verified_at": catalog.CATALOG_VERIFIED_AT, "permissive_licences": sorted(catalog.PERMISSIVE)}


_installs: set[str] = set()


def _install_bg(key: str, actor: str) -> None:
    s = SessionLocal()
    try:
        library.install(s, key, actor)
    except Exception:  # recorded on the row + audit log by library.install
        s.rollback()
    finally:
        _installs.discard(key)
        s.close()


@router.post("/daemon/library/{key}/install")
def d_install(key: str, db: Session = Depends(get_db), user: User = Depends(admin)):
    if key not in catalog.BY_KEY:
        raise HTTPException(404, "not in the verified catalog")
    if state.load(db)["offline_mode"]:
        raise HTTPException(409, "offline mode is on — downloads are disabled (use import-file)")
    if key in _installs:
        raise HTTPException(409, "install already running")
    _installs.add(key)
    gov.audit(db, user.email, "daemon.model.install_requested", key)
    db.commit()
    threading.Thread(target=_install_bg, args=(key, user.email), daemon=True).start()
    return {"started": True, "key": key}


class ImportIn(BaseModel):
    path: str


@router.post("/daemon/library/{key}/import-file")
def d_import(key: str, i: ImportIn, db: Session = Depends(get_db), user: User = Depends(admin)):
    try:
        return _cols(library.import_file(db, key, i.path, user.email))
    except library.LibraryError as e:
        raise HTTPException(409, str(e)) from e


class ActivateIn(BaseModel):
    slot: Literal["chat", "eco", "deep", "embedding"]
    key: str | None


@router.post("/daemon/library/activate")
def d_activate(a: ActivateIn, db: Session = Depends(get_db), user: User = Depends(admin)):
    try:
        return library.activate(db, a.slot, a.key, user.email)
    except library.LibraryError as e:
        raise HTTPException(409, str(e)) from e


class SlotIn(BaseModel):
    slot: Literal["chat", "eco", "deep", "embedding"]


@router.post("/daemon/library/rollback")
def d_rollback(s: SlotIn, db: Session = Depends(get_db), user: User = Depends(admin)):
    try:
        return library.rollback(db, s.slot, user.email)
    except library.LibraryError as e:
        raise HTTPException(409, str(e)) from e


@router.delete("/daemon/library/{key}")
def d_remove(key: str, db: Session = Depends(get_db), user: User = Depends(admin)):
    try:
        return _cols(library.remove(db, key, user.email))
    except library.LibraryError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/daemon/selftest")
def d_selftest(generate: bool = True, db: Session = Depends(get_db), _: User = Depends(operator)):
    return selftest.run(db, generate=generate)


# ---------------------------------------------------------------- prompts & tools
@router.get("/daemon/prompts")
def d_prompts(db: Session = Depends(get_db), _: User = Depends(current_user)):
    prompts.seed(db)
    db.commit()
    rows = db.scalars(select(PromptVersion).order_by(PromptVersion.name, PromptVersion.version.desc())).all()
    return [{**_cols(p), "estimated_tokens": prompts.estimate_tokens(p.text)} for p in rows]


class PromptIn(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9_.-]{2,96}$")
    text: str = Field(min_length=1, max_length=60_000)
    notes: str = ""
    activate: bool = False


@router.post("/daemon/prompts")
def d_prompt_create(p: PromptIn, db: Session = Depends(get_db), user: User = Depends(admin)):
    v = prompts.create_version(db, p.name, p.text, user.email, p.notes, p.activate)
    db.commit()
    return _cols(v)


class PromptActivate(BaseModel):
    version: int


@router.post("/daemon/prompts/{name}/activate")
def d_prompt_activate(name: str, a: PromptActivate, db: Session = Depends(get_db), user: User = Depends(admin)):
    try:
        v = prompts.activate_version(db, name, a.version, user.email)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    db.commit()
    return _cols(v)


class ContextIn(BaseModel):
    items: list[dict[str, Any]]
    budget_tokens: int = Field(4000, ge=100, le=1_000_000)


@router.post("/daemon/context/assemble")
def d_context(c: ContextIn, _: User = Depends(current_user)):
    return prompts.assemble_context(c.items, c.budget_tokens)


@router.get("/daemon/tools")
def d_tools(_: User = Depends(current_user)):
    return [t.public() for t in tools.TOOLS.values()]


@router.post("/daemon/tools/{name}/invoke")
def d_tool_invoke(name: str, args: dict[str, Any], db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        res = tools.invoke(db, user, name, args)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    gov.audit(db, user.email, "tool.invoke", name)
    db.commit()
    return {"tool": name, "result": res}


# ---------------------------------------------------------------- provider registry & credentials
@router.get("/daemon/providers")
def d_providers(db: Session = Depends(get_db), _: User = Depends(current_user)):
    registry_seed.seed(db)
    db.commit()
    st = state.load(db)
    health = {h["provider"]: h for h in get_router().health()}
    return [{**_cols(p), "paused": p.id in st["paused_providers"], "live": health.get("local" if p.id == "local-llamacpp" else p.id)}
            for p in db.scalars(select(ProviderRecord).order_by(ProviderRecord.kind, ProviderRecord.id)).all()]


class VerifyIn(BaseModel):
    source_url: str = Field(min_length=8, max_length=500)
    facts: dict[str, Any] = {}
    notes: str = ""


@router.post("/daemon/providers/{pid}/verify")
def d_provider_verify(pid: str, v: VerifyIn, db: Session = Depends(get_db), user: User = Depends(admin)):
    """A human records what they verified on the provider's official documentation (with the URL)."""
    p = db.get(ProviderRecord, pid)
    if not p:
        raise HTTPException(404)
    p.facts = {**(p.facts or {}), **v.facts, "verified_source": v.source_url}
    p.last_verified_at, p.verified_by, p.notes = datetime.now(UTC), user.email, v.notes or p.notes
    if p.status == "unverified":
        p.status = "not_integrated" if not p.adapter else "operational"
    gov.audit(db, user.email, "provider.verify", pid, source=v.source_url, fields=sorted(v.facts))
    db.commit()
    return _cols(p)


class PauseIn(BaseModel):
    paused: bool


@router.post("/daemon/providers/{pid}/pause")
def d_provider_pause(pid: str, p: PauseIn, db: Session = Depends(get_db), user: User = Depends(admin)):
    st = state.load(db)
    paused = set(st["paused_providers"])
    (paused.add if p.paused else paused.discard)(pid)
    state.update(db, paused_providers=sorted(paused))
    gov.audit(db, user.email, "provider.pause" if p.paused else "provider.resume", pid)
    db.commit()
    return {"provider": pid, "paused": p.paused}


@router.get("/daemon/credentials")
def d_creds(db: Session = Depends(get_db), _: User = Depends(admin)):
    return {"credentials": [credentials.public(c) for c in db.scalars(select(ProviderCredential).order_by(ProviderCredential.id.desc())).all()],
            "attestation_text": credentials.ATTESTATION}


class CredIn(BaseModel):
    provider: str = Field(pattern=r"^[a-z0-9:_.-]{2,48}$")
    secret: str = Field(min_length=8, max_length=4000)
    label: str = ""
    attestation: str
    expires_at: datetime | None = None


@router.post("/daemon/credentials")
def d_cred_add(c: CredIn, db: Session = Depends(get_db), user: User = Depends(admin)):
    try:
        row = credentials.store(db, c.provider, c.secret, label=c.label, attestation=c.attestation, actor=user.email, expires_at=c.expires_at)
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return credentials.public(row)


class RotateIn(BaseModel):
    secret: str = Field(min_length=8, max_length=4000)


@router.post("/daemon/credentials/{cid}/rotate")
def d_cred_rotate(cid: int, r: RotateIn, db: Session = Depends(get_db), user: User = Depends(admin)):
    try:
        return credentials.public(credentials.rotate(db, cid, r.secret, user.email))
    except LookupError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/daemon/credentials/{cid}/validate")
def d_cred_validate(cid: int, db: Session = Depends(get_db), user: User = Depends(admin)):
    try:
        return credentials.validate(db, cid, user.email)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except PermissionError as e:
        raise HTTPException(409, str(e)) from e


@router.delete("/daemon/credentials/{cid}")
def d_cred_disconnect(cid: int, db: Session = Depends(get_db), user: User = Depends(admin)):
    try:
        return credentials.public(credentials.disconnect(db, cid, user.email))
    except LookupError as e:
        raise HTTPException(404, str(e)) from e


# ---------------------------------------------------------------- costs, benchmarks, optimisation
@router.get("/daemon/costs")
def d_costs(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db), _: User = Depends(current_user)):
    return costs.dashboard(db, days)


@router.post("/daemon/cache/purge")
def d_cache_purge(db: Session = Depends(get_db), user: User = Depends(admin)):
    n = gateway.purge_cache(db)
    gov.audit(db, user.email, "daemon.cache.purge", "response_cache", rows=n)
    db.commit()
    return {"purged": n}


@router.get("/daemon/benchmarks")
def d_benchmarks(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return {"tasks": [{"id": t["id"], "skill": t["skill"], "prompt": t["prompt"]} for t in bench.TASKS],
            "runs": [_cols(b) for b in db.scalars(select(BenchmarkRun).order_by(BenchmarkRun.id.desc()).limit(50)).all()]}


class BenchIn(BaseModel):
    provider: str = "local"
    model: str = "chat"
    allow_spend: bool = False


def _bench_bg(provider_id: str, model: str, actor: str, call_model: str) -> None:
    s = SessionLocal()
    try:
        prov = get_router()._all_providers()[provider_id]
        bench.run(s, provider=prov, provider_id=provider_id, model=model, actor=actor, call_model=call_model)
    finally:
        s.close()


@router.post("/daemon/benchmarks/run")
def d_bench_run(b: BenchIn, db: Session = Depends(get_db), user: User = Depends(operator)):
    provs = get_router()._all_providers()
    if b.provider not in provs or not provs[b.provider].configured():
        raise HTTPException(409, f"provider {b.provider} is not configured")
    st = state.load(db)
    loc = policy.provider_locality(b.provider, provs[b.provider])
    if loc == "external":
        if st["offline_mode"]:
            raise HTTPException(409, "offline mode — external benchmarks disabled")
        if not b.allow_spend:
            raise HTTPException(409, "benchmarking an external model spends money: resend with allow_spend=true (explicit authorisation)")
        blocked = quota.spend_check(b.provider, len(bench.TASKS) * policy.estimate_cost(b.provider, b.model, bench.SYSTEM, "x" * 400, 96))
        if blocked:
            raise HTTPException(409, f"spend limit: {blocked}")
    model, call_model = b.model, b.model
    if b.provider == "local" and b.model in ("chat", "eco", "deep"):
        m = library.resolve(db, b.model)
        if not m:
            raise HTTPException(409, f"no local {b.model} model active")
        model = m.key
    gov.audit(db, user.email, "benchmark.run", f"{b.provider}:{model}", allow_spend=b.allow_spend)
    db.commit()
    threading.Thread(target=_bench_bg, args=(b.provider, model, user.email, call_model), daemon=True).start()
    return {"started": True, "provider": b.provider, "model": model, "tasks": len(bench.TASKS)}


@router.get("/daemon/proposals")
def d_proposals(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [_cols(p) for p in db.scalars(select(OptimizationProposal).order_by(OptimizationProposal.id.desc()).limit(200)).all()]


@router.post("/daemon/proposals/generate")
def d_proposals_generate(db: Session = Depends(get_db), user: User = Depends(operator)):
    registry_seed.seed(db)
    new = optimizer.generate(db)
    gov.audit(db, user.email, "optimization.generate", "proposals", created=len(new))
    db.commit()
    return {"created": len(new), "proposals": [_cols(p) for p in new]}


class DecideIn(BaseModel):
    approve: bool


@router.post("/daemon/proposals/{pid}/decide")
def d_proposal_decide(pid: int, d: DecideIn, db: Session = Depends(get_db), user: User = Depends(admin)):
    try:
        o = optimizer.decide(db, pid, d.approve, user.email)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    db.commit()
    return {**_cols(o), "note": "approval records the decision; configuration changes are applied by an admin in DAEMON settings"}


# ---------------------------------------------------------------- distributed workers
@router.get("/daemon/workers")
def d_workers(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [_cols(w) for w in db.scalars(select(ModelWorker).order_by(ModelWorker.id)).all()]


class WorkerIn(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9_-]{2,64}$")
    base_url: str = Field(pattern=r"^https?://")
    models: list[str] = []


@router.post("/daemon/workers")
def d_worker_add(w: WorkerIn, db: Session = Depends(get_db), user: User = Depends(admin)):
    row = workers.register(db, w.name, w.base_url, w.models, user.email)
    h = workers.check(db, row)
    gov.audit(db, user.email, "worker.register", w.name, base_url=w.base_url, locality=row.locality)
    db.commit()
    return {**_cols(row), "health": h, "warning": "this worker is outside your network — it counts as EXTERNAL" if row.locality == "external" else ""}


@router.post("/daemon/workers/{wid}/check")
def d_worker_check(wid: int, db: Session = Depends(get_db), _: User = Depends(operator)):
    w = db.get(ModelWorker, wid)
    if not w:
        raise HTTPException(404)
    h = workers.check(db, w)
    db.commit()
    return {**_cols(w), "health": h}


@router.delete("/daemon/workers/{wid}")
def d_worker_remove(wid: int, db: Session = Depends(get_db), user: User = Depends(admin)):
    w = db.get(ModelWorker, wid)
    if not w:
        raise HTTPException(404)
    db.delete(w)
    gov.audit(db, user.email, "worker.remove", w.name)
    db.commit()
    workers.invalidate()
    return {"removed": wid}


# ---------------------------------------------------------------- fine-tuning lab
@router.get("/daemon/finetune/feasibility")
def d_ft(_: User = Depends(current_user)):
    return finetune.feasibility()


@router.get("/daemon/finetune/datasets")
def d_ft_datasets(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [_cols(d) for d in db.scalars(select(TrainingDataset).order_by(TrainingDataset.id.desc())).all()]


class DatasetIn(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    purpose: str = ""
    source: str = ""
    contains_private_data: bool = False
    consent: Literal["none", "explicit"] = "none"
    record_count: int = 0


@router.post("/daemon/finetune/datasets")
def d_ft_dataset_add(d: DatasetIn, db: Session = Depends(get_db), user: User = Depends(admin)):
    status = "blocked_no_consent" if d.contains_private_data and d.consent != "explicit" else "registered"
    prev = db.scalars(select(TrainingDataset).where(TrainingDataset.name == d.name).order_by(TrainingDataset.version.desc())).first()
    row = TrainingDataset(**d.model_dump(), version=(prev.version + 1) if prev else 1, status=status, created_by=user.email,
                          consent_by=user.email if d.consent == "explicit" else "")
    db.add(row)
    db.flush()
    gov.audit(db, user.email, "dataset.register", f"{d.name}@{row.version}", status=status, private=d.contains_private_data)
    db.commit()
    return _cols(row)
