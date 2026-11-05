"""Local model library: install (download or offline import) with licence + checksum verification,
activate per slot with rollback history, and removal. Weights never enter git or the database."""
from __future__ import annotations

import hashlib
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..governance import core as gov
from ..models import LocalModel
from . import catalog, hardware, state

SLOTS = {"chat": "chat", "eco": "chat", "deep": "chat", "embedding": "embedding"}
THINKING_CTX = 8192  # thinking models need room for their reasoning


class LibraryError(RuntimeError):
    pass


def ensure_rows(db: Session) -> None:
    have = {m.key for m in db.scalars(select(LocalModel)).all()}
    for e in catalog.CATALOG:
        if e.key in have:
            continue
        db.add(LocalModel(key=e.key, display_name=e.display_name, family=e.family, kind=e.kind, fmt="gguf", quantization=e.quantization,
                          parameters=e.parameters, source="huggingface", source_repo=e.repo, source_file=e.file, license=e.license,
                          license_evidence=f"catalog: Hugging Face model-card metadata checked {catalog.CATALOG_VERIFIED_AT}",
                          commercial_use=catalog.commercial_use(e.license), sha256_expected=e.sha256, size_bytes=e.size_bytes,
                          context_length=e.context_length, languages=list(e.languages), capabilities=list(e.capabilities),
                          notes=e.notes, status="available"))
    db.flush()


def get(db: Session, key: str) -> LocalModel:
    m = db.scalars(select(LocalModel).where(LocalModel.key == key)).first()
    if not m:
        raise LibraryError(f"unknown model {key!r}")
    return m


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_thinking(m: Any) -> bool:
    return "thinking" in (getattr(m, "capabilities", None) or [])


def ctx_for(m: Any, st: dict[str, Any]) -> int:
    return max(st["local"]["n_ctx"], THINKING_CTX) if is_thinking(m) else st["local"]["n_ctx"]


def listing(db: Session) -> list[dict[str, Any]]:
    ensure_rows(db)
    snap = hardware.snapshot()
    st = state.load(db)
    out = []
    for m in db.scalars(select(LocalModel).order_by(LocalModel.kind, LocalModel.size_bytes)).all():
        f = hardware.fit(m.size_bytes, ctx_for(m, st), snap)
        slots = [s for s, k in st["active"].items() if k == m.key]
        out.append({c.key: getattr(m, c.key) for c in m.__table__.columns} | {
            "fit": f, "active_slots": slots,
            # never advertise a model as usable when it cannot run here
            "runnable": m.status == "installed" and f["verdict"] in ("fits", "tight"),
        })
    return out


def verify_upstream(entry: catalog.CatalogEntry, client: httpx.Client | None = None) -> dict[str, Any]:
    """Re-check licence and checksum against the live Hub before downloading."""
    c = client or httpx.Client(timeout=30, follow_redirects=True)
    meta = c.get(f"https://huggingface.co/api/models/{entry.repo}").json()
    lic = ((meta.get("cardData") or {}).get("license") or "").lower()
    tree = c.get(f"https://huggingface.co/api/models/{entry.repo}/tree/main").json()
    node = next((n for n in tree if n.get("path") == entry.file), None)
    if node is None:
        raise LibraryError(f"{entry.file} no longer exists in {entry.repo}")
    oid, size = node.get("lfs", {}).get("oid"), node.get("lfs", {}).get("size")
    if lic != entry.license:
        raise LibraryError(f"licence changed upstream: catalog {entry.license!r}, hub now {lic!r} — human review required")
    if oid != entry.sha256 or size != entry.size_bytes:
        raise LibraryError("upstream file changed (checksum/size differ from the verified catalog) — refusing")
    return {"license": lic, "sha256": oid, "size": size, "gated": meta.get("gated"), "sha": meta.get("sha", "")}


def install(db: Session, key: str, actor: str, *, client: httpx.Client | None = None) -> LocalModel:
    """Download from the trusted source, verify sha256, record licence. Blocking; call from a background task."""
    st = state.load(db)
    if st["offline_mode"]:
        raise LibraryError("offline mode is on — downloads are disabled; use import from a local file instead")
    entry = catalog.BY_KEY.get(key)
    if entry is None:
        raise LibraryError("only catalogued models can be downloaded; register other files with import-file")
    ensure_rows(db)
    m = get(db, key)
    f = hardware.fit(entry.size_bytes, ctx_for(entry, st))
    if f["verdict"] == "does_not_fit" or not f["disk_ok"]:
        raise LibraryError(f"model does not fit this machine ({f})")
    m.status, m.error, m.progress_bytes = "downloading", "", 0
    db.commit()
    c = client or httpx.Client(timeout=httpx.Timeout(60, read=120), follow_redirects=True)
    dest = hardware.models_dir() / entry.file
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        up = verify_upstream(entry, c)
        h = hashlib.sha256()
        with c.stream("GET", entry.url) as r:
            r.raise_for_status()
            host = r.url.host
            if not (host.endswith("huggingface.co") or host.endswith("hf.co")):
                # the Hub redirects large files to its own CDN (cas-bridge.xethub.hf.co / cdn-lfs.hf.co)
                raise LibraryError(f"download redirected to untrusted host {host}")
            with tmp.open("wb") as out:
                for chunk in r.iter_bytes(1 << 20):
                    out.write(chunk)
                    h.update(chunk)
                    m.progress_bytes += len(chunk)
                    if m.progress_bytes % (64 << 20) < (1 << 20):
                        db.commit()
        digest = h.hexdigest()
        if digest != entry.sha256:
            tmp.unlink(missing_ok=True)
            raise LibraryError(f"checksum mismatch: expected {entry.sha256[:12]}…, got {digest[:12]}…")
        tmp.replace(dest)
        m.sha256_actual, m.file_path, m.status = digest, str(dest), "installed"
        m.source_revision = up.get("sha", "")[:64]
        m.license, m.license_verified_at = up["license"], datetime.now(UTC)
        m.license_evidence = f"Hugging Face model-card metadata (cardData.license) for {entry.repo}@{m.source_revision[:12]}"
        m.commercial_use = catalog.commercial_use(up["license"])
        m.installed_by, m.installed_at = actor, datetime.now(UTC)
        gov.audit(db, actor, "daemon.model.install", m.key, sha256=digest, license=m.license, source=entry.url)
        db.commit()
        from . import cache as _cache

        _cache.invalidate("model-slots", "ai-status")
        return m
    except Exception as e:
        tmp.unlink(missing_ok=True)
        m.status, m.error = "failed", f"{type(e).__name__}: {e}"[:500]
        gov.audit(db, actor, "daemon.model.install_failed", m.key, error=m.error)
        db.commit()
        raise


def import_file(db: Session, key: str, path: str, actor: str) -> LocalModel:
    """Offline / air-gapped install: copy a local file in, accepted only if its sha256 matches the verified catalog."""
    entry = catalog.BY_KEY.get(key)
    if entry is None:
        raise LibraryError("only catalogued models can be imported (their licence and checksum were verified)")
    src = Path(path)
    if not src.is_file():
        raise LibraryError(f"no such file: {path}")
    digest = _sha256(src)
    if digest != entry.sha256:
        raise LibraryError(f"checksum mismatch: expected {entry.sha256[:12]}…, got {digest[:12]}…")
    ensure_rows(db)
    m = get(db, key)
    dest = hardware.models_dir() / entry.file
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)
    m.sha256_actual, m.file_path, m.status, m.error = digest, str(dest), "installed", ""
    m.license_evidence = f"catalog licence (verified {catalog.CATALOG_VERIFIED_AT}); file matched catalog sha256 on import"
    m.installed_by, m.installed_at = actor, datetime.now(UTC)
    gov.audit(db, actor, "daemon.model.import", m.key, sha256=digest)
    db.commit()
    from . import cache as _cache

    _cache.invalidate("model-slots", "ai-status")
    return m


def activate(db: Session, slot: str, key: str | None, actor: str) -> dict[str, Any]:
    if slot not in SLOTS:
        raise LibraryError(f"unknown slot {slot!r} (chat | eco | deep | embedding)")
    st = state.load(db)
    if key is not None:
        m = get(db, key)
        if m.status != "installed" or not m.file_path or not os.path.exists(m.file_path):
            raise LibraryError(f"{key} is not installed")
        if m.kind != SLOTS[slot]:
            raise LibraryError(f"{key} is a {m.kind} model; slot {slot} needs {SLOTS[slot]}")
        f = hardware.fit(m.size_bytes, ctx_for(m, st))
        if f["verdict"] not in ("fits", "tight"):
            raise LibraryError(f"{key} cannot run on this hardware ({f['verdict']})")
    prev = st["active"].get(slot)
    st["active"][slot] = key
    st["history"] = (st["history"] + [{"slot": slot, "previous": prev, "new": key, "at": datetime.now(UTC).isoformat(), "by": actor}])[-50:]
    state.save(db, st)
    gov.audit(db, actor, "daemon.model.activate", f"{slot}:{key}", previous=prev)
    db.commit()
    from . import cache as _cache

    _cache.invalidate("model-slots", "ai-status")
    from . import runtime

    runtime.get_local().unload_except(set(v for v in st["active"].values() if v))
    return {"slot": slot, "active": key, "previous": prev,
            "note": "re-embed the Archive (POST /api/archive/reembed) so stored vectors match the new embedding model" if slot == "embedding" else ""}


def rollback(db: Session, slot: str, actor: str) -> dict[str, Any]:
    st = state.load(db)
    last = next((h for h in reversed(st["history"]) if h["slot"] == slot and h["new"] == st["active"].get(slot)), None)
    if last is None:
        raise LibraryError(f"nothing to roll back for slot {slot}")
    return activate(db, slot, last["previous"], actor)


def remove(db: Session, key: str, actor: str) -> LocalModel:
    m = get(db, key)
    st = state.load(db)
    if key in st["active"].values():
        raise LibraryError(f"{key} is active — activate another model or roll back first")
    if m.file_path and os.path.exists(m.file_path):
        os.remove(m.file_path)
    m.status, m.file_path, m.sha256_actual, m.progress_bytes = "removed", "", "", 0
    gov.audit(db, actor, "daemon.model.remove", key)
    db.commit()
    from . import cache as _cache

    _cache.invalidate("model-slots", "ai-status")
    return m


def resolve(db: Session | None, slot: str) -> LocalModel | None:
    """The installed model behind a slot. Cached 5 s (L1; invalidated on install/activate/remove) — it is consulted on
    every routing decision and status call. Returns a detached, read-only snapshot."""
    from . import cache

    return cache.get("model-slots", 5).get_or_set(slot, lambda: _resolve(slot))


def _resolve(slot: str, db: Session | None = None) -> LocalModel | None:
    from .. import db as dbmod

    st = state.load(db)
    order = {"chat": ["chat", "eco"], "eco": ["eco", "chat"], "deep": ["deep"], "embedding": ["embedding"]}[slot]
    s = db or dbmod.SessionLocal()
    try:
        for sl in order:
            key = st["active"].get(sl)
            if not key:
                continue
            m = s.scalars(select(LocalModel).where(LocalModel.key == key)).first()
            if m and m.status == "installed" and m.file_path and os.path.exists(m.file_path):
                if db is None:
                    s.expunge(m)
                return m
        return None
    finally:
        if db is None:
            s.close()
