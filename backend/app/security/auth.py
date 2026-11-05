"""Authentication: PBKDF2 password hashing + HMAC-signed bearer tokens (stdlib only).

Swap for an OIDC provider in production if needed; the dependency `current_user`
is the single integration point.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import User

_ITER = 240_000
bearer = HTTPBearer(auto_error=False)


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, _ITER)
    return f"pbkdf2_sha256${_ITER}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, it, salt_b64, dk_b64 = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), base64.b64decode(salt_b64), int(it))
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except Exception:
        return False


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue_token(user: User) -> str:
    s = get_settings()
    body = {"sub": user.id, "email": user.email, "role": user.role, "tv": user.token_version or 0,
            "exp": int(time.time()) + s.token_ttl_hours * 3600}
    payload = _b64(json.dumps(body, separators=(",", ":")).encode())
    sig = _b64(hmac.new(s.secret_key.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def decode_token(token: str) -> dict[str, Any]:
    s = get_settings()
    try:
        payload, sig = token.split(".")
    except ValueError as e:
        raise ValueError("malformed token") from e
    expected = _b64(hmac.new(s.secret_key.encode(), payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        raise ValueError("bad signature")
    body = json.loads(_unb64(payload))
    if body.get("exp", 0) < time.time():
        raise ValueError("expired")
    return body


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        body = decode_token(creds.credentials)
    except ValueError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e
    user = db.get(User, body["sub"])
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown user")
    if user.disabled:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "account disabled")
    if body.get("tv", 0) != (user.token_version or 0):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token revoked — sign in again")
    return user


def require_role(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires role: {', '.join(roles)}")
        return user

    return dep
