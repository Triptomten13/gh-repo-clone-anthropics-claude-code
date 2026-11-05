"""REST API: AI core, The Archive, Memory, Archivum, G-sus, Demonkoncernen HQ."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..agents.catalog import build_orchestrator
from ..ai import registry, tracing
from ..ai.llm import LLMRefused, LLMUnavailable, get_provider, get_router
from ..config import get_settings
from ..db import get_db
from ..evals import runner as evals
from ..governance import core as gov
from ..gsus import engine as gsus
from ..gsus import modes as gmodes
from ..knowledge import canon, memory, process, search
from ..knowledge.extract import ExtractionError, extract
from ..models import (EVIDENCE_CLASSES, MEMORY_SCOPES, Agent, Annotation, Approval, AuditLog, BrandConcept, CanonAssertion, CanonChapter,
                      CanonVersion, CanonWork, CreativeAsset, Document, DocumentChunk, DocumentRelation, Entity, EntityMention, Experiment,
                      GsusRun, GsusStep, LLMCall, MemoryItem, Task, TimelineEvent, User)
from ..security.auth import current_user, require_role
from .routes import row

router = APIRouter(prefix="/api")
operator = require_role("admin", "operator")
admin_only = require_role("admin")


def _404(obj: Any, what: str) -> Any:
    if obj is None:
        raise HTTPException(404, f"{what} not found")
    return obj


# =================================================================== AI core
@router.get("/ai/models")
def ai_models(db: Session = Depends(get_db), _: User = Depends(current_user)):
    last = (gov.get_state(db, "evals").get("runs") or [None])[0]
    out = []
    for m in registry.all_models():
        d = m.as_dict()
        d["available"] = m.provider == "local" or any(h["provider"] == m.provider and h.get("configured") for h in get_router().health())
        if last:
            d["evaluations"] = [e for e in last.get("suites", []) if e.get("model") in (m.model_id, None) and e.get("requires_llm") == (m.provider != "local")]
        out.append(d)
    from ..daemon import policy

    provs = get_router()._all_providers()
    return {"models": out, "chains": {t: [[c.provider, c.model] for c in policy.plan(t, provs)[0]] for t in ("deep", "standard", "fast")}}


@router.get("/ai/providers")
def ai_providers(_: User = Depends(current_user)):
    model_id, _e = process.embedder()
    return {"llm": get_router().health(), "active": get_provider().name, "llm_enabled": get_settings().llm_enabled,
            "embeddings": {"active": model_id, "note": "local-hash-256 is lexical; set OLLAMA_EMBED_MODEL for semantic embeddings"}}


@router.get("/ai/usage")
def ai_usage(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db), _: User = Depends(current_user)):
    return {**tracing.usage(db, days), "spent_today_usd": round(tracing.spent_today(db), 6), "daily_cost_limit_usd": get_settings().daily_cost_limit_usd}


@router.get("/ai/calls")
def ai_calls(limit: int = Query(100, le=500), db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [row(c) for c in db.scalars(select(LLMCall).order_by(LLMCall.id.desc()).limit(limit)).all()]


@router.post("/ai/evals/run")
def run_evals(include_llm: bool = False, db: Session = Depends(get_db), user: User = Depends(operator)):
    res = evals.run_all(include_llm=include_llm)
    st = gov.get_state(db, "evals")
    st["runs"] = [res, *(st.get("runs") or [])][:20]
    gov.set_state(db, "evals", st)
    gov.audit(db, user.email, "ai.evals", summary={s["suite"]: s.get("score") for s in res["suites"]})
    db.commit()
    return res


@router.get("/ai/evals")
def list_evals(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return gov.get_state(db, "evals").get("runs") or []


# =================================================================== The Archive
def _flagged(db: Session) -> int:
    """Counted in Python: PostgreSQL's json type has no equality operator (portable across SQLite/PostgreSQL)."""
    return sum(1 for flags in db.scalars(select(Document.injection_flags)).all() if flags)


def _doc_out(d: Document, db: Session | None = None) -> dict[str, Any]:
    out = row(d, {"file_path"})
    if db is not None:
        out["chunks"] = db.query(DocumentChunk).filter(DocumentChunk.document_id == d.id).count()
    return out


def _meta(title: str, description: str, source: str, source_url: str, author: str, created_date: str, tags: str, categories: str,
          evidence_class: str, filename: str) -> dict[str, Any]:
    if evidence_class not in EVIDENCE_CLASSES:
        raise HTTPException(422, f"evidence_class must be one of {EVIDENCE_CLASSES}")
    split = lambda s: [x.strip() for x in s.split(",") if x.strip()]  # noqa: E731
    return {"title": title or filename, "description": description, "source": source, "source_url": source_url, "author": author,
            "created_date": created_date, "tags": split(tags), "categories": split(categories), "evidence_class": evidence_class, "filename": filename}


@router.post("/archive/upload")
async def archive_upload(file: UploadFile = File(...), title: str = Form(""), description: str = Form(""), source: str = Form(""),
                         source_url: str = Form(""), author: str = Form(""), created_date: str = Form(""), tags: str = Form(""),
                         categories: str = Form(""), evidence_class: str = Form("unclassified"), parent_id: int | None = Form(None),
                         db: Session = Depends(get_db), user: User = Depends(operator)):
    data = await file.read()
    try:
        ex = extract(file.filename or "upload", data)
    except ExtractionError as e:
        raise HTTPException(415, str(e)) from e
    parent = db.get(Document, parent_id) if parent_id else None
    doc = process.ingest(db, ex, _meta(title, description, source, source_url, author, created_date, tags, categories, evidence_class,
                                       file.filename or "upload"), raw=data, owner_id=user.id, parent=parent)
    gov.audit(db, user.email, "archive.upload", f"document:{doc.id}", status=doc.status, injection_flags=doc.injection_flags)
    db.commit()
    return _doc_out(doc, db)


class TextDoc(BaseModel):
    title: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=2_000_000)
    description: str = ""
    source: str = ""
    source_url: str = ""
    author: str = ""
    created_date: str = ""
    tags: list[str] = []
    categories: list[str] = []
    evidence_class: str = "unclassified"
    doc_type: str = "txt"
    parent_id: int | None = None


@router.post("/archive/text")
def archive_text(body: TextDoc, db: Session = Depends(get_db), user: User = Depends(operator)):
    from ..knowledge.extract import Extracted

    if body.evidence_class not in EVIDENCE_CLASSES:
        raise HTTPException(422, f"evidence_class must be one of {EVIDENCE_CLASSES}")
    ex = Extracted("markdown" if body.doc_type == "markdown" else "txt", "text/plain", body.text)
    parent = db.get(Document, body.parent_id) if body.parent_id else None
    doc = process.ingest(db, ex, body.model_dump(), owner_id=user.id, parent=parent)
    gov.audit(db, user.email, "archive.text", f"document:{doc.id}", status=doc.status)
    db.commit()
    return _doc_out(doc, db)


@router.get("/archive/documents")
def archive_list(q: str | None = None, doc_type: str | None = None, evidence_class: str | None = None, tag: str | None = None,
                 status: str | None = None, latest_only: bool = True, limit: int = Query(200, le=1000),
                 db: Session = Depends(get_db), _: User = Depends(current_user)):
    stmt = select(Document).order_by(Document.id.desc())
    if q:
        stmt = stmt.where(Document.title.ilike(f"%{q}%") | Document.description.ilike(f"%{q}%") | Document.author.ilike(f"%{q}%"))
    if doc_type:
        stmt = stmt.where(Document.doc_type == doc_type)
    if evidence_class:
        stmt = stmt.where(Document.evidence_class == evidence_class)
    if status:
        stmt = stmt.where(Document.status == status)
    docs = db.scalars(stmt.limit(limit)).all()
    if tag:
        docs = [d for d in docs if tag in (d.tags or [])]
    if latest_only:
        seen, out = set(), []
        for d in docs:
            if d.lineage_id not in seen:
                seen.add(d.lineage_id)
                out.append(d)
        docs = out
    return [_doc_out(d) for d in docs]


@router.get("/archive/documents/{did}")
def archive_get(did: int, offset: int = 0, db: Session = Depends(get_db), _: User = Depends(current_user)):
    d = _404(db.get(Document, did), "document")
    chunks = db.scalars(select(DocumentChunk).where(DocumentChunk.document_id == did).order_by(DocumentChunk.ordinal).offset(offset).limit(50)).all()
    rels = db.scalars(select(DocumentRelation).where((DocumentRelation.source_id == did) | (DocumentRelation.target_id == did))).all()
    ents = db.execute(select(Entity, EntityMention.count).join(EntityMention, EntityMention.entity_id == Entity.id)
                      .where(EntityMention.document_id == did)).all()
    versions = db.scalars(select(Document).where(Document.lineage_id == d.lineage_id).order_by(Document.version)).all()
    return {**_doc_out(d, db), "chunks_page": [row(c, {"embedding"}) for c in chunks],
            "relations": [{**row(r), "other_title": (db.get(Document, r.target_id if r.source_id == did else r.source_id) or d).title} for r in rels],
            "entities": [{"id": e.id, "name": e.name, "kind": e.kind, "mentions": n} for e, n in ents],
            "annotations": [row(a) for a in db.scalars(select(Annotation).where(Annotation.document_id == did).order_by(Annotation.id))],
            "versions": [{"id": v.id, "version": v.version, "imported_at": v.imported_at, "status": v.status} for v in versions],
            "related": search.related_documents(db, did)}


class DocPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    source: str | None = None
    source_url: str | None = None
    author: str | None = None
    created_date: str | None = None
    tags: list[str] | None = None
    categories: list[str] | None = None
    evidence_class: str | None = None


@router.patch("/archive/documents/{did}")
def archive_patch(did: int, body: DocPatch, db: Session = Depends(get_db), user: User = Depends(operator)):
    d = _404(db.get(Document, did), "document")
    ch = body.model_dump(exclude_none=True)
    if "evidence_class" in ch and ch["evidence_class"] not in EVIDENCE_CLASSES:
        raise HTTPException(422, "invalid evidence_class")
    for k, v in ch.items():
        setattr(d, k, v)
    from ..daemon import semantic_cache

    purged = semantic_cache.purge_document(db, did)  # cached answers carry the old title / evidence class
    gov.audit(db, user.email, "archive.update", f"document:{did}", fields=sorted(ch), cache_purged=purged)
    db.commit()
    return _doc_out(d, db)


@router.delete("/archive/documents/{did}")
def archive_delete(did: int, confirm: bool = False, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    d = _404(db.get(Document, did), "document")
    if not confirm:
        raise HTTPException(400, "deleting archive data is irreversible: repeat with confirm=true")
    db.query(DocumentChunk).filter(DocumentChunk.document_id == did).delete()
    db.query(EntityMention).filter(EntityMention.document_id == did).delete()
    db.query(Annotation).filter(Annotation.document_id == did).delete()
    db.query(DocumentRelation).filter((DocumentRelation.source_id == did) | (DocumentRelation.target_id == did)).delete(synchronize_session=False)
    if d.file_path:
        Path(d.file_path).unlink(missing_ok=True)
    from ..daemon import semantic_cache

    purged = semantic_cache.purge_document(db, did)  # quoted chunks must not survive deletion inside cached answers
    title = d.title
    db.delete(d)
    gov.audit(db, user.email, "archive.delete", f"document:{did}", title=title, cache_purged=purged)
    db.commit()
    return {"deleted": did}


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    mode: str = Field(default="hybrid", pattern="^(hybrid|keyword|semantic)$")
    k: int = Field(default=8, ge=1, le=50)
    filters: dict[str, Any] = {}


@router.post("/archive/search")
def archive_search(body: SearchIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    hits = search.search(db, body.query, body.k, body.mode, body.filters)
    for h in hits:
        h.pop("text", None)
    return {"query": body.query, "mode": body.mode, "results": hits}


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    mode: str = "archivist"
    use_llm: bool = False
    filters: dict[str, Any] = {}
    strictness: float | None = None


@router.post("/archive/ask")
def archive_ask(body: AskIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    settings = gmodes.settings_for(body.mode, {"strictness": body.strictness} if body.strictness is not None else {})
    llm = None
    if body.use_llm:
        provider = get_provider()
        if provider.name == "none":
            raise HTTPException(409, "no AI provider configured — use the extractive answer (use_llm=false)")

        def llm(system: str, prompt: str):
            try:
                res = provider.complete(system=system, prompt=prompt, tier=gmodes.DEPTH_TIER[settings["depth"]])
            except (LLMUnavailable, LLMRefused) as e:
                tracing.record(db, getattr(e, "attempts", []), agent_id="gsus", purpose="archive.ask")
                raise HTTPException(503, str(e)) from e
            tracing.record(db, getattr(res, "attempts", []), agent_id="gsus", purpose="archive.ask", fallback_result=res)
            return res
    ans = search.grounded_answer(db, body.question, filters=body.filters, llm=llm, mode_prompt=gmodes.system_prompt(settings),
                                 strictness=settings["strictness"])
    ans.pop("llm_result", None)
    db.commit()
    return ans


class RelationIn(BaseModel):
    source_id: int
    target_id: int
    relation: str = Field(pattern="^(cites|interprets|compares|related|contradicts|version_of|duplicates)$")
    note: str = ""


@router.post("/archive/relations")
def archive_relation(body: RelationIn, db: Session = Depends(get_db), user: User = Depends(operator)):
    _404(db.get(Document, body.source_id), "source")
    _404(db.get(Document, body.target_id), "target")
    r = DocumentRelation(**body.model_dump(), created_by=user.email)
    db.add(r)
    db.commit()
    return row(r)


class AnnotationIn(BaseModel):
    text: str = Field(min_length=1)
    kind: str = Field(default="note", pattern="^(note|interpretation|source_comparison|correction)$")
    evidence_class: str = "unclassified"
    chunk_id: int | None = None


@router.post("/archive/documents/{did}/annotations")
def archive_annotate(did: int, body: AnnotationIn, db: Session = Depends(get_db), user: User = Depends(operator)):
    _404(db.get(Document, did), "document")
    if body.evidence_class not in EVIDENCE_CLASSES:
        raise HTTPException(422, "invalid evidence_class")
    a = Annotation(document_id=did, author=user.email, **body.model_dump())
    db.add(a)
    db.commit()
    return row(a)


@router.get("/archive/entities")
def archive_entities(db: Session = Depends(get_db), _: User = Depends(current_user)):
    rows = db.execute(select(Entity, func.count(EntityMention.id)).join(EntityMention, EntityMention.entity_id == Entity.id, isouter=True)
                      .group_by(Entity.id).order_by(func.count(EntityMention.id).desc())).all()
    return [{"id": e.id, "name": e.name, "kind": e.kind, "aliases": e.aliases, "documents": n} for e, n in rows]


@router.get("/archive/graph")
def archive_graph(limit: int = Query(60, le=300), db: Session = Depends(get_db), _: User = Depends(current_user)):
    ments = db.scalars(select(EntityMention).limit(2000)).all()
    docs = {d.id: d for d in db.scalars(select(Document).where(Document.status == "ready")).all()}
    ents = {e.id: e for e in db.scalars(select(Entity)).all()}
    nodes, edges = {}, []
    for m in ments[:limit * 4]:
        if m.document_id not in docs or m.entity_id not in ents:
            continue
        nodes[f"d{m.document_id}"] = {"key": f"d{m.document_id}", "label": docs[m.document_id].title, "kind": "document",
                                       "data": {"evidence_class": docs[m.document_id].evidence_class}}
        nodes[f"e{m.entity_id}"] = {"key": f"e{m.entity_id}", "label": ents[m.entity_id].name, "kind": ents[m.entity_id].kind}
        edges.append({"source": f"d{m.document_id}", "target": f"e{m.entity_id}", "relation": f"mentions ×{m.count}"})
    return {"nodes": list(nodes.values())[:limit], "edges": edges}


@router.post("/archive/reembed")
def archive_reembed(db: Session = Depends(get_db), user: User = Depends(admin_only)):
    n = process.reembed(db)
    gov.audit(db, user.email, "archive.reembed", chunks=n)
    db.commit()
    return {"reembedded_chunks": n, "model": process.embedder()[0]}


@router.get("/archive/stats")
def archive_stats(db: Session = Depends(get_db), _: User = Depends(current_user)):
    by_class = dict(db.execute(select(Document.evidence_class, func.count(Document.id)).group_by(Document.evidence_class)).all())
    by_status = dict(db.execute(select(Document.status, func.count(Document.id)).group_by(Document.status)).all())
    return {"documents": db.query(Document).count(), "chunks": db.query(DocumentChunk).count(), "entities": db.query(Entity).count(),
            "by_evidence_class": by_class, "by_status": by_status, "injection_flagged": _flagged(db),
            "embedding_model": process.embedder()[0], "evidence_classes": list(EVIDENCE_CLASSES)}


# =================================================================== Memory (user-controlled)
class MemoryIn(BaseModel):
    scope: str
    key: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=20_000)
    tags: list[str] = []
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)
    allow_personal: bool = False


@router.get("/memory")
def memory_list(scope: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = select(MemoryItem).where(MemoryItem.owner_id == user.id).order_by(MemoryItem.id.desc())
    if scope:
        q = q.where(MemoryItem.scope == scope)
    now = datetime.now(UTC)
    return [row(m) for m in db.scalars(q).all() if not m.expires_at or (m.expires_at if m.expires_at.tzinfo else m.expires_at.replace(tzinfo=UTC)) > now]


@router.post("/memory")
def memory_add(body: MemoryIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if body.scope not in MEMORY_SCOPES:
        raise HTTPException(422, f"scope must be one of {MEMORY_SCOPES}")
    check = memory.screen(body.content + " " + body.key)
    if check["refuse"]:
        raise HTTPException(422, f"not stored: contains {', '.join(check['refuse'])}. Memory never keeps credentials or ID/card numbers.")
    if check["warn"] and not body.allow_personal:
        raise HTTPException(409, f"contains {', '.join(check['warn'])}; resend with allow_personal=true if you want this remembered")
    m = MemoryItem(owner_id=user.id, scope=body.scope, key=body.key, content=body.content, tags=body.tags, source="user",
                   expires_at=datetime.now(UTC) + timedelta(days=body.expires_in_days) if body.expires_in_days else None)
    db.add(m)
    db.commit()
    return row(m)


class MemoryPatch(BaseModel):
    key: str | None = None
    content: str | None = None
    tags: list[str] | None = None


@router.patch("/memory/{mid}")
def memory_edit(mid: int, body: MemoryPatch, db: Session = Depends(get_db), user: User = Depends(current_user)):
    m = db.get(MemoryItem, mid)
    if m is None or m.owner_id != user.id:
        raise HTTPException(404, "memory item not found")
    ch = body.model_dump(exclude_none=True)
    if "content" in ch and memory.screen(ch["content"])["refuse"]:
        raise HTTPException(422, "content contains data memory never stores")
    for k, v in ch.items():
        setattr(m, k, v)
    db.commit()
    return row(m)


@router.delete("/memory/{mid}")
def memory_delete(mid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    m = db.get(MemoryItem, mid)
    if m is None or m.owner_id != user.id:
        raise HTTPException(404, "memory item not found")
    db.delete(m)
    db.commit()
    return {"deleted": mid}


@router.get("/memory/export")
def memory_export(db: Session = Depends(get_db), user: User = Depends(current_user)):
    items = [row(m) for m in db.scalars(select(MemoryItem).where(MemoryItem.owner_id == user.id)).all()]
    return {"exported_at": datetime.now(UTC).isoformat(), "owner": user.email, "items": items}


@router.delete("/memory")
def memory_clear(scope: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    n = db.query(MemoryItem).filter(MemoryItem.owner_id == user.id, MemoryItem.scope == scope).delete()
    db.commit()
    return {"deleted": n, "scope": scope}


# =================================================================== Archivum Scientiae Vetitae
@router.get("/archivum/works")
def canon_works(db: Session = Depends(get_db), _: User = Depends(current_user)):
    out = []
    for w in db.scalars(select(CanonWork).order_by(CanonWork.number)).all():
        out.append({**row(w), "chapters": db.query(CanonChapter).filter(CanonChapter.work_id == w.id).count()})
    return {"works": out, "totals": {"works": len(out), "chapters": db.query(CanonChapter).count()},
            "note": None if out else "No canon structure is stored yet. Import your books/chapters — the platform never invents canon."}


@router.get("/archivum/works/{wid}")
def canon_work(wid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    w = _404(db.get(CanonWork, wid), "work")
    return {**row(w), "chapters": [row(c) for c in db.scalars(select(CanonChapter).where(CanonChapter.work_id == wid).order_by(CanonChapter.number))]}


class CanonImport(BaseModel):
    data: dict[str, Any]
    expected: dict[str, int] = {}
    note: str = "import"


@router.post("/archivum/import")
def canon_import(body: CanonImport, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    try:
        res = canon.import_structure(db, body.data, body.expected)
    except (KeyError, ValueError, TypeError) as e:
        raise HTTPException(422, f"invalid structure: {e}") from e
    v = canon.new_version(db, body.note, user.email)
    gov.audit(db, user.email, "canon.import", f"canon_version:{v.version}", **res["totals"])
    db.commit()
    return {**res, "canon_version": v.version}


class ChapterPatch(BaseModel):
    title: str | None = None
    summary: str | None = None
    body: str | None = None
    status: str | None = Field(default=None, pattern="^(draft|canon|retired)$")
    document_id: int | None = None


@router.patch("/archivum/chapters/{cid}")
def canon_chapter_patch(cid: int, body: ChapterPatch, db: Session = Depends(get_db), user: User = Depends(operator)):
    c = _404(db.get(CanonChapter, cid), "chapter")
    ch = body.model_dump(exclude_none=True)
    if ch.get("status") == "canon" and user.role != "admin":
        raise HTTPException(403, "only an admin can promote text to canon")
    for k, v in ch.items():
        setattr(c, k, v)
    gov.audit(db, user.email, "canon.chapter", f"chapter:{cid}", fields=sorted(ch))
    db.commit()
    return row(c)


class AssertionIn(BaseModel):
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: str = Field(min_length=1)
    evidence_class: str = "fiction_canon"
    chapter_id: int | None = None
    document_id: int | None = None
    source_note: str = ""


@router.get("/archivum/assertions")
def canon_assertions(subject: str | None = None, db: Session = Depends(get_db), _: User = Depends(current_user)):
    q = select(CanonAssertion).order_by(CanonAssertion.subject, CanonAssertion.predicate)
    if subject:
        q = q.where(CanonAssertion.subject.ilike(f"%{subject}%"))
    return [row(a) for a in db.scalars(q).all()]


@router.post("/archivum/assertions")
def canon_add_assertion(body: AssertionIn, db: Session = Depends(get_db), user: User = Depends(operator)):
    if body.evidence_class not in EVIDENCE_CLASSES:
        raise HTTPException(422, "invalid evidence_class")
    if body.evidence_class in ("historical_fact", "primary_source") and not (body.source_note or body.document_id):
        raise HTTPException(422, "historical claims need a source (source_note or document_id)")
    a = CanonAssertion(**body.model_dump(), created_by=user.email)
    db.add(a)
    db.flush()
    conflicts = [c for c in canon.contradictions(db) if any(v.get("assertion_id") == a.id for v in c["values"])]
    db.commit()
    return {**row(a), "conflicts": conflicts}


@router.post("/archivum/assertions/{aid}/retire")
def canon_retire(aid: int, db: Session = Depends(get_db), user: User = Depends(operator)):
    a = _404(db.get(CanonAssertion, aid), "assertion")
    a.status = "retired"
    gov.audit(db, user.email, "canon.retire", f"assertion:{aid}")
    db.commit()
    return row(a)


@router.get("/archivum/contradictions")
def canon_contradictions(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return canon.contradictions(db)


class TimelineIn(BaseModel):
    label: str = Field(min_length=1)
    date_text: str = Field(min_length=1)
    evidence_class: str = "unclassified"
    description: str = ""
    document_id: int | None = None
    chapter_id: int | None = None
    source_note: str = ""


@router.get("/archivum/timeline")
def timeline(db: Session = Depends(get_db), _: User = Depends(current_user)):
    evs = db.scalars(select(TimelineEvent)).all()
    return sorted([row(e) for e in evs], key=lambda e: (e["sort_year"] is None, e["sort_year"] or 0))


@router.post("/archivum/timeline")
def timeline_add(body: TimelineIn, db: Session = Depends(get_db), user: User = Depends(operator)):
    if body.evidence_class not in EVIDENCE_CLASSES:
        raise HTTPException(422, "invalid evidence_class")
    e = TimelineEvent(**body.model_dump(), sort_year=canon.parse_year(body.date_text))
    db.add(e)
    db.commit()
    return row(e)


@router.get("/archivum/versions")
def canon_versions(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [{k: v for k, v in row(x).items() if k != "snapshot"} | {"assertions": len(x.snapshot.get("assertions", []))}
            for x in db.scalars(select(CanonVersion).order_by(CanonVersion.version.desc())).all()]


class VersionIn(BaseModel):
    note: str = Field(min_length=3)


@router.post("/archivum/versions")
def canon_version(body: VersionIn, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    v = canon.new_version(db, body.note, user.email)
    gov.audit(db, user.email, "canon.version", f"canon_version:{v.version}")
    db.commit()
    return {"version": v.version}


# =================================================================== G-sus
@router.get("/gsus/modes")
def gsus_modes(_: User = Depends(current_user)):
    return {"modes": {k: {kk: vv for kk, vv in v.items() if kk != "prompt"} for k, v in gmodes.MODES.items()}, "tones": gmodes.TONES,
            "depths": list(gmodes.DEPTH_TIER), "llm": get_provider().name}


class RunIn(BaseModel):
    objective: str = Field(min_length=3, max_length=4000)
    mode: str = "gsus"
    settings: dict[str, Any] = {}


def _run_out(db: Session, r: GsusRun) -> dict[str, Any]:
    steps = db.scalars(select(GsusStep).where(GsusStep.run_id == r.id).order_by(GsusStep.ordinal)).all()
    calls = db.scalars(select(LLMCall).where(LLMCall.run_id == r.id)).all()
    return {**row(r), "steps": [row(s) for s in steps], "ai_cost_usd": round(sum(c.cost_usd for c in calls), 6), "ai_calls": len(calls)}


@router.post("/gsus/runs")
def gsus_run(body: RunIn, db: Session = Depends(get_db), user: User = Depends(operator)):
    run = gsus.start(db, body.objective, body.mode, body.settings, user.email)
    return _run_out(db, run)


@router.get("/gsus/runs")
def gsus_runs(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [row(r) for r in db.scalars(select(GsusRun).order_by(GsusRun.id.desc()).limit(100)).all()]


@router.get("/gsus/runs/{rid}")
def gsus_get(rid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return _run_out(db, _404(db.get(GsusRun, rid), "run"))


@router.post("/gsus/runs/{rid}/resume")
def gsus_resume(rid: int, db: Session = Depends(get_db), user: User = Depends(operator)):
    r = _404(db.get(GsusRun, rid), "run")
    if r.status != "waiting_for_approval":
        raise HTTPException(409, f"run is {r.status}")
    gsus.resume(db, r)
    return _run_out(db, r)


@router.post("/gsus/runs/{rid}/cancel")
def gsus_cancel(rid: int, db: Session = Depends(get_db), user: User = Depends(operator)):
    r = _404(db.get(GsusRun, rid), "run")
    if r.status in ("completed", "failed", "cancelled"):
        raise HTTPException(409, f"run is {r.status}")
    for s in db.scalars(select(GsusStep).where(GsusStep.run_id == rid)).all():
        if s.status in ("pending", "waiting_for_approval"):
            s.status = "cancelled"
            if s.approval_id:
                a = db.get(Approval, s.approval_id)
                if a and a.status == "pending":
                    gov.decide_approval(db, a, False, user.email, "run cancelled")
    r.status, r.finished_at = "cancelled", datetime.now(UTC)
    gov.audit(db, user.email, "gsus.cancel", f"gsus_run:{rid}")
    db.commit()
    return _run_out(db, r)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    mode: str = "gsus"
    settings: dict[str, Any] = {}
    use_archive: bool = True


@router.post("/gsus/chat/stream")
def gsus_chat(body: ChatIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Streaming conversation in a G-SUS mode. Archive passages (if any) are supplied as untrusted, cited context."""
    from ..security import untrusted

    settings = gmodes.settings_for(body.mode, body.settings)
    provider = get_provider()
    if provider.name == "none" or not hasattr(provider, "stream"):
        raise HTTPException(409, "no streaming-capable AI provider configured (set ANTHROPIC_API_KEY or OLLAMA_BASE_URL)")
    hits = search.search(db, body.message, k=5) if body.use_archive else []
    context = "\n".join(untrusted.wrap(h["text"], str(i + 1), h["title"], h["evidence_label"]) for i, h in enumerate(hits))
    system = gmodes.system_prompt(settings) + " " + untrusted.GUARD
    prompt = body.message + (f"\n\nArchive context (cite as [n]):\n{context}" if context else "")
    tier = gmodes.DEPTH_TIER[settings["depth"]]
    sources = [{"n": i + 1, "title": h["title"], "evidence": h["evidence_label"], "document_id": h["document_id"]} for i, h in enumerate(hits)]

    def gen():
        yield f"event: sources\ndata: {json.dumps(sources)}\n\n"
        status, err, chars = "ok", "", 0
        try:
            for chunk in provider.stream(system=system, prompt=prompt, tier=tier):
                chars += len(chunk)
                yield f"data: {json.dumps({'text': chunk})}\n\n"
        except (LLMUnavailable, LLMRefused) as e:
            status, err = "refused" if isinstance(e, LLMRefused) else "unavailable", str(e)
            yield f"event: error\ndata: {json.dumps({'error': err})}\n\n"
        from ..db import SessionLocal

        s2 = SessionLocal()
        try:
            s2.add(LLMCall(agent_id="gsus", purpose=f"chat:{settings['mode']}", provider=provider.name, model=tier, tier=tier, status=status,
                           error=err or f"streamed {chars} chars; token usage not captured for streams"))
            s2.commit()
        finally:
            s2.close()
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


# =================================================================== Demonkoncernen HQ
DEPARTMENTS: dict[str, dict[str, Any]] = {
    "executive": {"title": "Executive Office", "purpose": "Strategy, goals, planning and oversight", "divisions": ["executive"]},
    "research": {"title": "Research Division", "purpose": "Research agents, source analysis, intelligence, discovery",
                 "divisions": ["research", "opportunity", "commercial", "field_ops"]},
    "development": {"title": "Development Division", "purpose": "Engineering, architecture, testing and releases (Claude Code subagents + CI)",
                    "divisions": []},
    "archive": {"title": "Archive Division", "purpose": "Documents, knowledge, memory and historical research", "divisions": []},
    "creative": {"title": "Creative Division", "purpose": "Writing, design, visual concepts and creative experiments",
                 "divisions": ["brand", "creative_studio", "marketing"]},
    "operations": {"title": "Operations Division", "purpose": "Workflows, integrations, scheduled tasks and system health",
                   "divisions": ["operations", "commerce"]},
    "security": {"title": "Security Division", "purpose": "Access control, threat detection, audit and incidents", "divisions": []},
    "laboratory": {"title": "Laboratory", "purpose": "Experiments, model evaluations and new AI capabilities", "divisions": []},
}


def _dept(db: Session, key: str) -> dict[str, Any]:
    spec = DEPARTMENTS[key]
    since = datetime.now(UTC) - timedelta(days=1)
    agents = db.scalars(select(Agent).where(Agent.division.in_(spec["divisions"]))).all() if spec["divisions"] else []
    ids = [a.id for a in agents]
    tasks = db.scalars(select(Task).where(Task.agent_id.in_(ids)).order_by(Task.id.desc()).limit(15)).all() if ids else []
    alerts = db.scalars(select(Task).where(Task.agent_id.in_(ids), Task.status.in_(("failed", "blocked")), Task.created_at >= since)).all() if ids else []
    metrics: dict[str, Any] = {}
    if key == "executive":
        metrics = {"pending_approvals": db.query(Approval).filter(Approval.status == "pending").count(),
                   "gsus_runs": db.query(GsusRun).count(), "waiting_for_approval": db.query(GsusRun).filter(GsusRun.status == "waiting_for_approval").count()}
    elif key == "archive":
        metrics = {"documents": db.query(Document).count(), "chunks": db.query(DocumentChunk).count(), "entities": db.query(Entity).count(),
                   "canon_works": db.query(CanonWork).count(), "canon_chapters": db.query(CanonChapter).count(),
                   "canon_contradictions": len(canon.contradictions(db)), "memory_items": db.query(MemoryItem).count()}
    elif key == "creative":
        metrics = {"concepts": db.query(BrandConcept).count(), "assets": db.query(CreativeAsset).count()}
    elif key == "operations":
        metrics = {"queued_tasks": db.query(Task).filter(Task.status.in_(("queued", "running"))).count(),
                   "scheduler": gov.get_state(db, "scheduler"), "scheduler_enabled": get_settings().scheduler_enabled}
    elif key == "security":
        metrics = {"audit_events_24h": db.query(AuditLog).filter(AuditLog.created_at >= since).count(),
                   "failed_logins_24h": db.query(AuditLog).filter(AuditLog.action == "auth.login_failed", AuditLog.created_at >= since).count(),
                   "lockouts_24h": db.query(AuditLog).filter(AuditLog.action == "auth.login_locked", AuditLog.created_at >= since).count(),
                   "injection_flagged_documents": _flagged(db),
                   "kill_switch": gov.get_state(db, "kill_switch"), "suspended_agents": db.query(Agent).filter(Agent.status == "suspended").count()}
    elif key == "laboratory":
        runs = gov.get_state(db, "evals").get("runs") or []
        metrics = {"experiments_running": db.query(Experiment).filter(Experiment.status == "running").count(),
                   "providers": get_router().health(), "last_eval": runs[0] if runs else None,
                   "ai_spend_today_usd": round(tracing.spent_today(db), 6)}
    elif key == "development":
        metrics = {"version": "0.3.0", "database": get_settings().database_url.split(":")[0],
                   "dev_agents": "defined in .claude/agents (Claude Code subagents) — see CLAUDE.md",
                   "verification": "scripts/verify.sh runs lint, tests, type check and build"}
    status = "attention" if alerts or (key == "security" and metrics.get("kill_switch", {}).get("engaged")) else "nominal"
    return {"id": key, **{k: v for k, v in spec.items() if k != "divisions"}, "status": status,
            "agents": [{"id": a.id, "name": a.name, "status": a.status, "level": a.permission_level, "ok": a.tasks_succeeded,
                        "failed": a.tasks_failed, "blocked": a.tasks_blocked, "cost_usd": round(a.cost_total_usd, 4)} for a in agents],
            "recent_tasks": [{"id": t.id, "type": t.type, "agent": t.agent_id, "status": t.status, "created_at": t.created_at} for t in tasks],
            "alerts": [{"task_id": t.id, "type": t.type, "agent": t.agent_id, "status": t.status, "error": (t.error or "")[:200]} for t in alerts],
            "metrics": metrics}


@router.get("/hq/departments")
def hq_departments(db: Session = Depends(get_db), _: User = Depends(current_user)):
    build_orchestrator()
    return [_dept(db, k) for k in DEPARTMENTS]


@router.get("/hq/departments/{key}")
def hq_department(key: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    if key not in DEPARTMENTS:
        raise HTTPException(404, "unknown department")
    return _dept(db, key)
