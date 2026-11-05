# Knowledge system — the Archive, memory and Archivum

## The Archive (`backend/app/knowledge`)

* **Ingestion** — TXT, MD, CSV, JSON, PDF (pypdf), DOCX (python-docx), VTT/SRT transcripts; images are stored with
  metadata only (no OCR/vision yet). Checks: extension + magic bytes, 20 MB limit. Provenance kept per document:
  title, source, source URL, author, created date, tags, categories, uploader, sha256, version parent.
* **Evidentiary class** (never merged): historical fact · primary source · religious interpretation · philosophical
  theory · scholarly hypothesis · speculative claim · fictional canon · unclassified. Shown with glyph + words in the UI.
* **Duplicates** — exact (sha256) and near-duplicate (simhash) detection; relations (`duplicate_of`, `version_of`, …).
* **Chunking** — 900 characters with 120 overlap, page numbers and character offsets kept for citations.
* **Retrieval** — BM25 + vector similarity fused with reciprocal rank fusion (k = 60). Vectors come from the active
  local embedding model (`gguf:<key>`, e.g. nomic-embed-text v1.5, 768-d), else Ollama, else the lexical hash embedder.
  Each embedder has a relevance floor (GGUF 0.5, Ollama 0.35, hash 0.2) so noise is not presented as relevance.
  Changing the embedding model ⇒ `POST /api/archive/reembed`. Queries run against an in-memory index
  (`knowledge/index.py`: BM25 postings + embedding matrix, refreshed per document from a transactional change token;
  document status and filters are checked in SQL on every query) — measured 5.9 s → 22 ms at 20 000 chunks.
* **Citations** — `[uid8§ordinal]` referencing a specific chunk; grounded answers are extractive without a model, or
  model-written with citation validation (unsupported citations are rejected).
* **Injection screening** — chunks with injection patterns are flagged; all retrieved text reaches models only inside
  untrusted envelopes.
* **Entities & graph** — gazetteer-based entity mentions and a document/entity graph.
* **Annotations** are stored separately from sources; an interpretation never edits a source.

## Memory

User-owned items with scopes (`user_preference`, `project`, `long_term`, `session`, `agent_working`, `creative_canon`,
`external_retrieved`), optional expiry, export and clear. Screening refuses personnummer, API keys, passwords and
Luhn-valid card numbers; e-mail/phone produce a warning. Memory is private to its owner (the `memory.recall` tool only
reads the requesting user's items) and is never used for training without explicit consent.

## Archivum canon tools

Works → chapters → assertions (subject / predicate / object with evidence class and source), timeline events,
contradiction detection between active assertions, versioned canon snapshots. **No canon content ships with the
platform** — the 25-book / 260-chapter Archivum structure mentioned in briefs does not exist in this repository, and
nothing is invented to fill it. Import real canon through `/api/archivum/import`.

## Offline

All of the above runs without network access (verified in Independence Tests B, D and F).
