"""Safe text extraction. Files are parsed as data only — never executed, never opened by path from user input."""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field

MAX_BYTES = 20 * 1024 * 1024
TYPES = {  # extension -> (doc_type, mime)
    ".txt": ("txt", "text/plain"), ".md": ("markdown", "text/markdown"), ".markdown": ("markdown", "text/markdown"),
    ".csv": ("csv", "text/csv"), ".json": ("json", "application/json"), ".pdf": ("pdf", "application/pdf"),
    ".docx": ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ".vtt": ("transcript", "text/vtt"), ".srt": ("transcript", "application/x-subrip"),
    ".png": ("image", "image/png"), ".jpg": ("image", "image/jpeg"), ".jpeg": ("image", "image/jpeg"), ".webp": ("image", "image/webp"),
}
MAGIC = {"pdf": [b"%PDF"], "docx": [b"PK\x03\x04"], "image": [b"\x89PNG", b"\xff\xd8\xff", b"RIFF"]}


class ExtractionError(ValueError):
    pass


@dataclass
class Extracted:
    doc_type: str
    mime: str
    text: str
    pages: list[tuple[int, int, int]] = field(default_factory=list)  # (page_no, start_char, end_char)
    notes: list[str] = field(default_factory=list)


def safe_name(filename: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename.split("/")[-1].split("\\")[-1])[:120]
    return name or "upload"


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ExtractionError("undecodable text")


def extract(filename: str, data: bytes) -> Extracted:
    if len(data) > MAX_BYTES:
        raise ExtractionError(f"file too large ({len(data)} bytes; max {MAX_BYTES})")
    if not data:
        raise ExtractionError("empty file")
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in TYPES:
        raise ExtractionError(f"unsupported file type '{ext or 'none'}' (allowed: {', '.join(sorted(TYPES))})")
    doc_type, mime = TYPES[ext]
    if doc_type in MAGIC and not any(data.startswith(m) for m in MAGIC[doc_type]):
        raise ExtractionError(f"file content does not match its {ext} extension")
    if doc_type in ("txt", "markdown"):
        return Extracted(doc_type, mime, _decode(data))
    if doc_type == "csv":
        rows = list(csv.reader(io.StringIO(_decode(data))))
        if not rows:
            raise ExtractionError("empty csv")
        head = rows[0]
        lines = ["; ".join(f"{h}: {v}" for h, v in zip(head, r, strict=False) if v) for r in rows[1:]]
        return Extracted(doc_type, mime, "\n".join([" | ".join(head), *lines]), notes=[f"{len(rows) - 1} rows"])
    if doc_type == "json":
        try:
            obj = json.loads(_decode(data))
        except json.JSONDecodeError as e:
            raise ExtractionError(f"invalid JSON: {e}") from e
        out: list[str] = []

        def walk(o, path=""):
            if isinstance(o, dict):
                for k, v in o.items():
                    walk(v, f"{path}.{k}" if path else str(k))
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    walk(v, f"{path}[{i}]")
            else:
                out.append(f"{path}: {o}")
        walk(obj)
        return Extracted(doc_type, mime, "\n".join(out))
    if doc_type == "pdf":
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(data))
            parts, pages, pos = [], [], 0
            for i, page in enumerate(reader.pages, start=1):
                t = (page.extract_text() or "").strip()
                pages.append((i, pos, pos + len(t)))
                parts.append(t)
                pos += len(t) + 2
        except Exception as e:  # noqa: BLE001 - malformed PDFs raise many types
            raise ExtractionError(f"unreadable PDF: {type(e).__name__}") from e
        text = "\n\n".join(parts)
        notes = [] if text.strip() else ["no extractable text (scanned PDF?) — OCR is not available"]
        return Extracted(doc_type, mime, text, pages, notes)
    if doc_type == "docx":
        import docx

        try:
            d = docx.Document(io.BytesIO(data))
        except Exception as e:  # noqa: BLE001
            raise ExtractionError(f"unreadable DOCX: {type(e).__name__}") from e
        paras = [p.text for p in d.paragraphs if p.text.strip()]
        for table in d.tables:
            for r in table.rows:
                paras.append(" | ".join(c.text for c in r.cells))
        return Extracted(doc_type, mime, "\n\n".join(paras))
    if doc_type == "transcript":
        lines = []
        for line in _decode(data).splitlines():
            s = line.strip()
            if not s or s == "WEBVTT" or s.isdigit() or "-->" in s or s.startswith(("NOTE", "STYLE")):
                continue
            lines.append(s)
        return Extracted(doc_type, mime, "\n".join(lines))
    # images: stored with metadata only
    return Extracted(doc_type, mime, "", notes=["image stored without OCR/vision analysis (no vision provider configured)"])
