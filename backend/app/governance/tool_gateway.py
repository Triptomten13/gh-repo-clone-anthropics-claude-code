"""DAEMON TOOL SECURITY GATEWAY — the only way an agent or a user runs a tool.

Order of checks (every request, allowed or not, is recorded in tool_invocations and the audit chain):
  1 authenticate the agent (must exist and be active)          6 validate inputs against the tool's schema
  2 identify the requesting user (permission tools.invoke)     7 rate limits and budgets (row-locked: concurrency-safe)
  3 workflow scope                                             8 policy decision + approval (single use, under lock)
  4 allow-lists: deny by default — a GRANT must cover the      9 execute (secrets only through the grant's scope)
    tool + operation for the agent (or its workflow) AND,     10 validate / classify / redact the output
    when an agent works for a user, for that user's role      11 record the invocation
  5 the operation must exist on the tool
An agent therefore never gets more than both its own grants and the user it works for allow.
"""
from __future__ import annotations

import json
import os
import smtplib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Agent, BudgetRule, ToolGrant, ToolInvocation, User
from . import core as gov
from .policy import ApprovalRequired, Category, PolicyDenied, Request, enforce

OPERATIONS = ("READ", "CREATE", "UPDATE", "DELETE", "EXECUTE", "ADMINISTER")
SECRET_KEYS = ("password", "secret", "token", "api_key", "apikey", "key", "authorization", "credential")
MAX_OUTPUT_CHARS = 50_000


class GatewayDenied(Exception):
    def __init__(self, reason: str, status: str = "denied", decision: dict | None = None, approval_id: int | None = None):
        super().__init__(reason)
        self.status, self.decision, self.approval_id = status, decision or {}, approval_id


class NotConfigured(Exception):
    pass


@dataclass
class ToolContext:
    db: Session
    user: User | None
    agent_id: str | None
    grant: ToolGrant | None
    classification: str = "INTERNAL"
    _secrets: list[str] = field(default_factory=list)

    def secret(self, credential: str) -> str:
        """A secret reaches a tool only through the grant's credential scope — never shared admin credentials."""
        from ..daemon.credentials import secret_for

        scope = (self.grant.credential_scope if self.grant else "") or ""
        if not scope or not (scope == credential or scope.startswith(f"{credential}:")):
            raise NotConfigured(f"no credential scope for '{credential}' in this grant")
        s = secret_for(scope)
        if not s:
            raise NotConfigured(f"credential '{scope}' is not stored")
        self._secrets.append(s)
        return s


@dataclass
class GovernedTool:
    name: str
    description: str
    operation: str
    input_schema: dict[str, Any]
    fn: Callable[..., Any]
    external: bool = False            # leaves the deployment boundary
    output_class: str = "internal"    # internal | untrusted (wrapped before any model sees it)
    credential: str = ""              # which kind of credential the tool needs, if any

    def public(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "operation": self.operation, "input_schema": self.input_schema,
                "external": self.external, "output_class": self.output_class, "credential": self.credential or None}


# ------------------------------------------------------------------ tools
def _archive_search(ctx: ToolContext, query: str, k: int = 5) -> Any:
    from ..knowledge.search import search

    return [{k_: h[k_] for k_ in ("document_id", "title", "snippet", "citation", "evidence_class", "score")}
            for h in search(ctx.db, query, k=k, user=ctx.user)]


def _memory_recall(ctx: ToolContext, query: str) -> Any:
    from ..daemon.tools import _memory_recall as recall

    if ctx.user is None:
        raise GatewayDenied("memory.recall needs a user context")
    return recall(ctx.db, ctx.user, query)


def _calc(ctx: ToolContext, expression: str) -> Any:
    from ..daemon.tools import _calc as calc

    return calc(expression)


def _now(ctx: ToolContext) -> Any:
    return datetime.now(UTC).isoformat()


def _annotate(ctx: ToolContext, document_id: int, text: str) -> Any:
    from ..models import Annotation, Document

    if ctx.db.get(Document, document_id) is None:
        raise ValueError("no such document")
    a = Annotation(document_id=document_id, author=ctx.user.email if ctx.user else f"agent:{ctx.agent_id}", kind="note", text=text[:4000])
    ctx.db.add(a)
    ctx.db.flush()
    return {"annotation_id": a.id}


def _archive_delete(ctx: ToolContext, document_id: int) -> Any:
    from ..knowledge.vault import delete_document

    return delete_document(ctx.db, document_id, actor=ctx.user.email if ctx.user else f"agent:{ctx.agent_id}")


def _web_fetch(ctx: ToolContext, url: str) -> Any:
    from ..internet.http import FetchError, OfflineError, fetch_page
    from ..security.untrusted import wrap

    try:
        page = fetch_page(ctx.db, url)
    except (FetchError, OfflineError) as e:
        raise GatewayDenied(str(e), status="error") from e
    return {"url": url, "content": wrap(page["text"][:20_000], source_id="web", title=url)}


def _email_send(ctx: ToolContext, to: str, subject: str, body: str) -> Any:
    host = os.getenv("SMTP_HOST", "")
    if not host:
        raise NotConfigured("no SMTP server configured (SMTP_HOST) — nothing was sent")
    password = ctx.secret("smtp")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = os.getenv("SMTP_FROM", ""), to, subject
    msg.set_content(body)
    with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=20) as s:
        s.starttls()
        s.login(os.getenv("SMTP_USER", ""), password)
        s.send_message(msg)
    return {"sent_to": to}


TOOLS: dict[str, GovernedTool] = {t.name: t for t in [
    GovernedTool("archive.search", "Search the Knowledge Vault (only documents the user may read). Results are untrusted data.", "READ",
                 {"properties": {"query": {"type": "string"}, "k": {"type": "integer"}}, "required": ["query"]}, _archive_search,
                 output_class="untrusted"),
    GovernedTool("memory.recall", "The requesting user's own memory items.", "READ",
                 {"properties": {"query": {"type": "string"}}, "required": ["query"]}, _memory_recall),
    GovernedTool("calc", "Safe arithmetic.", "READ", {"properties": {"expression": {"type": "string"}}, "required": ["expression"]}, _calc),
    GovernedTool("time.now", "Current UTC time.", "READ", {"properties": {}}, _now),
    GovernedTool("archive.annotate", "Add a note to a document (kept apart from the source text).", "CREATE",
                 {"properties": {"document_id": {"type": "integer"}, "text": {"type": "string"}}, "required": ["document_id", "text"]}, _annotate),
    GovernedTool("archive.delete", "Delete a document, its chunks, embeddings and cached answers (verified).", "DELETE",
                 {"properties": {"document_id": {"type": "integer"}}, "required": ["document_id"]}, _archive_delete),
    GovernedTool("web.fetch", "Fetch a public web page (robots.txt, SSRF guard, offline mode respected). Untrusted content.", "READ",
                 {"properties": {"url": {"type": "string"}}, "required": ["url"]}, _web_fetch, external=True, output_class="untrusted"),
    GovernedTool("code.execute", "Run model-generated code.", "EXECUTE", {"properties": {"code": {"type": "string"}}, "required": ["code"]},
                 lambda ctx, code: (_ for _ in ()).throw(GatewayDenied("blocked: no isolated sandbox is provisioned; model-generated code "
                                                                        "is never executed on the host", status="blocked")), external=False),
    GovernedTool("email.send", "Send an e-mail through the configured SMTP server.", "EXECUTE",
                 {"properties": {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}},
                  "required": ["to", "subject", "body"]}, _email_send, external=True, credential="smtp"),
]}

# visible, revocable defaults that reproduce the previous behaviour for HUMANS (agents get nothing by default)
DEFAULT_ROLE_GRANTS = {
    "archive.search": ["admin", "security_admin", "system_admin", "workflow_designer", "agent_developer", "operator", "approver", "user", "viewer"],
    "memory.recall": ["admin", "operator", "user", "viewer", "approver", "workflow_designer", "agent_developer", "system_admin", "security_admin"],
    "calc": ["admin", "operator", "user", "viewer"], "time.now": ["admin", "operator", "user", "viewer"],
    "archive.annotate": ["admin", "operator", "user"], "archive.delete": ["admin"], "web.fetch": ["admin", "operator"],
    "email.send": ["admin"],
}


def ensure_default_grants(db: Session) -> int:
    n = 0
    have = {(g.subject_id, g.tool) for g in db.scalars(select(ToolGrant).where(ToolGrant.subject_kind == "role"))}
    for tool, roles in DEFAULT_ROLE_GRANTS.items():
        for r in roles:
            if (r, tool) not in have:
                db.add(ToolGrant(subject_kind="role", subject_id=r, tool=tool, operations=[TOOLS[tool].operation], created_by="system-defaults",
                                 reason="default human access (revocable)"))
                n += 1
    if n:
        db.flush()
    return n


# ------------------------------------------------------------------ the gateway
def _redact_args(args: dict[str, Any]) -> dict[str, Any]:
    return {k: ("[REDACTED]" if any(s in k.lower() for s in SECRET_KEYS) else (v if len(str(v)) < 500 else str(v)[:500] + "…"))
            for k, v in args.items()}


def _grant(db: Session, kind: str, sid: str | None, tool: str, op: str, env: str, lock: bool = False) -> ToolGrant | None:
    if not sid:
        return None
    q = select(ToolGrant).where(ToolGrant.subject_kind == kind, ToolGrant.subject_id == sid, ToolGrant.tool == tool, ToolGrant.enabled.is_(True))
    if lock:
        q = q.with_for_update()
    now = datetime.now(UTC)
    for g in db.execute(q).scalars():
        exp = g.expires_at.replace(tzinfo=UTC) if g.expires_at and g.expires_at.tzinfo is None else g.expires_at
        if op in (g.operations or []) and (not g.environments or env in g.environments) and (exp is None or exp > now):
            return g
    return None


def _validate(t: GovernedTool, args: dict[str, Any]) -> None:
    props = t.input_schema.get("properties", {})
    unknown = set(args) - set(props)
    if unknown:
        raise GatewayDenied(f"unknown arguments: {sorted(unknown)}", status="invalid")
    missing = [r for r in t.input_schema.get("required", []) if r not in args]
    if missing:
        raise GatewayDenied(f"missing arguments: {missing}", status="invalid")
    types = {"string": str, "integer": int, "number": (int, float), "boolean": bool}
    for k, v in args.items():
        want = types.get(props[k].get("type", ""), object)
        if not isinstance(v, want) or (want is int and isinstance(v, bool)):
            raise GatewayDenied(f"argument {k!r} must be {props[k].get('type')}", status="invalid")


def _take_budgets(db: Session, grant: ToolGrant | None, agent_id: str | None, user: User | None, workflow: str | None) -> list[str]:
    """Take one unit from every applicable limit atomically; on any refusal give back what was taken and stop.
    A call counts once it passes policy (executed, whether it then succeeds or fails)."""
    from . import usage

    limits: list[tuple[str, float, str]] = []
    if grant is not None and grant.max_calls_per_day is not None:
        limits.append((f"grant:{grant.id}", grant.max_calls_per_day, f"grant #{grant.id}"))
    scopes = {"agent": agent_id, "user": user.email if user else None, "workflow": workflow, "global": "*"}
    for r in db.scalars(select(BudgetRule).where(BudgetRule.metric == "tool_calls", BudgetRule.enabled.is_(True), BudgetRule.period == "day")):
        sid = scopes.get(r.scope_kind)
        if sid is not None and r.scope_id in ("*", sid):
            limits.append((f"budget:{r.id}:{sid}", r.limit, f"budget #{r.id} ({r.scope_kind} {sid})"))
    taken: list[str] = []
    for key, limit, label in limits:
        if not usage.take(db, key, limit):
            for k in taken:
                usage.give_back(db, k)
            raise GatewayDenied(f"{label}: {int(limit)} tool calls per day reached — stopped, not bypassed", status="budget_exhausted")
        taken.append(key)
    return taken


def _redact_output(out: Any, secrets: list[str]) -> Any:
    s = json.dumps(out, default=str, ensure_ascii=False)
    for sec in secrets:
        if sec and len(sec) >= 4:
            s = s.replace(sec, "[REDACTED]")
    if len(s) > MAX_OUTPUT_CHARS:
        raise GatewayDenied(f"tool output too large ({len(s)} chars)", status="error")
    return json.loads(s)


def invoke(db: Session, tool: str, args: dict[str, Any], *, user: User | None = None, agent_id: str | None = None,
           workflow: str | None = None, run_id: int | None = None, approval_id: int | None = None,
           classification: str = "INTERNAL", request_approval: bool = True) -> dict[str, Any]:
    """Run a tool through every check. Returns {"status", "result"?, "invocation_id", "decision"}; raises GatewayDenied."""
    t0 = time.monotonic()
    env = os.getenv("APP_ENV", "development")
    t = TOOLS.get(tool)
    op = t.operation if t else "?"
    rec = ToolInvocation(tool=tool, operation=op, agent_id=agent_id or "", user_email=user.email if user else "", workflow=workflow or "",
                         run_id=run_id, decision="denied", status="denied", args_redacted=_redact_args(args), approval_id=approval_id)

    def finish(status: str, decision: str, reason: str = "", category: int = 1, grant: ToolGrant | None = None, summary: str = "") -> None:
        rec.status, rec.decision, rec.reason, rec.category = status, decision, reason[:2000], category
        rec.grant_id = grant.id if grant else None
        rec.output_summary, rec.latency_ms = summary[:500], int((time.monotonic() - t0) * 1000)
        db.add(rec)
        db.flush()
        gov.audit(db, user.email if user else f"agent:{agent_id}", "tool.invoke", f"tool:{tool}.{op}", invocation=rec.id, status=status,
                  decision=decision, agent=agent_id, workflow=workflow, reason=reason[:300])
        from . import observability

        observability.event("tool", f"{tool}.{op}", {"invocation_id": rec.id, "status": status, "decision": decision, "approval_id": rec.approval_id,
                                                      "reason": reason[:300]}, duration_ms=rec.latency_ms)

    try:
        if t is None:
            raise GatewayDenied(f"unknown tool {tool!r}")
        # 1 agent identity
        if agent_id is not None:
            a = db.get(Agent, agent_id)
            if a is None or a.status != "active":
                raise GatewayDenied(f"agent {agent_id!r} is unknown or not active")
        # 2 user
        from ..security.rbac import has

        if user is not None and not has(user, "tools.invoke") and agent_id is None:
            raise GatewayDenied(f"user role {user.role!r} may not invoke tools")
        # 3+4 allow-lists (deny by default)
        grant = None
        if agent_id is not None:
            grant = _grant(db, "agent", agent_id, tool, op, env, lock=True) or _grant(db, "workflow", workflow, tool, op, env, lock=True)
            if grant is None:
                raise GatewayDenied(f"agent {agent_id} has no grant for {tool} {op}" + (f" (workflow {workflow})" if workflow else "") + " — deny by default")
        if user is not None:
            role_grant = _grant(db, "role", user.role, tool, op, env, lock=grant is None)
            if role_grant is None:
                raise GatewayDenied(f"{'the user this agent works for' if agent_id else 'your role'} ({user.role}) has no grant for {tool} {op}")
            grant = grant or role_grant
        elif agent_id is None:
            raise GatewayDenied("no identity: a tool call needs an agent or a user")
        # 6 inputs
        _validate(t, args)
        # 8 policy + approval (a valid approval is consumed atomically: single use even under concurrency)
        req = Request(action=f"tool:{tool}.{op}", agent_id=agent_id, user_email=user.email if user else None, user_role=user.role if user else None,
                      workflow=workflow, classification=classification, external=t.external, approval_id=approval_id, payload=args)
        try:
            decision = enforce(db, req, request_approval_title=f"{tool} ({op})" if request_approval else None)
        except ApprovalRequired as e:
            rec.approval_id = e.decision.approval_id
            finish("pending_approval", "approval_required", "; ".join(e.decision.reasons), e.decision.category, grant)
            raise GatewayDenied("; ".join(e.decision.reasons[-2:]), status="pending_approval", decision=e.decision.public(),
                                approval_id=e.decision.approval_id) from None
        except PolicyDenied as e:
            finish("denied", "prohibited" if e.decision.category == Category.PROHIBITED else "denied", "; ".join(e.decision.reasons),
                   e.decision.category, grant)
            raise GatewayDenied("; ".join(e.decision.reasons[-2:]), decision=e.decision.public()) from None
        # 7 budgets / rate limits — atomic counters, taken only once policy allows the call
        _take_budgets(db, grant, agent_id, user, workflow)
        # 9 execute
        ctx = ToolContext(db, user, agent_id, grant, classification)
        try:
            out = t.fn(ctx, **args)
        except NotConfigured as e:
            finish("not_configured", "allowed", str(e), decision.category, grant)
            raise GatewayDenied(str(e), status="not_configured", decision=decision.public()) from None
        except GatewayDenied as e:
            finish(e.status, "allowed", str(e), decision.category, grant)
            raise
        except (ValueError, LookupError) as e:  # bad input the schema could not catch (e.g. an invalid expression)
            finish("invalid", "allowed", str(e), decision.category, grant)
            raise GatewayDenied(str(e), status="invalid", decision=decision.public()) from None
        except Exception as e:  # noqa: BLE001 — the tool failed; recorded, not hidden
            finish("error", "allowed", f"{type(e).__name__}: {e}", decision.category, grant)
            raise GatewayDenied(f"{tool} failed: {e}", status="error", decision=decision.public()) from None
        # 10 output
        out = _redact_output(out, ctx._secrets)
        finish("ok", "allowed", "; ".join(decision.reasons[-2:]), decision.category, grant, summary=json.dumps(out, default=str)[:300])
        return {"status": "ok", "result": out, "output_class": t.output_class, "invocation_id": rec.id, "decision": decision.public()}
    except GatewayDenied as e:
        if rec.id is None:
            finish(e.status, "denied", str(e))
        e.invocation_id = rec.id  # type: ignore[attr-defined]
        raise
