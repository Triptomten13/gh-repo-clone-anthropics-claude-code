"""Document processing pipeline: provenance → dedupe/versioning → chunking → embeddings → entity links."""
from __future__ import annotations

import logging

import hashlib
import os
import re
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.providers import LocalHashEmbedder, OllamaProvider, tokenize
from ..models import EVIDENCE_CLASSES, Document, DocumentChunk, DocumentRelation, Entity, EntityMention
from ..security.untrusted import detect
from .extract import Extracted, safe_name

CHUNK_CHARS = 900
OVERLAP = 120
NEAR_DUP_BITS = 3

# Curated gazetteer for the research domains (names only — no claims about them).
GAZETTEER: dict[str, tuple[str, tuple[str, ...]]] = {
    "Babylon": ("place", ()), "Mesopotamia": ("place", ()), "Sumer": ("civilization", ("Sumerians",)), "Akkad": ("civilization", ("Akkadian",)),
    "Assyria": ("civilization", ("Assyrian", "Assyrians")), "Egypt": ("place", ("Egyptian", "Egyptians")), "Rome": ("place", ("Roman", "Romans")),
    "Greece": ("place", ("Greek", "Greeks")), "Persia": ("civilization", ("Persian", "Persians")), "Phoenicia": ("civilization", ("Phoenician",)),
    "Jerusalem": ("place", ()), "Alexandria": ("place", ()), "Nineveh": ("place", ()), "Ur": ("place", ()),
    "Moses": ("person", ()), "Abraham": ("person", ()), "Noah": ("person", ()), "Jesus": ("person", ("Jesus of Nazareth",)),
    "Paul": ("person", ("Paul the Apostle", "Saint Paul")), "Peter": ("person", ("Simon Peter",)), "Enoch": ("person", ()),
    "Hermes Trismegistus": ("person", ()), "Zoroaster": ("person", ("Zarathustra",)), "Nebuchadnezzar": ("person", ("Nebuchadnezzar II",)),
    "Hammurabi": ("person", ()), "Akhenaten": ("person", ()), "Plato": ("person", ()), "Aristotle": ("person", ()), "Pythagoras": ("person", ()),
    "Josephus": ("person", ("Flavius Josephus",)), "Philo of Alexandria": ("person", ()), "Origen": ("person", ()), "Constantine": ("person", ()),
    "Ptolemy": ("person", ()), "Copernicus": ("person", ()), "Kepler": ("person", ()), "Galileo": ("person", ()), "Paracelsus": ("person", ()),
    "Isaac Newton": ("person", ("Newton",)), "John Dee": ("person", ()),
    "Dead Sea Scrolls": ("text", ()), "Nag Hammadi": ("text", ("Nag Hammadi library",)), "Septuagint": ("text", ("LXX",)), "Torah": ("text", ()),
    "Genesis": ("text", ()), "Exodus": ("text", ()), "Revelation": ("text", ("Book of Revelation", "Apocalypse of John")),
    "Book of Enoch": ("text", ("1 Enoch",)), "Epic of Gilgamesh": ("text", ("Gilgamesh",)), "Corpus Hermeticum": ("text", ()),
    "Emerald Tablet": ("text", ()), "Council of Nicaea": ("event", ("Nicaea",)), "Babylonian exile": ("event", ("Babylonian captivity",)),
    "Aramaic": ("language", ()), "Hebrew": ("language", ()), "Coptic": ("language", ()), "Latin": ("language", ()), "Sumerian": ("language", ()),
    "alchemy": ("concept", ("alchemical", "alchemist")), "astrolabe": ("symbol", ()), "Ouroboros": ("symbol", ()),
}

log = logging.getLogger(__name__)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode()).hexdigest()


def simhash(text: str) -> str:
    toks = tokenize(text)
    shingles = [" ".join(toks[i:i + 3]) for i in range(max(1, len(toks) - 2))] or [""]
    v = [0] * 64
    for s in shingles:
        h = int(hashlib.md5(s.encode(), usedforsecurity=False).hexdigest()[:16], 16)
        for i in range(64):
            v[i] += 1 if (h >> i) & 1 else -1
    return f"{sum(1 << i for i in range(64) if v[i] > 0):016x}"


def hamming(a: str, b: str) -> int:
    if not a or not b:
        return 64
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def chunk(text: str, pages: list[tuple[int, int, int]] | None = None) -> list[dict[str, Any]]:
    """Paragraph-aware chunks of ~CHUNK_CHARS with overlap; keeps character offsets and page numbers for citations."""
    out: list[dict[str, Any]] = []
    if not text.strip():
        return out
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + CHUNK_CHARS)
        if end < n:
            cut = max(text.rfind("\n\n", start + CHUNK_CHARS // 2, end), text.rfind(". ", start + CHUNK_CHARS // 2, end))
            if cut > start:
                end = cut + 1
        piece = text[start:end].strip()
        if piece:
            page = next((p for p, s, e in (pages or []) if s <= start <= e), None)
            out.append({"ordinal": len(out), "text": piece, "start_char": start, "end_char": end, "page": page})
        if end >= n:
            break
        start = max(end - OVERLAP, start + 1)
    return out


def embedder() -> tuple[str, Any]:
    """(model_id, embed(texts, kind="document"|"query")). Preference: the DAEMON's local GGUF embedding model,
    then Ollama if configured, then the always-available lexical hash embedder. All three are local."""
    try:
        from ..daemon.runtime import local_embedder

        loc = local_embedder()
        if loc is not None:
            return loc
    except Exception as e:  # pragma: no cover - runtime problems fall back to the next local option
        log.warning("local embedding model unavailable, falling back: %s", e)
    model = os.getenv("OLLAMA_EMBED_MODEL", "").strip()
    if model and os.getenv("OLLAMA_BASE_URL"):
        prov = OllamaProvider()
        return f"ollama:{model}", lambda texts, kind="document": prov.embed(model, texts)
    e = LocalHashEmbedder()
    return e.id, lambda texts, kind="document": e.embed(texts)


def find_entities(text: str) -> dict[str, int]:
    found: dict[str, int] = {}
    for name, (_, aliases) in GAZETTEER.items():
        n = 0
        for term in (name, *aliases):
            n += len(re.findall(r"(?<![\w])" + re.escape(term) + r"(?![\w])", text))
        if n:
            found[name] = n
    return found


def _link_entities(db: Session, doc: Document, text: str) -> None:
    for name, count in find_entities(text).items():
        ent = db.scalars(select(Entity).where(Entity.name == name)).first()
        if ent is None:
            kind, aliases = GAZETTEER[name]
            ent = Entity(name=name, kind=kind, aliases=list(aliases))
            db.add(ent)
            db.flush()
        db.add(EntityMention(entity_id=ent.id, document_id=doc.id, count=count))


def ingest(db: Session, ex: Extracted, meta: dict[str, Any], raw: bytes | None = None, owner_id: int | None = None,
           parent: Document | None = None, archive_dir: str | None = None) -> Document:
    ev = meta.get("evidence_class") or "unclassified"
    if ev not in EVIDENCE_CLASSES:
        raise ValueError(f"evidence_class must be one of {EVIDENCE_CLASSES}")
    h = content_hash(ex.text) if ex.text.strip() else hashlib.sha256(raw or b"").hexdigest()
    sh = simhash(ex.text) if ex.text.strip() else ""
    doc = Document(uid=str(uuid.uuid4()), title=(meta.get("title") or meta.get("filename") or "Untitled")[:512],
                   description=meta.get("description", ""), source=meta.get("source", ""), source_url=meta.get("source_url", ""),
                   author=meta.get("author", ""), created_date=meta.get("created_date", ""), doc_type=ex.doc_type, mime=ex.mime,
                   tags=meta.get("tags", []), categories=meta.get("categories", []), evidence_class=ev, content_hash=h, simhash=sh,
                   size_bytes=len(raw or ex.text.encode()), char_count=len(ex.text), owner_id=owner_id, status="processing",
                   version=(parent.version + 1) if parent else 1, parent_id=parent.id if parent else None,
                   injection_flags=detect(ex.text), error="; ".join(ex.notes))
    db.add(doc)
    db.flush()
    doc.lineage_id = parent.lineage_id if parent else doc.id
    if raw is not None:
        d = Path(archive_dir or os.getenv("ARCHIVE_DIR", "./data/archive"))
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{doc.uid}_{safe_name(meta.get('filename', 'upload'))}"
        path.write_bytes(raw)
        doc.file_path = str(path)
    # exact duplicate → keep the record (provenance) but do not re-index
    dup = db.scalars(select(Document).where(Document.content_hash == h, Document.id != doc.id, Document.status != "duplicate")).first()
    if dup and ex.text.strip():
        doc.status, doc.duplicate_of = "duplicate", dup.id
        db.add(DocumentRelation(source_id=doc.id, target_id=dup.id, relation="duplicates", note="identical normalised content"))
        db.flush()
        return doc
    if sh:
        for other in db.scalars(select(Document).where(Document.id != doc.id, Document.simhash != "", Document.status == "ready")).all():
            if hamming(sh, other.simhash) <= NEAR_DUP_BITS:
                db.add(DocumentRelation(source_id=doc.id, target_id=other.id, relation="duplicates", note=f"near-duplicate (simhash Δ{hamming(sh, other.simhash)})"))
    if parent:
        db.add(DocumentRelation(source_id=doc.id, target_id=parent.id, relation="version_of", note=f"v{doc.version}"))
    pieces = chunk(ex.text, ex.pages)
    model_id, embed = embedder()
    vectors = embed([p["text"] for p in pieces]) if pieces else []
    for p, vec in zip(pieces, vectors, strict=True):
        db.add(DocumentChunk(document_id=doc.id, ordinal=p["ordinal"], text=p["text"], start_char=p["start_char"], end_char=p["end_char"],
                             page=p["page"], embedding=vec, embedding_model=model_id, injection_risk=bool(detect(p["text"]))))
    _link_entities(db, doc, ex.text)
    doc.status = "ready"
    db.flush()
    return doc


def reembed(db: Session) -> int:
    model_id, embed = embedder()
    chunks = db.scalars(select(DocumentChunk).where(DocumentChunk.embedding_model != model_id)).all()
    for i in range(0, len(chunks), 64):
        batch = chunks[i:i + 64]
        for c, v in zip(batch, embed([c.text for c in batch]), strict=True):
            c.embedding, c.embedding_model = v, model_id
    db.flush()
    return len(chunks)
