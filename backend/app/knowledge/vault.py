"""DAEMON KNOWLEDGE VAULT — document lifecycle operations shared by the API and the Tool Gateway.

Deletion guarantee: chunks (text + embeddings), entity mentions, annotations, relations, the stored file and every
cached answer quoting the document are removed in ONE transaction, the in-memory retrieval index is told which
document changed (change token, same transaction), and the result is VERIFIED before returning — nothing of the
document remains queryable. Backups taken before the deletion still contain it until they age out (docs: backups).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..governance import core as gov
from ..models import Annotation, Collection, Document, DocumentChunk, DocumentRelation, EntityMention

CLASSIFICATIONS = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", "HIGHLY_SENSITIVE"]


def _rank(c: str | None) -> int:
    return CLASSIFICATIONS.index(c) if c in CLASSIFICATIONS else 1


def effective(doc_cls: str, doc_access: dict | None, col: Collection | None) -> tuple[str, dict[str, list[str]]]:
    """Inherited permissions: readers = document list ∪ collection list; classification = the higher one."""
    cls = doc_cls if col is None or _rank(doc_cls) >= _rank(col.classification) else col.classification
    a, c = doc_access or {}, (col.access if col else None) or {}
    return cls, {"roles": sorted(set(a.get("roles", [])) | set(c.get("roles", []))), "users": sorted(set(a.get("users", [])) | set(c.get("users", [])))}


def can_read(user: Any, owner_id: int | None, cls: str, access: dict[str, list[str]]) -> bool:
    """The single rule for every path (search, ask, document view, tools, agents, model context).
    No user (system / agent without a user): only documents everyone may read."""
    explicit = bool(access.get("roles") or access.get("users"))
    if user is None:
        return _rank(cls) <= 1 and not explicit
    from ..security.rbac import has

    if not has(user, "knowledge.read"):
        return False
    if owner_id is not None and owner_id == user.id:
        return True
    listed = user.role in access.get("roles", []) or user.email in access.get("users", [])
    rank = _rank(cls)
    if rank == 4:  # HIGHLY_SENSITIVE: owner and named people only — not even administrators
        return user.email in access.get("users", [])
    if rank >= 2:  # CONFIDENTIAL / RESTRICTED: listed, or a knowledge administrator
        return listed or has(user, "knowledge.admin")
    return listed or not explicit or has(user, "knowledge.admin")


def readable_ids(db: Session, user: Any, doc_ids: list[int] | None = None) -> set[int]:
    cols = {c.name: c for c in db.scalars(select(Collection))}
    q = select(Document.id, Document.owner_id, Document.classification, Document.access, Document.collection)
    if doc_ids is not None:
        q = q.where(Document.id.in_(doc_ids))
    out = set()
    for did, owner, cls, acc, col in db.execute(q).all():
        c, a = effective(cls or "INTERNAL", acc, cols.get(col))
        if can_read(user, owner, c, a):
            out.add(did)
    return out


def check_read(db: Session, user: Any, did: int) -> Document:
    """404 for both 'missing' and 'not yours' — never reveal that a document exists."""
    d = db.get(Document, did)
    if d is None or did not in readable_ids(db, user, [did]):
        raise LookupError("document not found")
    return d


def max_classification(db: Session, doc_ids: list[int]) -> str:
    if not doc_ids:
        return "PUBLIC"
    cols = {c.name: c for c in db.scalars(select(Collection))}
    worst = 0
    for cls, acc, col in db.execute(select(Document.classification, Document.access, Document.collection).where(Document.id.in_(doc_ids))).all():
        worst = max(worst, _rank(effective(cls or "INTERNAL", acc, cols.get(col))[0]))
    return CLASSIFICATIONS[worst]


def widens(old_cls: str, old_access: dict | None, new_cls: str, new_access: dict | None) -> bool:
    """True when the change lets MORE people read: a lower classification, new readers, or dropping an explicit list."""
    o, n = old_access or {}, new_access or {}
    if _rank(new_cls) < _rank(old_cls):
        return True
    if set(n.get("roles", [])) - set(o.get("roles", [])) or set(n.get("users", [])) - set(o.get("users", [])):
        return True
    old_explicit, new_explicit = bool(o.get("roles") or o.get("users")), bool(n.get("roles") or n.get("users"))
    return old_explicit and not new_explicit and _rank(new_cls) <= 1


def sensitivity_for(classification: str) -> str:
    """Model routing per classification (enforced by daemon/policy.plan, which no caller can override):
    PUBLIC / INTERNAL → any permitted provider · CONFIDENTIAL → local or self-hosted LAN ("private") ·
    RESTRICTED → this machine's models only ("sensitive") · HIGHLY_SENSITIVE → in-process models only."""
    r = _rank(classification)
    return "highly_sensitive" if r >= 4 else "sensitive" if r == 3 else "private" if r == 2 else "normal"


def delete_document(db: Session, did: int, *, actor: str) -> dict[str, Any]:
    from ..daemon import semantic_cache

    d = db.get(Document, did)
    if d is None:
        raise LookupError(f"document {did} does not exist")
    chunks = int(db.scalar(select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == did)) or 0)
    db.query(DocumentChunk).filter(DocumentChunk.document_id == did).execution_options(archive_docs=[did]).delete()
    db.query(EntityMention).filter(EntityMention.document_id == did).delete()
    db.query(Annotation).filter(Annotation.document_id == did).delete()
    db.query(DocumentRelation).filter((DocumentRelation.source_id == did) | (DocumentRelation.target_id == did)).delete(synchronize_session=False)
    file_removed = False
    if d.file_path:
        Path(d.file_path).unlink(missing_ok=True)
        file_removed = not Path(d.file_path).exists()
    purged = semantic_cache.purge_document(db, did)  # quoted chunks must not survive inside cached answers
    title = d.title
    db.delete(d)
    db.flush()
    remaining = int(db.scalar(select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == did)) or 0)
    verified = remaining == 0 and db.get(Document, did) is None and (not d.file_path or file_removed)
    if not verified:
        raise RuntimeError(f"deletion of document {did} could not be verified ({remaining} chunks remain)")
    gov.audit(db, actor, "archive.delete", f"document:{did}", title=title, chunks_removed=chunks, cache_purged=purged, verified=True)
    return {"deleted": did, "chunks_removed": chunks, "cache_purged": purged, "file_removed": file_removed or not d.file_path, "verified": True}
