# Technical audit — 2026-11-05 (before the "Master System Evolution" phase)

Traced through the full stack (API → orchestrator → engines → DB → UI), not inferred from page names.

## What exists and works (verified by tests and browser runs)

| Area | Reality |
|---|---|
| Stack | FastAPI 0.16x + SQLAlchemy 2 + Alembic (2 migrations), SQLite/PostgreSQL 16; Next.js 16 + React 19 + Tailwind 4 + Recharts |
| Size | ~9.1k lines Python (backend/app), ~2.8k lines TS/TSX, 30 tables, 95 REST endpoints + 1 WebSocket |
| Auth | PBKDF2 passwords, HMAC bearer tokens, roles admin/operator/viewer; admin-only approvals, compliance, persona edits |
| Orchestration | Task registry with dependencies, depth/loop/dedupe guards, retries, timeouts, token budgets, daily cost cap, kill switch, suspension, audit trail, live event bus |
| Agents | 14 commerce agents + Rocky Flare engine/council/persona/commercial agents (≈60), all routed through one orchestrator |
| Engines | Scoring, trends, economics, pricing, business models, compliance (incl. mobility/survival), finance, experiments, genres, originality, mutation, sideways, field, campaigns, learning, portfolio, assets |
| Tests | 74 backend tests (unit + end-to-end API); frontend type-checked and built in CI; browser walkthroughs done manually |
| Security posture | No known vulnerable dependencies (pip-audit, npm audit: 0); approvals for LEVEL 4–5 actions; SVG assets rendered as `<img>` |

## Weaknesses found

| # | Finding | Severity | Evidence |
|---|---|---|---|
| W1 | **AI layer is single-provider** (Anthropic only), no model registry, no per-call tracing, no provider health, no fallback across providers, no circuit breaker, no streaming, no embeddings | High | `app/ai/llm.py` has one adapter and a hard-coded price table; token use is only aggregated per task |
| W2 | **No knowledge system**: no document upload/processing, no full-text or semantic search, no citations, no memory store. The "Intelligence Archive" page only shows audit log, lessons and suppliers | High | no document tables; search = SQL `ILIKE` on products |
| W3 | **No head orchestrator for user objectives**: users must know task-type names; no planning, contradiction detection or final synthesis across tasks | High | `/api/tasks` takes raw `type` strings |
| W4 | **Prompt-injection exposure**: text from external platforms (product descriptions imported by research connectors) is interpolated into LLM prompts without marking it as untrusted | High | `content.generate`, `brand.generate`, `opportunity.generate(enrich)` |
| W5 | **No login rate limiting / lockout**; no security headers | Medium | `/api/auth/login` |
| W6 | No "waiting for approval" task state; approval-gated work cannot resume a workflow | Medium | `TaskStatus` enum |
| W7 | `GET /api/products/{id}` scans the latest 500 tasks in Python to find related ones | Low (perf) | `routes.py:get_product` |
| W8 | No lint/format configuration; ruff reports 195 findings (176 are FastAPI `Depends` false positives, ~19 real: unused imports/variables, zip strictness) | Low | `ruff check` |
| W9 | No Claude Code project instructions, skills, subagents or hooks | Medium (dev velocity) | no `CLAUDE.md`, no `.claude/` |
| W10 | Documentation lives at repo root (7 files); no AI-system, knowledge, design-system, decision or testing docs | Low | repo root |
| W11 | Single in-process worker; `/api/flare/run` executes synchronously inside the request | Medium (scale) | `orchestrator.drain` |
| W12 | The "Archivum" 25-book / 260-chapter structure referenced in the brief **does not exist in this repository** — only Archivum as a genre/brand name | Info | grep |

## Priorities (this phase)

1. **AI core (W1)** — provider adapters behind one interface (Anthropic SDK, Ollama for local models), model registry with metadata, fallback chains, circuit breaker, per-call tracing/usage, health checks, embeddings interface.
2. **Knowledge system (W2, W12)** — documents with provenance and evidentiary class, processing pipeline (TXT/MD/CSV/JSON/PDF/DOCX/transcripts), chunking, BM25 + embedding hybrid retrieval, citations, duplicates, versions, entities, user-controlled memory; Archivum canon tools (books/chapters/assertions/timeline/contradictions) — empty until real canon is imported.
3. **G-sus head orchestrator (W3, W6)** — objective → plan (allowed task types only) → dependency-aware execution → contradiction checks → verification → grounded answer; runs persisted with step states incl. `waiting_for_approval`; creative modes.
4. **Security (W4, W5)** — untrusted-content envelopes + injection heuristics, login rate limiting, security headers, safe uploads.
5. **Dev intelligence (W8, W9, W10)** — CLAUDE.md + scoped rules, skills, subagents, hooks, ruff, verify script, docs/ structure, progress.md.
6. **Interface** — design tokens (obsidian / violet / cyan / antique gold, serif headings), G-sus Chamber, The Archive, Archivum, Demonkoncernen HQ.

Deferred (documented in progress.md): multi-worker queue (W11), external search providers, vision/audio processing, OpenAI adapter.
