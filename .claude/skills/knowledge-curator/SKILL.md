---
name: knowledge-curator
description: Curate the Archive and Archivum canon — import documents with correct provenance and evidentiary class, detect duplicates/contradictions, and keep sources separate from interpretations. Use when adding or reorganising knowledge.
---
- Every document needs: title, source (and URL if any), author/date when known, and an evidence class
  (historical_fact, primary_source, religious_interpretation, philosophical_theory, scholarly_hypothesis, speculative, fiction_canon).
  If unsure, use `unclassified` — never guess "historical_fact".
- Interpretations go into annotations (`kind=interpretation`) on the source, not into the source text.
- Canon (Archivum) is imported, never generated: `POST /api/archivum/import` with `expected` counts to validate structure.
- After imports run `GET /api/archivum/contradictions` and the retrieval eval (`POST /api/ai/evals/run`).
- Never fabricate quotations or references; if a source cannot be verified, mark it `speculative` and say why.
