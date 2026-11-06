"""DAEMON AUDIT & PROVENANCE — tamper-evident audit trail.

Every audit record is SEALED when its transaction commits: it gets the next sequence number and
    hash = HMAC-SHA256(key, previous hash ‖ canonical(record))
so records form a keyed hash chain. What this detects (verify()):
  * a changed field in any record (its hash no longer matches),
  * a deleted record (gap in the sequence / broken link),
  * re-ordered or inserted records (broken link),
  * a truncated tail (the chain head kept in system_state no longer matches the last record).
Because the hash is KEYED (AUDIT_HMAC_KEY, or derived from SECRET_KEY), someone with write access to the database
alone cannot rewrite the chain consistently. Limits — documented, not hidden: whoever holds BOTH the database and the
key can recompute everything (anchor exported, signed manifests outside the system to defend against that); the
database triggers (append-only: no UPDATE of a sealed record, no DELETE outside retention pruning) stop the
application and casual edits, not a database superuser. A normal database table is not immutable.

Sealing happens at commit (not when the record is created) so the chain lock is held only for the commit itself —
never across a long agent transaction.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import os
import zipfile
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DDL, event, select
from sqlalchemy.orm import Session

HEAD = "audit_head"      # system_state key: {"seq": n, "hash": h}
ANCHOR = "audit_anchor"  # where verification starts after retention pruning: {"seq": n, "hash": h, "pruned_at": …}
PRUNING = "audit_prune_in_progress"
GENESIS = "0" * 64


def _key(purpose: str) -> bytes:
    from ..config import get_settings

    base = os.getenv("AUDIT_HMAC_KEY") or f"derived:{get_settings().secret_key}"
    return hashlib.sha256(f"dk-{purpose}-v1|{base}".encode()).digest()


def _ts(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")


def canonical(seq: int, actor: str, action: str, target: str, details: Any, created_at: datetime | None) -> bytes:
    return json.dumps({"seq": seq, "actor": actor, "action": action, "target": target or "", "details": details or {},
                       "created_at": _ts(created_at)}, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()


def seal_hash(prev: str, seq: int, row: Any) -> str:
    return hmac.new(_key("audit"), prev.encode() + b"|" + canonical(seq, row.actor, row.action, row.target, row.details, row.created_at),
                    hashlib.sha256).hexdigest()


# ------------------------------------------------------------------ sealing at commit
def _state_row(session: Session, key: str, lock: bool = False):
    from ..models import SystemState

    q = select(SystemState).where(SystemState.key == key)
    return session.execute(q.with_for_update() if lock else q).scalar_one_or_none()


def _install() -> None:
    from ..models import AuditLog

    @event.listens_for(Session, "after_flush")
    def _track(session: Session, _ctx: Any) -> None:
        new = [o for o in session.new if isinstance(o, AuditLog)]
        if new:
            session.info.setdefault("audit_unsealed", []).extend(new)

    @event.listens_for(Session, "before_commit")
    def _seal(session: Session) -> None:
        session.flush()
        rows = session.info.pop("audit_unsealed", [])
        if not rows:
            return
        from ..models import SystemState

        head = _state_row(session, HEAD, lock=True)
        state = dict(head.value) if head else {"seq": 0, "hash": GENESIS}
        seq, prev = int(state["seq"]), state["hash"]
        for r in sorted(rows, key=lambda x: x.id):
            if r.hash:
                continue
            seq += 1
            r.seq, r.prev_hash = seq, prev
            r.hash = prev = seal_hash(prev, seq, r)
        if head:
            head.value = {"seq": seq, "hash": prev}
        else:
            session.add(SystemState(key=HEAD, value={"seq": seq, "hash": prev}))
        session.flush()

    @event.listens_for(Session, "after_rollback")
    def _forget(session: Session) -> None:
        session.info.pop("audit_unsealed", None)

    # append-only at the database level (also created by migration 0006 for migrated databases)
    for ddl in TRIGGERS_SQLITE:
        event.listen(AuditLog.__table__, "after_create", DDL(ddl).execute_if(dialect="sqlite"))
    for ddl in TRIGGERS_POSTGRES:
        event.listen(AuditLog.__table__, "after_create", DDL(ddl).execute_if(dialect="postgresql"))


TRIGGERS_SQLITE = [
    """CREATE TRIGGER IF NOT EXISTS audit_log_append_only_update BEFORE UPDATE ON audit_log WHEN OLD.hash IS NOT NULL AND OLD.hash != ''
       BEGIN SELECT RAISE(ABORT, 'audit_log is append-only: sealed records cannot be changed'); END""",
    """CREATE TRIGGER IF NOT EXISTS audit_log_append_only_delete BEFORE DELETE ON audit_log
       WHEN NOT EXISTS (SELECT 1 FROM system_state WHERE key = 'audit_prune_in_progress')
       BEGIN SELECT RAISE(ABORT, 'audit_log is append-only: records are removed only by retention pruning'); END""",
]
TRIGGERS_POSTGRES = [
    """CREATE OR REPLACE FUNCTION audit_log_append_only() RETURNS trigger AS $$
       BEGIN
         IF TG_OP = 'UPDATE' AND OLD.hash IS NOT NULL AND OLD.hash <> '' THEN
           RAISE EXCEPTION 'audit_log is append-only: sealed records cannot be changed';
         END IF;
         IF TG_OP = 'DELETE' AND NOT EXISTS (SELECT 1 FROM system_state WHERE key = 'audit_prune_in_progress') THEN
           RAISE EXCEPTION 'audit_log is append-only: records are removed only by retention pruning';
         END IF;
         IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
         RETURN NEW;
       END $$ LANGUAGE plpgsql""",
    "DROP TRIGGER IF EXISTS audit_log_append_only ON audit_log",
    "CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON audit_log FOR EACH ROW EXECUTE FUNCTION audit_log_append_only()",
]


# ------------------------------------------------------------------ verification
def verify(db: Session, limit: int | None = None) -> dict[str, Any]:
    """Walk the chain from the retention anchor (or genesis) and report the FIRST problem found."""
    from ..models import AuditLog

    anchor = _state_row(db, ANCHOR)
    a = dict(anchor.value) if anchor else {"seq": 0, "hash": GENESIS}
    expect_seq, prev = int(a["seq"]) + 1, a["hash"]
    checked = 0
    unsealed = db.scalars(select(AuditLog.id).where((AuditLog.hash.is_(None)) | (AuditLog.hash == "")).limit(5)).all()
    q = select(AuditLog).where(AuditLog.seq.is_not(None), AuditLog.seq >= expect_seq).order_by(AuditLog.seq)
    if limit:
        q = q.limit(limit)
    for r in db.execute(q).scalars():
        if r.seq != expect_seq:
            return _bad(checked, r.seq, f"sequence gap: expected {expect_seq}, found {r.seq} — record(s) deleted or chain re-ordered")
        if r.prev_hash != prev:
            return _bad(checked, r.seq, "broken link: previous-hash does not match the preceding record")
        if not hmac.compare_digest(r.hash, seal_hash(prev, r.seq, r)):
            return _bad(checked, r.seq, f"content changed: record {r.id} ({r.action}) no longer matches its seal")
        prev, expect_seq, checked = r.hash, expect_seq + 1, checked + 1
    head = _state_row(db, HEAD)
    h = dict(head.value) if head else {"seq": 0, "hash": GENESIS}
    if not limit and (int(h["seq"]) != expect_seq - 1 or h["hash"] != prev):
        return _bad(checked, expect_seq, f"chain head mismatch: head says seq {h['seq']}, last verified record is {expect_seq - 1} — tail truncated or head altered")
    return {"ok": True, "checked": checked, "first_seq": int(a["seq"]) + 1, "last_seq": expect_seq - 1, "head_hash": prev,
            "unsealed_records": len(unsealed), "anchored": bool(anchor), "verified_at": datetime.now(UTC).isoformat(),
            "limitations": "detects edits, deletions, re-ordering and truncation by anyone without the audit key"}


def _bad(checked: int, seq: int, reason: str) -> dict[str, Any]:
    return {"ok": False, "checked": checked, "failed_at_seq": seq, "reason": reason, "verified_at": datetime.now(UTC).isoformat()}


# ------------------------------------------------------------------ retention
def prune(db: Session, before: datetime, actor: str) -> dict[str, Any]:
    """Retention: remove the OLDEST records (created before `before`) only after verifying them, and keep an anchor
    (last removed seq + hash) so the remaining chain still verifies. Writes its own audit record."""
    from ..models import AuditLog, SystemState
    from . import core as gov

    v = verify(db)
    if not v["ok"]:
        raise ValueError(f"refusing to prune an audit trail that does not verify: {v['reason']}")
    rows = db.scalars(select(AuditLog).where(AuditLog.created_at < before, AuditLog.seq.is_not(None)).order_by(AuditLog.seq)).all()
    # only a contiguous prefix of the chain may go
    anchor = _state_row(db, ANCHOR)
    start = int(dict(anchor.value)["seq"]) + 1 if anchor else 1
    prefix = []
    for r in rows:
        if r.seq != start + len(prefix):
            break
        prefix.append(r)
    if not prefix:
        return {"pruned": 0}
    last = prefix[-1]
    db.add(SystemState(key=PRUNING, value={"by": actor}))
    db.flush()
    for r in prefix:
        db.delete(r)
    db.flush()
    db.delete(_state_row(db, PRUNING))
    new_anchor = {"seq": last.seq, "hash": last.hash, "pruned_at": datetime.now(UTC).isoformat(), "pruned_by": actor}
    if anchor:
        anchor.value = new_anchor
    else:
        db.add(SystemState(key=ANCHOR, value=new_anchor))
    gov.audit(db, actor, "audit.pruned", "audit_log", records=len(prefix), up_to_seq=last.seq, before=before.isoformat())
    db.flush()
    return {"pruned": len(prefix), "anchor_seq": last.seq}


# ------------------------------------------------------------------ export
FIELDS = ["seq", "id", "created_at", "actor", "action", "target", "details", "prev_hash", "hash"]


def query(db: Session, *, since: datetime | None = None, until: datetime | None = None, actor: str | None = None,
          action: str | None = None, target: str | None = None, limit: int = 100_000) -> list[Any]:
    from ..models import AuditLog

    q = select(AuditLog)
    if since:
        q = q.where(AuditLog.created_at >= since)
    if until:
        q = q.where(AuditLog.created_at < until)
    if actor:
        q = q.where(AuditLog.actor == actor)
    if action:
        q = q.where(AuditLog.action.like(action.replace("*", "%")))
    if target:
        q = q.where(AuditLog.target.like(f"{target}%"))
    return list(db.scalars(q.order_by(AuditLog.seq.is_(None), AuditLog.seq, AuditLog.id).limit(limit)))


def _record(r: Any) -> dict[str, Any]:
    return {"seq": r.seq, "id": r.id, "created_at": _ts(r.created_at), "actor": r.actor, "action": r.action, "target": r.target,
            "details": r.details, "prev_hash": r.prev_hash, "hash": r.hash}


def export(db: Session, fmt: str, filters: dict[str, Any], actor: str) -> tuple[bytes, str]:
    """json | csv | zip. The ZIP holds events.json, events.csv, manifest.json (filters, counts, chain verification,
    SHA-256 of each file, the chain head) and manifest.sig = HMAC-SHA256 of manifest.json with the export key."""
    rows = [_record(r) for r in query(db, **filters)]
    if fmt == "json":
        return json.dumps(rows, ensure_ascii=False, indent=1).encode(), "application/json"
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=FIELDS)
    w.writeheader()
    for r in rows:
        w.writerow({**r, "details": json.dumps(r["details"], ensure_ascii=False, sort_keys=True)})
    csv_bytes = buf.getvalue().encode()
    if fmt == "csv":
        return csv_bytes, "text/csv"
    events = json.dumps(rows, ensure_ascii=False, indent=1).encode()
    manifest = {"generator": "Demonkoncernen AB · DAEMON AUDIT & PROVENANCE", "generated_at": datetime.now(UTC).isoformat(), "generated_by": actor,
                "filters": {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in filters.items() if v},
                "records": len(rows), "first_seq": rows[0]["seq"] if rows else None, "last_seq": rows[-1]["seq"] if rows else None,
                "chain_verification": verify(db),
                "files": {"events.json": hashlib.sha256(events).hexdigest(), "events.csv": hashlib.sha256(csv_bytes).hexdigest()},
                "signature": "manifest.sig = HMAC-SHA256(export key, manifest.json); verify with `python -m app.cli audit-verify-export <zip>`"}
    mbytes = json.dumps(manifest, indent=1, sort_keys=True).encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("events.json", events)
        z.writestr("events.csv", csv_bytes)
        z.writestr("manifest.json", mbytes)
        z.writestr("manifest.sig", hmac.new(_key("audit-export"), mbytes, hashlib.sha256).hexdigest())
    return out.getvalue(), "application/zip"


def verify_export(data: bytes) -> dict[str, Any]:
    """Check an exported ZIP: manifest signature, file hashes, and that the records chain to each other."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        mbytes, sig = z.read("manifest.json"), z.read("manifest.sig").decode().strip()
        problems = []
        if not hmac.compare_digest(sig, hmac.new(_key("audit-export"), mbytes, hashlib.sha256).hexdigest()):
            problems.append("manifest signature invalid (manifest changed, or a different key)")
        m = json.loads(mbytes)
        for name, digest in m["files"].items():
            if hashlib.sha256(z.read(name)).hexdigest() != digest:
                problems.append(f"{name} changed after export")
        rows = json.loads(z.read("events.json"))
    for a, b in zip(rows, rows[1:], strict=False):
        if a["seq"] is not None and b["seq"] == a["seq"] + 1 and b["prev_hash"] != a["hash"]:
            problems.append(f"records {a['seq']}→{b['seq']} do not chain")
            break
    return {"ok": not problems, "problems": problems, "records": len(rows)}
