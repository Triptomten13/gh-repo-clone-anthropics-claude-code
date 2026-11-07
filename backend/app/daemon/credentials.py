"""Owner-authorised provider credentials, encrypted at rest (Fernet, AES-128-CBC + HMAC-SHA256).

Key: CREDENTIALS_KEY (urlsafe base64, 32 bytes) if set, else derived from SECRET_KEY with HKDF.
Changing SECRET_KEY without CREDENTIALS_KEY makes stored secrets unreadable — re-enter them.
Secrets are never returned by the API, never logged and never given to agents; only provider adapters read them.
Only human admins can add, rotate, validate or disconnect credentials, and adding one requires the admin to attest
that the organisation owns the account and accepted the provider's terms.
"""
from __future__ import annotations

import base64
import hashlib
import os
import threading
import time
from datetime import UTC, datetime
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..governance import core as gov
from ..models import ProviderCredential

ATTESTATION = ("I confirm that Demonkoncernen AB is authorised to use this account and credential, that the account owner "
               "created the account and accepted the provider's terms, and that it is not a shared consumer subscription.")
_cache: dict[str, tuple[float, str | None]] = {}
_lock = threading.Lock()


def _fernet() -> Fernet:
    k = os.getenv("CREDENTIALS_KEY")
    if k:
        return Fernet(k.encode())
    from ..config import get_settings

    raw = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"daemon-core", info=b"provider-credentials").derive(get_settings().secret_key.encode())
    return Fernet(base64.urlsafe_b64encode(raw))


def fingerprint(secret: str) -> str:
    return f"…{secret[-4:]}·{hashlib.sha256(secret.encode()).hexdigest()[:8]}"


def public(c: ProviderCredential) -> dict[str, Any]:
    return {"id": c.id, "provider": c.provider, "label": c.label, "fingerprint": c.fingerprint, "status": c.status,
            "authorized_by": c.authorized_by, "expires_at": c.expires_at, "last_validated_at": c.last_validated_at,
            "last_validation": c.last_validation, "created_at": c.created_at, "rotated_at": c.rotated_at,
            "expiring_soon": bool(c.expires_at and (c.expires_at.replace(tzinfo=c.expires_at.tzinfo or UTC) - datetime.now(UTC)).days < 14)}


def invalidate() -> None:
    with _lock:
        _cache.clear()


def store(db: Session, provider: str, secret: str, *, label: str, attestation: str, actor: str, expires_at: datetime | None = None) -> ProviderCredential:
    if attestation.strip() != ATTESTATION:
        raise PermissionError("the owner attestation must be accepted verbatim")
    if len(secret.strip()) < 8:
        raise ValueError("secret looks empty")
    for old in db.scalars(select(ProviderCredential).where(ProviderCredential.provider == provider, ProviderCredential.status == "active")).all():
        old.status = "disabled"  # one active credential per provider — never a pool to rotate around limits
    c = ProviderCredential(provider=provider, label=label, secret_enc=_fernet().encrypt(secret.strip().encode()).decode(),
                           fingerprint=fingerprint(secret.strip()), status="active", attestation=attestation, authorized_by=actor,
                           expires_at=expires_at)
    db.add(c)
    db.flush()
    gov.audit(db, actor, "credential.add", f"{provider}:{c.id}", fingerprint=c.fingerprint, label=label)
    db.commit()
    invalidate()
    return c


def rotate(db: Session, cid: int, secret: str, actor: str) -> ProviderCredential:
    c = db.get(ProviderCredential, cid)
    if not c or c.status == "revoked":
        raise LookupError("no such credential")
    old_fp = c.fingerprint
    c.secret_enc = _fernet().encrypt(secret.strip().encode()).decode()
    c.fingerprint, c.rotated_at, c.last_validation, c.last_validated_at = fingerprint(secret.strip()), datetime.now(UTC), {}, None
    gov.audit(db, actor, "credential.rotate", f"{c.provider}:{c.id}", old=old_fp, new=c.fingerprint)
    db.commit()
    invalidate()
    return c


def disconnect(db: Session, cid: int, actor: str) -> ProviderCredential:
    c = db.get(ProviderCredential, cid)
    if not c:
        raise LookupError("no such credential")
    c.status, c.secret_enc = "revoked", ""  # the secret is destroyed, the audit trail stays
    gov.audit(db, actor, "credential.disconnect", f"{c.provider}:{c.id}", fingerprint=c.fingerprint)
    db.commit()
    invalidate()
    return c


def secret_for(provider: str) -> str | None:
    now = time.monotonic()
    with _lock:
        hit = _cache.get(provider)
        if hit and now - hit[0] < 30:
            return hit[1]
    from .. import db as dbmod

    s = dbmod.SessionLocal()
    val: str | None = None
    try:
        c = s.scalars(select(ProviderCredential).where(ProviderCredential.provider == provider, ProviderCredential.status == "active")
                      .order_by(ProviderCredential.id.desc())).first()
        if c and c.secret_enc and not (c.expires_at and c.expires_at.replace(tzinfo=c.expires_at.tzinfo or UTC) < datetime.now(UTC)):
            try:
                val = _fernet().decrypt(c.secret_enc.encode()).decode()
            except InvalidToken:
                val = None  # key changed — treated as missing, never as valid
    except Exception:
        val = None
    finally:
        s.close()
    with _lock:
        _cache[provider] = (now, val)
    return val


def validate(db: Session, cid: int, actor: str) -> dict[str, Any]:
    """Explicit connection test requested by an admin. Anthropic: list models (a metadata call, no tokens generated)."""
    from . import state

    c = db.get(ProviderCredential, cid)
    if not c or c.status != "active":
        raise LookupError("no active credential with that id")
    if state.load(db)["offline_mode"]:
        raise PermissionError("offline mode is on — external connection tests are disabled")
    secret = _fernet().decrypt(c.secret_enc.encode()).decode()
    result: dict[str, Any]
    if c.provider == "anthropic":
        import anthropic

        try:
            page = anthropic.Anthropic(api_key=secret, max_retries=0, timeout=20).models.list(limit=5)
            result = {"ok": True, "models_visible": [m.id for m in page.data]}
        except anthropic.AuthenticationError:
            result = {"ok": False, "error": "authentication failed"}
        except Exception as e:
            result = {"ok": False, "error": f"{type(e).__name__}"}
    elif c.provider.startswith("worker:"):
        from .workers import provider_for

        h = provider_for(db, c.provider.split(":", 1)[1]).health()
        result = {"ok": bool(h.get("reachable")), **{k: v for k, v in h.items() if k != "error"}}
    else:
        result = {"ok": None, "note": "no adapter for this provider — stored, not tested"}
    c.last_validated_at, c.last_validation = datetime.now(UTC), result
    gov.audit(db, actor, "credential.validate", f"{c.provider}:{c.id}", ok=result.get("ok"))
    db.commit()
    return result
