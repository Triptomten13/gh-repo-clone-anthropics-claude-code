"""Archivum Scientiae Vetitae canon tools: import, versioning, contradiction detection, timeline ordering.
Structure only — canon content is imported by its authors, never generated here."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CanonAssertion, CanonChapter, CanonVersion, CanonWork, TimelineEvent


def parse_year(text: str) -> int | None:
    t = text.lower().replace("ca.", "c.").strip()
    m = re.search(r"(\d{1,4})\s*(bce|bc|b\.c\.|f\.?\s?kr)", t)
    if m:
        return -int(m.group(1))
    m = re.search(r"(\d{1,2})(st|nd|rd|th|:e|:a)?\s*(century|århundradet)\s*(bce|bc|f\.?\s?kr)?", t)
    if m:
        c = int(m.group(1))
        return -(c * 100 - 50) if m.group(4) else c * 100 - 50
    m = re.search(r"(\d{1,4})\s*(ce|ad|e\.?\s?kr)", t) or re.search(r"\b(\d{3,4})\b", t)
    return int(m.group(1)) if m else None


def import_structure(db: Session, data: dict[str, Any], expected: dict[str, int] | None = None) -> dict[str, Any]:
    works = chapters = 0
    for w in data.get("works", []):
        row = db.scalars(select(CanonWork).where(CanonWork.number == int(w["number"]))).first()
        if row is None:
            row = CanonWork(number=int(w["number"]), title=w["title"])
            db.add(row)
            db.flush()
            works += 1
        row.title, row.description = w["title"], w.get("description", row.description)
        for c in w.get("chapters", []):
            ch = db.scalars(select(CanonChapter).where(CanonChapter.work_id == row.id, CanonChapter.number == int(c["number"]))).first()
            if ch is None:
                ch = CanonChapter(work_id=row.id, number=int(c["number"]), title=c["title"])
                db.add(ch)
                chapters += 1
            ch.title, ch.summary = c["title"], c.get("summary", ch.summary)
            if "body" in c:
                ch.body = c["body"]
    db.flush()
    totals = {"works": db.query(CanonWork).count(), "chapters": db.query(CanonChapter).count()}
    check = {k: {"expected": v, "actual": totals[k], "ok": totals[k] == v} for k, v in (expected or {}).items() if k in totals}
    return {"created": {"works": works, "chapters": chapters}, "totals": totals, "structure_check": check}


def snapshot(db: Session) -> dict[str, Any]:
    return {"works": [{"number": w.number, "title": w.title, "status": w.status,
                       "chapters": [{"number": c.number, "title": c.title, "status": c.status}
                                    for c in db.scalars(select(CanonChapter).where(CanonChapter.work_id == w.id).order_by(CanonChapter.number))]}
                      for w in db.scalars(select(CanonWork).order_by(CanonWork.number))],
            "assertions": [{"id": a.id, "subject": a.subject, "predicate": a.predicate, "object": a.object, "evidence_class": a.evidence_class}
                           for a in db.scalars(select(CanonAssertion).where(CanonAssertion.status == "active"))]}


def new_version(db: Session, note: str, actor: str) -> CanonVersion:
    last = db.scalars(select(CanonVersion).order_by(CanonVersion.version.desc())).first()
    v = CanonVersion(version=(last.version + 1) if last else 1, note=note, snapshot=snapshot(db), created_by=actor)
    db.add(v)
    db.flush()
    return v


def contradictions(db: Session) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    groups: dict[tuple[str, str], list[CanonAssertion]] = defaultdict(list)
    for a in db.scalars(select(CanonAssertion).where(CanonAssertion.status == "active")).all():
        groups[(a.subject.strip().lower(), a.predicate.strip().lower())].append(a)
    for (subj, pred), items in groups.items():
        objs = {a.object.strip().lower() for a in items}
        if len(objs) > 1:
            classes = {a.evidence_class for a in items}
            kind = "canon_conflict" if classes == {"fiction_canon"} else "canon_vs_source" if "fiction_canon" in classes else "source_disagreement"
            out.append({"type": kind, "subject": subj, "predicate": pred,
                        "values": [{"assertion_id": a.id, "object": a.object, "evidence_class": a.evidence_class, "chapter_id": a.chapter_id,
                                    "source_note": a.source_note} for a in items],
                        "note": {"canon_conflict": "Internal canon disagrees with itself — retire one assertion or reconcile.",
                                 "canon_vs_source": "Canon differs from a historical/scholarly source. Allowed in fiction, but keep it labelled.",
                                 "source_disagreement": "Sources disagree — present both with their evidentiary status."}[kind]})
    by_label: dict[str, list[TimelineEvent]] = defaultdict(list)
    for e in db.scalars(select(TimelineEvent)).all():
        by_label[e.label.strip().lower()].append(e)
    for label, evs in by_label.items():
        years = {e.sort_year for e in evs if e.sort_year is not None}
        if len(years) > 1:
            out.append({"type": "timeline_conflict", "subject": label, "predicate": "date",
                        "values": [{"event_id": e.id, "date_text": e.date_text, "evidence_class": e.evidence_class} for e in evs],
                        "note": "The same event is dated differently."})
    return out
