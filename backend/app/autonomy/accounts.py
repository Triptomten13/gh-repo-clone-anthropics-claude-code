"""ACCOUNT VAULT — DAEMON ACCOUNT & INTEGRATION MANAGEMENT.

Practical autonomy for agents without spreading secrets between models:
* An account is a ServiceAccount record (why, who owns it, which scopes, which level). Its secret is stored encrypted in
  the EXISTING credential store (provider_credentials, Fernet) under the scope `<service>:<account id>`.
* Agents never receive a secret. They receive a TOOL GRANT whose credential scope names the account; the governed tool
  runs on the server, the gateway hands the secret only to that tool function, redacts it from the result, and every use
  is written to the audit trail (`vault.use`). Prompts, model context, traces, logs and API responses never contain it.
* Levels: 0 research · 1 prepare · 2 authorised provisioning · 3 managed operation · 4 sensitive. Level ≥ 2 needs a
  human approval (four eyes); paid services, broad scopes and duplicates are challenged by the Devil's Advocate first.
* Creating the account itself on the provider's website is done by a PERSON: sign-up flows use e-mail/phone
  verification and CAPTCHAs, which are never bypassed. Agents research and prepare; the owner signs up, creates a
  least-privilege token, and connects it here. One account per identity — never extra accounts to stretch free limits.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..governance import core as gov

JUSTIFICATION_KEYS = ("service", "usefulness", "existing", "capabilities", "terms", "ownership", "permissions", "costs",
                      "alternative_integration", "decision")
JUSTIFICATION_HELP = {
    "service": "1. Which service?", "usefulness": "2. Why is it useful?", "existing": "3. Does an account already exist?",
    "capabilities": "4. Free and paid capabilities?", "terms": "5. Terms of service and account requirements reviewed?",
    "ownership": "6. Personal, organisational or project account?", "permissions": "7. Which permissions are necessary?",
    "costs": "8. Costs and limitations?", "alternative_integration": "9. Can an existing integration do the same?",
    "decision": "10. Is creating/connecting it justified — and why?"}
LEVELS = {0: "research", 1: "prepare", 2: "authorised provisioning", 3: "managed operation", 4: "sensitive operation"}

# Facts about each service, recorded with where they come from. They describe sign-up and token practice; the owner must
# still read the current terms (they change). Health checks use the services' official, documented endpoints.
SERVICES: dict[str, dict[str, Any]] = {
    "huggingface": {
        "name": "Hugging Face", "use": "model search, model cards, licence metadata, downloads (higher rate limits with a token), gated models",
        "signup": "https://huggingface.co/join — e-mail verification; a person signs up",
        "token": "https://huggingface.co/settings/tokens — prefer a fine-grained READ token",
        "recommended_scopes": ["read-repos"], "free": "free account; anonymous public search and downloads also work",
        "terms": "https://huggingface.co/terms-of-service",
        "health": {"url": "https://huggingface.co/api/whoami-v2", "identity": "name"}},
    "github": {
        "name": "GitHub", "use": "repositories, issues, pull requests, CI for the Development Division",
        "signup": "https://github.com/signup — e-mail verification and a CAPTCHA; a person signs up",
        "token": "https://github.com/settings/personal-access-tokens — fine-grained token limited to chosen repositories; a GitHub App for an organisation",
        "recommended_scopes": ["contents:read", "pull_requests:write", "issues:write", "metadata:read"],
        "free": "free for public and private repositories with limits", "terms": "https://docs.github.com/site-policy/github-terms/github-terms-of-service",
        "health": {"url": "https://api.github.com/user", "identity": "login"}},
    "gitlab": {
        "name": "GitLab", "use": "alternative repository hosting and CI", "signup": "https://gitlab.com/users/sign_up — e-mail verification; a person signs up",
        "token": "https://gitlab.com/-/user_settings/personal_access_tokens — read_api for read-only use", "recommended_scopes": ["read_api"],
        "free": "free tier with CI-minute limits", "terms": "https://about.gitlab.com/terms/",
        "health": {"url": "https://gitlab.com/api/v4/user", "identity": "username"}},
}


def research(service: str) -> dict[str, Any]:
    """Level 0: what the service offers, how sign-up works, which token to make. No account is touched."""
    s = SERVICES.get(service)
    if s is None:
        return {"service": service, "known": False, "note": "not in the vault's service list — research it with Research & Monitoring first"}
    return {"service": service, "known": True, **{k: v for k, v in s.items() if k != "health"},
            "how": ["a person signs up (verification and CAPTCHAs are never bypassed)", "create a least-privilege token",
                    "connect it here with the owner attestation", "grant a tool, not the token, to an agent"]}


def scope_of(a: Any) -> str:
    return f"{a.service}:{a.id}"


def _existing(db: Session, service: str, identity: str) -> Any:
    from ..models import ServiceAccount

    return db.scalars(select(ServiceAccount).where(ServiceAccount.service == service, ServiceAccount.identity == identity,
                                                   ServiceAccount.status.in_(("pending_approval", "approved", "connected")))).first()


def propose(db: Session, *, service: str, identity: str, purpose: str, scopes: list[str], justification: dict[str, Any], level: int = 2,
            paid: bool = False, requested_by: str, proposer_model: str = "") -> Any:
    """Levels 0–1 are prepared without approval; level ≥ 2 is filed for a human approval after the Devil's Advocate review."""
    from ..governance.policy import ApprovalRequired, PolicyDenied, Request, enforce
    from ..models import ServiceAccount
    from . import advocate

    if level not in LEVELS:
        raise ValueError("level must be 0–4")
    dup = _existing(db, service, identity)
    decision = {"kind": "account_request", "ref": f"{service}:{identity}", "summary": f"connect {service} account '{identity}' for: {purpose}",
                "objective": purpose, "evidence": [justification.get("usefulness", "")] if justification.get("usefulness") else [],
                "alternatives": [justification.get("alternative_integration", "")] if justification.get("alternative_integration") else [],
                "assumptions": [justification.get("capabilities", "")] if justification.get("capabilities") else [],
                "risks": ["token misuse — limited by the scopes"], "verification": "vault health check (official whoami endpoint)",
                "would_change_if": justification.get("decision", ""), "permissions": scopes, "cost_usd": 0 if not paid else None,
                "scopes": scopes, "paid": paid, "proposer": requested_by, "proposer_model": proposer_model,
                "existing_account": f"#{dup.id} ({dup.status})" if dup else "", "justification": justification}
    crit = advocate.review(db, decision, actor="devils_advocate")
    a = ServiceAccount(service=service, identity=identity, purpose=purpose, level=level, scopes=scopes, justification=justification,
                       requested_by=requested_by, critique_id=crit.id, status="proposed")
    db.add(a)
    db.flush()
    if crit.verdict == "block":
        a.status = "rejected"
    elif level >= 2:
        is_agent = requested_by.startswith("agent:")
        try:
            enforce(db, Request(action="accounts.paid" if paid else "accounts.provision", agent_id=requested_by[6:] if is_agent else None,
                                user_email=None if is_agent else requested_by.removeprefix("user:"),
                                payload={"service": service, "identity": identity, "scopes": sorted(scopes), "account": a.id}),
                    request_approval_title=f"Connect {SERVICES.get(service, {}).get('name', service)} account '{identity}' (level {level}: {LEVELS[level]})")
            a.status = "approved"  # only when a rule made it autonomous; the default floor requires an approval
        except ApprovalRequired as e:
            a.status, a.approval_id = "pending_approval", e.decision.approval_id
        except PolicyDenied:
            a.status = "rejected"
    gov.audit(db, requested_by, "vault.account.propose", f"account:{a.id}", service=service, identity=identity, level=level, scopes=scopes,
              status=a.status, critique=crit.id, verdict=crit.verdict)
    db.commit()
    return a


def _approved(db: Session, a: Any) -> bool:
    from ..models import Approval

    if a.level < 2 or a.status == "approved":
        return True
    ap = db.get(Approval, a.approval_id) if a.approval_id else None
    return bool(ap and ap.status == "approved" and ap.revoked_at is None)


def connect(db: Session, aid: int, secret: str, *, attestation: str, actor: str, expires_at: datetime | None = None, client: httpx.Client | None = None) -> Any:
    """A PERSON connects the token they created. Stored encrypted; then checked once against the official endpoint."""
    from ..daemon import credentials
    from ..models import ServiceAccount

    a = db.get(ServiceAccount, aid)
    if a is None:
        raise LookupError("account not found")
    if a.status in ("revoked", "rejected"):
        raise ValueError(f"account is {a.status}")
    if not _approved(db, a):
        raise PermissionError("this account needs an approved approval first (four eyes)")
    c = credentials.store(db, scope_of(a), secret, label=f"{a.service} · {a.identity}", attestation=attestation, actor=actor, expires_at=expires_at)
    a.credential_id, a.credential_scope, a.expires_at, a.status = c.id, scope_of(a), expires_at, "connected"
    gov.audit(db, actor, "vault.account.connect", f"account:{a.id}", service=a.service, fingerprint=c.fingerprint)
    db.commit()
    health(db, aid, actor=actor, client=client)
    return a


def health(db: Session, aid: int, *, actor: str = "system", client: httpx.Client | None = None) -> dict[str, Any]:
    """Call the service's official identity endpoint with the stored token (server-side only). Records the account name the
    token belongs to and expiry warnings — never the token."""
    from ..daemon import credentials
    from ..models import ServiceAccount

    a = db.get(ServiceAccount, aid)
    if a is None:
        raise LookupError("account not found")
    now = datetime.now(UTC)
    out: dict[str, Any] = {"checked_at": now.isoformat()}
    spec = SERVICES.get(a.service, {}).get("health")
    if a.status != "connected" or not a.credential_scope:
        out.update(ok=False, reason=f"not connected ({a.status})")
    elif spec is None:
        out.update(ok=None, reason="no documented health endpoint for this service")
    else:
        credentials.invalidate()
        token = credentials.secret_for(a.credential_scope)
        if not token:
            out.update(ok=False, reason="the stored credential is missing, disabled or expired")
        else:
            c = client or httpx.Client(timeout=15)
            try:
                r = c.get(spec["url"], headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
                body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                out.update(ok=r.status_code == 200, status=r.status_code, identity=str(body.get(spec["identity"], ""))[:128])
                if r.headers.get("x-oauth-scopes") is not None:
                    out["granted_scopes"] = r.headers.get("x-oauth-scopes")
                if r.status_code in (401, 403):
                    out["reason"] = "the service refused the token (revoked, expired or lacking scope)"
            except (httpx.HTTPError, ValueError) as e:
                out.update(ok=False, reason=f"could not reach {a.service}: {type(e).__name__}")
            finally:
                token = None  # noqa: F841 — not kept beyond the call
    if a.expires_at:
        exp = a.expires_at if a.expires_at.tzinfo else a.expires_at.replace(tzinfo=UTC)
        if exp < now + timedelta(days=7):
            out["expiry_warning"] = f"expires {exp.date().isoformat()} — create a new token and rotate"
    a.health, a.last_health_at = out, now
    gov.audit(db, actor, "vault.account.health", f"account:{a.id}", ok=out.get("ok"), status=out.get("status"))
    db.commit()
    return out


def revoke(db: Session, aid: int, *, actor: str, reason: str = "") -> Any:
    """Disconnect the secret, remove every tool grant that used its scope, keep the record and the audit trail."""
    from ..daemon import credentials
    from ..models import ServiceAccount, ToolGrant

    a = db.get(ServiceAccount, aid)
    if a is None:
        raise LookupError("account not found")
    if a.credential_id:
        try:
            credentials.disconnect(db, a.credential_id, actor)
        except Exception as e:  # noqa: BLE001 — already disconnected is fine; the grants below still go
            gov.audit(db, actor, "vault.account.disconnect_note", f"account:{a.id}", note=str(e)[:200])
    grants = db.scalars(select(ToolGrant).where(ToolGrant.credential_scope == scope_of(a))).all() if a.credential_scope else []
    for g in grants:
        db.delete(g)
    a.status, a.revoked_at, a.revoked_by = "revoked", datetime.now(UTC), actor
    credentials.invalidate()
    gov.audit(db, actor, "vault.account.revoke", f"account:{a.id}", reason=reason, grants_removed=len(grants))
    db.commit()
    return a


def public(a: Any) -> dict[str, Any]:
    """What the API and the interface may show: never the secret, not even its fingerprint beyond the credential record."""
    keys = ("id", "service", "identity", "purpose", "level", "status", "scopes", "justification", "credential_scope", "requested_by",
            "approval_id", "critique_id", "expires_at", "last_health_at", "health", "created_at", "revoked_at", "revoked_by")
    out = {k: getattr(a, k) for k in keys}
    out["level_name"] = LEVELS.get(a.level, "")
    return out
