"""DAEMON IDENTITY & ACCESS — roles are named bundles of permissions; endpoints check PERMISSIONS.

Existing roles keep exactly their previous reach (admin · operator · viewer; legacy `require_role` checks are
unchanged). The new roles separate duties: whoever BUILDS agents or workflows cannot APPROVE their consequential
actions, approvers cannot change policy, auditors read and export evidence but change nothing, and only a security
admin (or the super admin) can change policies, tool grants or retention. Roles never inherit implicitly — every
permission a role has is listed here, so no accidental escalation through a hierarchy.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status

from ..models import User
from .auth import current_user

PERMISSIONS = {
    "audit.read": "read the audit trail",
    "audit.export": "export audit records",
    "audit.verify": "run integrity verification",
    "audit.retention": "prune audit records under the retention policy",
    "policy.read": "read policies",
    "policy.write": "create / change / roll back policies",
    "approval.read": "see approvals",
    "approval.decide": "approve or reject consequential actions",
    "tools.read": "see tools, grants and invocations",
    "tools.grant": "grant / revoke tool permissions",
    "tools.invoke": "invoke tools as a user",
    "runs.read": "read execution traces and replays",
    "work.run": "start agent work and workflows",
    "workflow.design": "create and version workflows",
    "agent.develop": "configure agents",
    "eval.run": "run evaluations",
    "gates.write": "change release-gate thresholds",
    "knowledge.read": "search the Knowledge Vault (within document permissions)",
    "knowledge.write": "add documents",
    "knowledge.admin": "change document classification and access, delete documents",
    "models.manage": "model registry, routing, credentials",
    "system.configure": "offline / air-gap mode, deployment profile, budgets",
    "users.manage": "users and roles",
}

ROLES: dict[str, set[str]] = {
    # super admin: everything (the first account; keep few)
    "admin": set(PERMISSIONS),
    "security_admin": {"audit.read", "audit.export", "audit.verify", "audit.retention", "policy.read", "policy.write", "approval.read",
                       "tools.read", "tools.grant", "runs.read", "knowledge.admin", "knowledge.read"},
    "system_admin": {"audit.read", "policy.read", "tools.read", "runs.read", "models.manage", "system.configure", "knowledge.read"},
    "workflow_designer": {"policy.read", "workflow.design", "runs.read", "eval.run", "tools.read", "knowledge.read"},
    "agent_developer": {"policy.read", "agent.develop", "runs.read", "eval.run", "tools.read", "knowledge.read"},
    "operator": {"audit.read", "policy.read", "approval.read", "tools.read", "tools.invoke", "runs.read", "work.run",
                 "eval.run", "knowledge.read", "knowledge.write"},
    "approver": {"approval.read", "approval.decide", "policy.read", "runs.read", "knowledge.read"},
    "auditor": {"audit.read", "audit.export", "audit.verify", "policy.read", "approval.read", "tools.read", "runs.read"},
    "user": {"work.run", "tools.invoke", "knowledge.read", "knowledge.write"},
    "viewer": {"audit.read", "policy.read", "approval.read", "tools.read", "runs.read", "knowledge.read"},
    # public demo visitor (DEMO_MODE servers only, created by POST /api/demo/session — never assignable): read sample
    # data and run the approved sample workflows; no tools, approvals, uploads, settings or administration
    "demo": {"audit.read", "policy.read", "approval.read", "tools.read", "runs.read", "knowledge.read", "work.run", "eval.run"},
}
ASSIGNABLE_ROLES = [r for r in ROLES if r != "demo"]
ROLE_PATTERN = "^(" + "|".join(ASSIGNABLE_ROLES) + ")$"
# roles only a super admin may hand out (prevents a security admin from minting super admins)
PRIVILEGED_ROLES = {"admin", "security_admin"}


def permissions_of(role: str) -> set[str]:
    return ROLES.get(role, set())


def has(user: User, perm: str) -> bool:
    return perm in permissions_of(user.role) and not user.disabled


def require_permission(*perms: str):
    """FastAPI dependency: the user's role must grant ALL listed permissions."""
    def dep(user: User = Depends(current_user)) -> User:
        missing = [p for p in perms if not has(user, p)]
        if missing:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires permission: {', '.join(missing)}")
        return user
    return dep
