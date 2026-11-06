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
from ..models import Annotation, Document, DocumentChunk, DocumentRelation, EntityMention


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
