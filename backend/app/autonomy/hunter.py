"""THE MODEL HUNTER — finds models worth testing, and lets measurement on THIS hardware and OUR tasks decide.

DISCOVER (official Hugging Face API, change detection by revision) → SCREEN (deterministic: single-file GGUF only, licence
stated, not gated, not safety-stripped, fits RAM and the storage budget, not already installed) → REVIEW (Devil's
Advocate) → APPROVE (a person; downloads of discovered models are APPROVAL_REQUIRED) → DOWNLOAD + VERIFY (the existing
verified installer: licence and sha256 re-checked against the live Hub, trusted hosts only) → CHAMPIONSHIP (the same
tasks as every installed model) → only then is anything called "better".

Popularity (downloads, likes) is recorded as metadata and never used as evidence of quality. Nothing is executed from a
repository: GGUF weights are data for llama.cpp, and other formats (pickle weights, custom modelling code) are not
downloaded at all.
"""
from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..governance import core as gov

HUB = "https://huggingface.co"
# What the Hunter searches for. Search terms only narrow the field; the championship decides.
TASKS: dict[str, dict[str, str]] = {
    "general": {"search": "instruct", "why": "general assistant and agent work"},
    "swedish": {"search": "swedish", "why": "Swedish writing and comprehension"},
    "coding": {"search": "coder", "why": "code generation and debugging"},
    "reasoning": {"search": "reasoning", "why": "multi-step reasoning"},
    "small": {"search": "0.6b", "why": "fast, small models for classification and routing"},
    "embedding": {"search": "embedding", "why": "Archive search embeddings"},
}
# What a repository must declare to be useful for the task (Hub `pipeline_tag`, or the equivalent tag). Found in the first
# real run: a search for small models returned speech-recognition, text-to-speech, embedding and reranker GGUFs.
CHAT_PIPELINES = {"text-generation", "image-text-to-text", "conversational"}
TASK_PIPELINES = {"embedding": {"feature-extraction", "sentence-similarity"}}
QUANT_PREFERENCE = ["Q4_K_M", "Q4_K_S", "IQ4_XS", "Q4_0", "Q5_K_M", "Q5_K_S", "Q6_K", "Q8_0"]
SAFETY_TAGS = ("abliterated", "uncensored", "jailbreak", "decensored")
SPLIT = re.compile(r"-\d{5}-of-\d{5}\.gguf$", re.I)
QUANT = re.compile(r"(IQ\d_[A-Z]+|Q\d_K_[SML]|Q\d_K|Q\d_\d|BF16|F16|F32)", re.I)


def max_bytes() -> int:
    return int(float(os.getenv("MODEL_HUNTER_MAX_GB", "6")) * 1e9)


def _client(client: httpx.Client | None) -> httpx.Client:
    return client or httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": "demonkoncernen-model-hunter/1.0"})


def hub_search(query: str, *, limit: int = 20, client: httpx.Client | None = None) -> list[dict[str, Any]]:
    """Official search API; GGUF repositories only; with revision for change detection."""
    c = _client(client)
    params = [("search", query), ("filter", "gguf"), ("sort", "downloads"), ("direction", "-1"), ("limit", str(min(limit, 50)))]
    params += [("expand[]", k) for k in ("sha", "lastModified", "downloads", "likes", "tags", "gated")]
    r = c.get(f"{HUB}/api/models", params=params)
    r.raise_for_status()
    return r.json()


def pick_file(tree: list[dict[str, Any]]) -> dict[str, Any] | None:
    """One single-file GGUF of the preferred quantization (no split shards, no vision projectors)."""
    files = [f for f in tree if str(f.get("path", "")).lower().endswith(".gguf") and f.get("lfs") and not SPLIT.search(f["path"])
             and "mmproj" not in f["path"].lower() and "/" not in f["path"]]
    def rank(f: dict[str, Any]) -> tuple[int, int]:
        m = QUANT.search(f["path"])
        q = m.group(1).upper() if m else ""
        return (QUANT_PREFERENCE.index(q) if q in QUANT_PREFERENCE else 99, f["lfs"].get("size", 0))
    files.sort(key=rank)
    return files[0] if files and rank(files[0])[0] < 99 else None


def details(repo: str, *, client: httpx.Client | None = None) -> dict[str, Any]:
    c = _client(client)
    meta = c.get(f"{HUB}/api/models/{repo}").json()
    tree = c.get(f"{HUB}/api/models/{repo}/tree/main").json()
    f = pick_file(tree if isinstance(tree, list) else [])
    tags = meta.get("tags") or []
    lic = ((meta.get("cardData") or {}).get("license") or next((t.split(":", 1)[1] for t in tags if t.startswith("license:")), "")).lower()
    base = (meta.get("cardData") or {}).get("base_model") or next((t.split(":", 1)[1] for t in tags if t.startswith("base_model:") and t.count(":") == 1), "")
    gg = meta.get("gguf") or {}
    if meta.get("pipeline_tag"):
        tags = [f"pipeline:{meta['pipeline_tag']}", *tags]
    return {"revision": meta.get("sha", ""), "license": lic, "gated": bool(meta.get("gated")), "tags": tags[:40],
            "base_model": base if isinstance(base, str) else (base[0] if base else ""), "downloads": meta.get("downloads", 0),
            "likes": meta.get("likes", 0), "last_modified": meta.get("lastModified", "") or "",
            "parameters_b": round(gg["total"] / 1e9, 2) if gg.get("total") else None, "context_length": gg.get("context_length"),
            "architecture": gg.get("architecture", ""),
            "file": f["path"] if f else "", "size_bytes": f["lfs"].get("size", 0) if f else 0, "sha256": f["lfs"].get("oid", "") if f else "",
            "quantization": (QUANT.search(f["path"]).group(1).upper() if f and QUANT.search(f["path"]) else "")}


def purpose_ok(c: Any) -> tuple[bool, str]:
    """Does the repository declare that it can do the task it was found for?"""
    tags = set(c.tags or [])
    pipeline = next((t.split(":", 1)[1] for t in tags if t.startswith("pipeline:")), "")
    want = TASK_PIPELINES.get(c.task, CHAT_PIPELINES)
    if pipeline in want or (not pipeline and tags & want):
        return True, ""
    return False, (f"not a {'embedding' if c.task == 'embedding' else 'chat / text-generation'} model "
                   f"(declared task: {pipeline or 'none'})")


def rescreen(db: Session) -> int:
    """Re-apply the screening rules to stored candidates (after a rule change) without contacting the Hub."""
    from ..daemon import hardware
    from ..models import LocalModel, ModelCandidate

    snap = hardware.snapshot()
    installed = {m.sha256_actual for m in db.scalars(select(LocalModel).where(LocalModel.status == "installed")) if m.sha256_actual}
    n = 0
    for c in db.scalars(select(ModelCandidate).where(ModelCandidate.status.in_(("discovered", "shortlisted", "screened_out")))):
        screen(c, snap=snap, installed=installed)
        n += 1
    db.commit()
    return n


def screen(c: Any, *, snap: dict[str, Any] | None = None, installed: set[str] | None = None) -> None:
    """Deterministic screening BEFORE any download. Sets c.status and c.reasons (each reason states its evidence)."""
    from ..daemon import catalog, hardware

    reasons: list[str] = []
    status = "shortlisted"
    safety = [t for t in c.tags or [] if any(s in t.lower() for s in SAFETY_TAGS)] + [s for s in SAFETY_TAGS if s in c.repo.lower()]
    if not c.file:
        status, reasons = "screened_out", ["no single-file GGUF in a supported quantization — other formats (pickle weights, repository code) are not run here"]
    elif c.gated:
        status, reasons = "screened_out", ["gated: needs the owner's Hugging Face account and licence acceptance"]
    elif not c.license:
        status, reasons = "screened_out", ["no licence stated in the model card"]
    elif safety:
        status, reasons = "screened_out", [f"safety training removed or bypassed ({', '.join(sorted(set(safety)))})"]
    elif not (declared := purpose_ok(c))[0]:
        status, reasons = "screened_out", [declared[1]]
    elif c.size_bytes > max_bytes():
        status, reasons = "screened_out", [f"{c.size_bytes / 1e9:.1f} GB is above the storage budget of {max_bytes() / 1e9:.0f} GB (MODEL_HUNTER_MAX_GB)"]
    else:
        f = hardware.fit(c.size_bytes, 4096, snap)
        c.fit = f
        if f["verdict"] in ("does_not_fit", "no_runtime") or not f["disk_ok"]:
            status, reasons = "screened_out", [f"does not fit this machine: needs ~{f['ram_needed_bytes'] / 1e9:.1f} GB RAM, "
                                               f"{f['ram_available_bytes'] / 1e9:.1f} GB available ({f['verdict']})"]
        else:
            if f["verdict"] == "tight":
                reasons.append(f"tight fit: ~{f['ram_needed_bytes'] / 1e9:.1f} GB of {f['ram_available_bytes'] / 1e9:.1f} GB")
            c.commercial_use = catalog.commercial_use(c.license)
            if c.commercial_use != "permitted":
                reasons.append(f"licence '{c.license}': commercial use needs a person's review")
            if installed and c.sha256 in installed:
                status, reasons = "installed", ["already installed (same sha256)"]
            else:
                reasons.append("not yet measured on our tasks — the Model Championship decides")
    c.status, c.reasons, c.checked_at = status, reasons, datetime.now(UTC)


def discover(db: Session, task: str = "general", *, limit: int = 15, client: httpx.Client | None = None, actor: str = "agent:model_hunter") -> dict[str, Any]:
    """Search, fetch details only for new or changed repositories, screen everything. Downloads nothing."""
    from ..daemon import hardware, state
    from ..models import LocalModel, ModelCandidate

    if task not in TASKS:
        raise ValueError(f"unknown task {task}; one of {sorted(TASKS)}")
    if state.load(db).get("offline_mode"):
        raise RuntimeError("offline mode is on — the Model Hunter does not reach the internet")
    c = _client(client)
    hits = hub_search(TASKS[task]["search"], limit=limit, client=c)
    snap = hardware.snapshot()
    installed = {m.sha256_actual for m in db.scalars(select(LocalModel).where(LocalModel.status == "installed")) if m.sha256_actual}
    counts = {"searched": len(hits), "new": 0, "changed": 0, "unchanged": 0, "shortlisted": 0, "screened_out": 0}
    for h in hits:
        repo = h["id"]
        known = db.scalars(select(ModelCandidate).where(ModelCandidate.repo == repo)).first()
        if known and known.revision and known.revision == h.get("sha"):
            counts["unchanged"] += 1  # change detection: same revision → no detail requests
            continue
        try:
            d = details(repo, client=c)
        except (httpx.HTTPError, ValueError, KeyError):
            continue
        row = db.scalars(select(ModelCandidate).where(ModelCandidate.repo == repo, ModelCandidate.file == d["file"])).first()
        counts["changed" if known else "new"] += 1
        if row is None:
            row = ModelCandidate(repo=repo, file=d["file"], task=task)
            db.add(row)
        for k in ("revision", "license", "gated", "tags", "base_model", "downloads", "likes", "last_modified", "parameters_b", "size_bytes",
                  "sha256", "quantization"):
            setattr(row, k, d[k])
        if row.status in ("installed", "acquiring", "pending_approval"):
            continue
        screen(row, snap=snap, installed=installed)
        counts[row.status] = counts.get(row.status, 0) + 1
    gov.audit(db, actor, "models.discover", f"task:{task}", **counts)
    db.commit()
    return {"task": task, **counts}


def local_key(c: Any) -> str:
    base = re.sub(r"[^a-z0-9.]+", "-", c.repo.split("/")[-1].lower()).strip("-").replace("-gguf", "")
    return f"{base}-{(c.quantization or 'q').lower()}"[:96]


def request_acquisition(db: Session, cid: int, *, actor: str, agent_id: str | None = None, user_email: str | None = None,
                        incumbent_parameters_b: float | None = None) -> Any:
    """Devil's Advocate review, then a governed approval request. Nothing is downloaded here."""
    from ..governance.policy import ApprovalRequired, PolicyDenied, Request, enforce
    from ..models import ModelCandidate
    from . import advocate

    c = db.get(ModelCandidate, cid)
    if c is None:
        raise LookupError("candidate not found")
    if c.status != "shortlisted":
        raise ValueError(f"only shortlisted candidates can be acquired (this one is {c.status}: {'; '.join(c.reasons or [])})")
    safety = [t for t in c.tags or [] if any(s in t.lower() for s in SAFETY_TAGS)]
    crit = advocate.review(db, {
        "kind": "model_acquisition", "ref": f"candidate:{c.id}", "summary": f"download {c.repo}/{c.file} ({c.size_bytes / 1e9:.1f} GB) for {c.task}",
        "objective": f"a better local model for {c.task}: {TASKS.get(c.task, {}).get('why', '')}",
        "evidence": [f"Hub metadata: {c.downloads} downloads, {c.likes} likes — popularity, not quality"],
        "alternatives": ["keep the installed models"], "assumptions": ["the model runs under llama.cpp on this CPU"],
        "risks": ["disk space", "a weaker model than the incumbents"], "verification": "run it in the Model Championship against the installed models",
        "would_change_if": "it loses the championship", "permissions": ["models.acquire"], "cost_usd": 0,
        "format": "gguf" if c.file.lower().endswith(".gguf") else c.file, "license": c.license, "commercial_use": c.commercial_use,
        "gated": c.gated, "fit_verdict": (c.fit or {}).get("verdict"), "ram_needed_gb": round((c.fit or {}).get("ram_needed_bytes", 0) / 1e9, 1),
        "safety_modified": bool(safety), "safety_tags": safety, "measured": False, "parameters_b": c.parameters_b,
        "incumbent_parameters_b": incumbent_parameters_b, "proposer": f"agent:{agent_id}" if agent_id else actor}, actor="devils_advocate")
    c.critique_id = crit.id
    if crit.verdict == "block":
        c.status = "rejected"
        c.reasons = [*(c.reasons or []), f"Devil's Advocate blocked it (critique #{crit.id})"]
        db.commit()
        return c
    try:
        enforce(db, Request(action="models.acquire", agent_id=agent_id, user_email=user_email,
                            payload={"candidate": c.id, "repo": c.repo, "file": c.file, "sha256": c.sha256}),
                request_approval_title=f"Download model {c.repo}/{c.file} ({c.size_bytes / 1e9:.1f} GB, {c.license}) for the championship")
        c.status = "approved"
    except ApprovalRequired as e:
        c.status, c.approval_id = "pending_approval", e.decision.approval_id
    except PolicyDenied as e:
        c.status = "rejected"
        c.reasons = [*(c.reasons or []), f"policy: {e}"]
    gov.audit(db, actor, "models.acquire.request", f"candidate:{c.id}", repo=c.repo, status=c.status, critique=crit.id)
    db.commit()
    return c


def acquire(db: Session, cid: int, *, actor: str, client: httpx.Client | None = None) -> Any:
    """After approval: register the candidate as a pinned library entry and run the EXISTING verified installer
    (licence + sha256 re-checked against the live Hub, trusted hosts only, checksum verified after download)."""
    from ..daemon import catalog, library
    from ..models import Approval, LocalModel, ModelCandidate

    c = db.get(ModelCandidate, cid)
    if c is None:
        raise LookupError("candidate not found")
    if c.status == "pending_approval":
        ap = db.get(Approval, c.approval_id) if c.approval_id else None
        if not (ap and ap.status == "approved" and ap.revoked_at is None):
            raise PermissionError(f"approval #{c.approval_id} is not approved yet")
        ap.consumed_at = datetime.now(UTC)
    elif c.status != "approved":
        raise ValueError(f"candidate is {c.status}")
    key = local_key(c)
    m = db.scalars(select(LocalModel).where(LocalModel.key == key)).first()
    if m is None:
        m = LocalModel(key=key, display_name=f"{c.repo.split('/')[-1]} ({c.quantization})", family=(c.base_model or c.repo).split("/")[-1].split("-")[0].lower(),
                       kind="embedding" if c.task == "embedding" else "chat", fmt="gguf", quantization=c.quantization,
                       parameters=f"{c.parameters_b}B" if c.parameters_b else "", source="huggingface", source_repo=c.repo, source_file=c.file,
                       license=c.license, license_evidence=f"Model Hunter: Hub model-card metadata, revision {c.revision[:12]}",
                       commercial_use=catalog.commercial_use(c.license), sha256_expected=c.sha256, size_bytes=c.size_bytes,
                       context_length=4096, languages=["multilingual"], capabilities=["text"], status="available",
                       notes=f"acquired by the Model Hunter (candidate #{c.id}, task {c.task}); pinned to sha256 {c.sha256[:12]}")
        db.add(m)
    c.status, c.local_key = "acquiring", key
    db.commit()
    try:
        library.install(db, key, actor, client=client)
        c.status = "installed"
    except Exception as e:  # noqa: BLE001 — recorded with the reason; the candidate stays visible
        c.status = "failed"
        c.reasons = [*(c.reasons or []), f"install failed: {str(e)[:200]}"]
    gov.audit(db, actor, "models.acquire", f"candidate:{c.id}", key=key, status=c.status)
    db.commit()
    return c


def board(db: Session) -> dict[str, Any]:
    from ..models import ModelCandidate

    rows = db.scalars(select(ModelCandidate).order_by(ModelCandidate.checked_at.desc()).limit(300)).all()
    since = datetime.now(UTC) - timedelta(days=7)
    def fresh(r: Any) -> bool:
        d = r.discovered_at if r.discovered_at.tzinfo else r.discovered_at.replace(tzinfo=UTC)
        return d >= since
    by = lambda s: [r for r in rows if r.status == s]  # noqa: E731
    return {"tasks": {k: v["why"] for k, v in TASKS.items()}, "storage_budget_gb": max_bytes() / 1e9,
            "counts": {s: len(by(s)) for s in ("shortlisted", "screened_out", "pending_approval", "approved", "acquiring", "installed", "rejected", "failed")},
            "new_this_week": sum(1 for r in rows if fresh(r)), "candidates": rows}
