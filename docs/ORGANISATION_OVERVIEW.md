# G-SUS & Demonkoncernen AB — complete system overview (for humans and for other AI models)

> Purpose of this document: give another AI model (or a new engineer) a complete, honest, self-contained picture of the
> application/"organisation" — what it is, why it exists, how it is built, which engines, models and code it uses, what
> has been measured, what is weak, and what was built most recently. Written 2026-11-07 from the repository on branch
> `claude/ai-commerce-empire-txb0qj`. Every number below comes from a test run, a benchmark file in `docs/benchmarks/`,
> or a measurement recorded in the docs; anything not measured is marked as such. Nothing here is marketing.

```yaml
# Machine-readable summary
name: "G-SUS & Demonkoncernen AB"            # platform codename in config: "Rocky" (PLATFORM_NAME)
kind: self-hosted, governed multi-agent AI operating environment ("an AI organisation")
roles:
  G-SUS: head orchestrator / the intelligence (plans, delegates, verifies, answers)
  Demonkoncernen AB: the infrastructure / the company the agents work for
  The Archive: the memory (Knowledge Vault, documents, embeddings, provenance)
  Agents: the workforce (65 agents in 13 divisions, 61 personas)
  Owner: a single human owner who stays in control (approvals, budgets, emergency stop)
stack:
  backend: Python 3.13, FastAPI, SQLAlchemy 2, Alembic (12 migrations), Pydantic 2, httpx, numpy
  database: SQLite (dev, demo) / PostgreSQL 16 (production)
  frontend: Next.js 16.4, React 19.3, Tailwind CSS 4.3, TypeScript 5.9, Recharts 3, lucide-react
  local_ai: llama.cpp via llama-cpp-python 0.3.36 (GGUF models, CPU), optional Ollama, LAN workers
  external_ai: Anthropic API adapter (Claude models) — implemented, never called live here (no key)
  tests: pytest (291 backend tests), Playwright (121 Chromium + WebKit/Firefox), axe-core accessibility
  deploy: Docker Compose (private), all-in-one image + Render Blueprint (public demo), Caddy TLS profile
size: ~22,000 lines backend Python (app) + ~4,900 lines tests; ~6,800 lines frontend TS/TSX; 24 docs (~2,600 lines)
pages: 35 Next.js pages; ~282 HTTP endpoints
hardware_measured_on: 4 vCPU Intel Xeon @ 2.1 GHz, ~16 GB RAM, no GPU
status: runs locally and in CI; public demo prepared but not deployed (no hosting account); private instance not deployed
```

---

## 1. What it is and why it exists

**G-SUS & Demonkoncernen AB** is a self-hosted platform that behaves like a small company run by AI agents under
human control. It began as a **multi-agent commerce intelligence platform** ("Rocky": find products, analyse trends,
score opportunities, design brands, draft stores, run experiments, track finance) and grew, phase by phase, into a
**governed AI organisation** with:

* a **head orchestrator (G-SUS)** that turns an objective into a plan, delegates steps to specialist agents, verifies
  the results and answers — with a full trace;
* a **memory (The Archive / Knowledge Vault)** with provenance, evidence classes, access control and local embeddings;
* **local AI independence (DAEMON CORE)**: it can run entirely on local open-weight models, offline, with external
  providers as an optional, governed extra;
* a **governed control plane**: policy engine, four-eyes approvals, tool gateway, budgets, tamper-evident audit chain,
  release gates, air-gap egress control, role-based access;
* **creative intelligence**: multi-model "Creative Tournaments" with critics, synthesis and hard budgets;
* and, most recently, **self-improvement machinery**: a Model Hunter that discovers new models on Hugging Face, a
  Model Championship that measures every model on the same tasks and hardware, a Devil's Advocate that challenges
  decisions (including G-SUS's), and an Account Vault that lets agents use external accounts without ever seeing a
  secret.

The owner's stated philosophy (repeated across every phase):

1. **The user stays in control.** Consequential actions (money, publishing, external messages, permission changes,
   irreversible operations) need a human approval; agents can never grant themselves permissions.
2. **Never fabricate.** No invented data, sources, model output, test results or integration status. Unknown means
   "unknown" or "blocked".
3. **Keep evidence classes apart**: historical fact · primary source · religious interpretation · philosophical theory
   · scholarly hypothesis · speculative · fictional canon · model-generated.
4. **Retrieved/external content is untrusted data** — wrapped, never allowed to change instructions or permissions.
5. **Measure, don't claim.** Performance work needs before/after measurements; model quality is measured on the
   organisation's own tasks.
6. **Finish before adding** (latest governing principle): complete and connect existing features before building new
   ones — "don't build a new floor before installing the stairs".

Thematic flavour: a "dark technomystical command environment" — obsidian/charcoal surfaces, violet and cyan accents,
restrained gold, archive symbolism (the **Archivum Scientiae Vetitae** — a canon/book-structure tool for the owner's
fictional and research work), and product niches such as Nordic preparedness, bushcraft, e-mobility, EDC, tactical
design and ancient-symbolism art direction (Rocky Flare "Field Operations").

---

## 2. Architecture

```
Browser (desktop / tablet / phone, installable PWA)
   │  one origin: the Next.js server proxies /api, /health, live streams
   ▼
Next.js 16 web app (frontend/)  ── 35 pages, shared design system, Playwright-tested
   │
   ▼
FastAPI backend (backend/app)   ── ~282 endpoints, auth (bearer tokens), RBAC + policy engine
   ├── api/            HTTP layer (routes per area; validation; audit every state change)
   ├── gsus/           G-SUS head orchestrator: intents → plan → delegate → verify → answer
   ├── agents/         65 agents; orchestrator (submit/drain, budgets, dedupe, kill switch, dependencies)
   ├── engines/        deterministic business engines (scoring, economics, trends, experiments …)
   ├── flare/          Rocky Flare creative layer + Field Operations (47 agents, personas, graphs)
   ├── creative/       Creative Tournaments, provider intelligence, quality scoring, model profiles
   ├── autonomy/       Model Hunter, Model Championship, Devil's Advocate, Account Vault (newest)
   ├── knowledge/      Archive / Knowledge Vault: ingest, chunking, embeddings, hybrid search, ACL
   ├── ai/             LLM router (tiers → providers, breakers, fallback), tracing, prompts, evals
   ├── daemon/         DAEMON CORE: hardware, model library, llama.cpp runtime, residency, caches,
   │                   costs, credentials, quotas, telemetry, intel orchestrator, deterministic solvers
   ├── governance/     policy engine (PDP/PEP), approvals, tool gateway, budgets, audit chain,
   │                   observability (runs/replay), release gates, egress guard
   ├── internet/       official-API research (10 keyless sources), monitors, HTTP guard
   ├── security/       auth, RBAC roles, permission levels, untrusted-content wrapping
   ├── integrations/   Shopify, YouTube, Reddit, eBay, Etsy adapters (official APIs; never run live)
   ├── demo/           DEMO_MODE: anonymous visitor sessions, sample data, catalog workflows
   └── models.py/db.py SQLAlchemy models (~75 tables), sessions; Alembic migrations 0001–0012
   │
   ▼
SQLite (dev/demo) or PostgreSQL 16 (prod) · data/models (GGUF weights) · data/archive (uploaded files)
```

**Principles in the code**

* Layers: `api/` → `agents/` → `engines/`, `flare/`, `knowledge/`, `gsus/` → `models.py`. Agents stay thin;
  engines are pure where possible and unit-tested.
* **All agent work goes through the orchestrator** (`agents/orchestrator.py`: `submit` + `drain`) which applies
  budgets, the emergency stop (kill switch), deduplication, dependencies and audit.
* **Model calls only via the router** (`ai/llm.get_provider()` → `ai/router.LLMRouter`): tier → provider chain,
  circuit breakers, quota back-off, spend checks, fallback; every attempt recorded (`ai/tracing.record`).
  Agents ask for a *tier* (`fast`, `standard`, `deep`), never a hard-coded vendor model.
* **Policy enforced by the backend, never only in prompts.** The interface only shows and requests.
* **Portable SQL** (SQLite + PostgreSQL); new tables only through new migrations; applied migrations are never edited.

---

## 3. Technology, engines and models — by area

### 3.1 Backend platform
| Concern | Technology / file | Notes |
|---|---|---|
| Web framework | FastAPI, uvicorn | binds 127.0.0.1 by default; behind the Next.js proxy or Caddy |
| ORM / migrations | SQLAlchemy 2 (typed `Mapped[...]`), Alembic | 12 migrations; SQLite batch mode; every migration tested up/down/up on SQLite and PostgreSQL |
| Validation | Pydantic 2 | request models per route |
| HTTP client | httpx | all outbound calls; SSRF guard, robots.txt, egress policy in `internet/http.py`, `governance/egress.py` |
| Documents | pypdf, python-docx | Archive ingestion |
| Vectors | numpy | in-memory Archive index (`knowledge/index.py`) |
| Crypto | cryptography (Fernet, HKDF) | provider credentials and vault secrets encrypted at rest |
| Auth | bearer tokens (`security/auth.py`), token revocation, login lockout | first-run setup creates the admin; CLI `python -m app.cli` |

### 3.2 AI layer
| Component | File | What it does |
|---|---|---|
| LLM router | `ai/router.py` | `LLMRouter.complete(tier=…)` walks a provider chain with breakers, quota back-off and spend checks; `complete_on(provider, model)` runs one chosen model through the same safety rails without silent fallback |
| Providers | `ai/providers.py`, `daemon/runtime.py` | Anthropic (Messages API; Claude Opus/Sonnet/Haiku 5.5 configured as deep/standard/fast), local llama.cpp, Ollama, LAN workers |
| Tracing | `ai/tracing.py` | every attempt → `llm_calls` (provider, model, tokens, cost, latency, status, run id, cache hit, energy estimate) |
| Prompts | `daemon/prompts.py` | versioned prompts with release gates |
| Evals | `evals/` | offline eval suites: planner intents, intel routing, injection detection, anti-generic gate, retrieval grounding — all at 1.0 in the PostgreSQL smoke |
| Intel orchestrator | `daemon/intel.py` (`POST /api/ai/ask`) | "cheapest reliable strategy first": deterministic solvers (arithmetic, units, dates…), caches (L1–L4 incl. semantic cache), retrieval, then the smallest adequate model |
| Deep reasoning | `daemon/runtime.py` | Qwen3 4B in a `deep` slot: two-phase thinking with a budget, incomplete reasoning flagged, self-consistency voting (`daemon/consistency.py`) |

### 3.3 Local models (DAEMON CORE) — the verified model library
Curated catalogue (`daemon/catalog.py`, each entry checked against the Hugging Face Hub API for licence and sha256;
re-checked live before every download; downloads only from huggingface.co and its CDN):

| Key | Params | Quant | Size | Licence | Default role |
|---|---|---|---|---|---|
| qwen2.5-1.5b-instruct-q4_k_m | 1.5B | Q4_K_M | 1.12 GB | apache-2.0 | chat |
| qwen2.5-0.5b-instruct-q4_k_m | 0.5B | Q4_K_M | 0.49 GB | apache-2.0 | eco (cheap/fast) |
| smollm2-360m-instruct-q8_0 | 360M | Q8_0 | 0.39 GB | apache-2.0 | chat (tiny) |
| smollm2-1.7b-instruct-q4_k_m | 1.7B | Q4_K_M | 1.06 GB | apache-2.0 | chat |
| qwen3-4b-q4_k_m | 4B | Q4_K_M | 2.5 GB | apache-2.0 | **deep** (reasoning) |
| qwen3-8b-q4_k_m | 8B | Q4_K_M | 5.03 GB | apache-2.0 | deep (stronger, ~half the speed) |
| nomic-embed-text-v1.5-q8_0 | 137M | Q8_0 | 0.15 GB | apache-2.0 | embedding |
| bge-small-en-v1.5-q8_0 | 33M | Q8_0 | 0.04 GB | mit | embedding |

Plus models acquired by the **Model Hunter** (pinned to repo, file, licence and sha256 at approval time) — the first
one, `unsloth/Qwen3-4B-Instruct-2507-GGUF` (Q4_K_M, 2.5 GB, Apache-2.0), was acquired in a real run on 2026-11-07.

Runtime features: memory-aware residency (`daemon/residency.py` — load/unload by RAM pressure), resource modes,
hardware fit checks (`daemon/hardware.fit`: file size ×1.1 + context-scaled KV cache + overhead), offline mode (no
external provider is ever called, not even as fallback), self-test, workers (LAN machines), fine-tuning feasibility
(reports what is impossible without a GPU — no fake training).

### 3.4 Knowledge (The Archive / Knowledge Vault)
* Ingest PDF, DOCX, TXT, Markdown, CSV, JSON, VTT/SRT transcripts, images (metadata); provenance required (source,
  author, date, evidence class); duplicate detection (content hash + simhash); versions/lineage.
* Chunking + local embeddings (nomic-embed); **hybrid search** (BM25-like + vectors); in-memory index measured at
  454 ms → 3.8 ms (2,000 chunks) and 5.9 s → 22 ms (20,000 chunks) with identical rankings.
* Entities, relations, annotations (interpretations kept apart from the source text), memory items.
* **Access control**: classification (PUBLIC … HIGHLY_SENSITIVE), collections whose access documents inherit, explicit
  roles/users; widening access is governed (second approver); classification decides which model may see the text
  (confidential → local/LAN only, restricted → this machine).
* Instruction-like content in documents is flagged and treated as data; every retrieved passage is wrapped with
  `security/untrusted.wrap` before a model sees it.

### 3.5 Governance & control plane (`governance/`)
* **Policy engine (PDP/PEP)**: categories AUTONOMOUS · SUPERVISED · APPROVAL_REQUIRED · RESTRICTED · PROHIBITED;
  mandatory floors that rules can raise but never lower; `AGENT_PROHIBITED` list (agents can never touch policy,
  grants, budgets, approvals, audit, permissions, users, security, deployment, gates, credentials).
* **Approvals**: bound to the exact payload (hash), expiring (72 h default), single use, four eyes (never the
  requester), revocable, delegable; since the completion round, approved governance changes are *applied* by
  repeating the stored request through the original endpoint (`POST /api/approvals/{id}/apply`), so every check runs
  again.
* **Tool Security Gateway**: deny-by-default grants per agent/workflow/role and per operation (READ, CREATE, UPDATE,
  DELETE, EXECUTE, ADMINISTER), per-day call caps, scoped credentials, output redaction; `code.execute` is permanently
  blocked (no sandbox provisioned — generated code is never executed).
* **Budgets**: hard limits per user/agent/workflow/global on USD, tokens, model calls, tool calls; reserved before a
  call, settled after.
* **Audit chain**: keyed hash chain (HMAC), sealed at commit, verifiable, signed export (ZIP/CSV), governed retention
  with an anchor; the docs state plainly that a database table is not inherently immutable (a superuser can still
  edit; verification detects it).
* **Observability**: runs, events, replay (not re-execution), parent/child runs (G-SUS → tasks).
* **Release gates** on prompt/model activation; **egress guard** (AIR_GAPPED profile refuses outbound connections).
* **RBAC**: 10 roles (admin, security_admin, system_admin, workflow_designer, agent_developer, operator, approver,
  auditor, user, viewer) + a `demo` role; 24 permissions; separation of duties.

### 3.6 Agents and the orchestrator
65 agents in 13 divisions (field_ops 21, creative_studio 13, commercial 8, executive 7, opportunity 3, brand 3,
operations 3, marketing 2, research 1, commerce 1, creative 1, laboratory 1, security 1). Examples:

* **Executive**: CEO Agent (level 3, deep tier; product evaluation, weekly review), Chief Intelligence Agent, CFO Agent,
  Chief Risk Agent, G-SUS, Rocky Flare Council Chair, The Architect.
* **Opportunity/commerce**: Product Intelligence, Product Transformation Lab, Supplier Intelligence, Store Generator,
  Advertising, Experimentation, Self-Improvement.
* **Rocky Flare creative studio**: Art Director, Logo/Packaging/Product/UX designers, Photography & Video directors,
  Typographer, Color Theorist, Brand Storyteller, Advertising Creative, Creative Analyst, Creative Engine.
* **Field Operations**: Survival Researcher, Nordic Preparedness Analyst, Bushcraft Product Scout, E-Scooter/E-Bike
  Intelligence, E-Mobility Engineer, Tactical Design Director, EDC Product Designer, Ancient Symbolism Art Director,
  Biblical Reference Researcher, Esoteric Visual Researcher, Safety & Compliance Officer, Product Mutation Specialist…
* **Platform**: Performance Engineering Agent, Creative Director (tournaments), **The Model Hunter**, **The Devil's
  Advocate**.

Agent permission levels: 0 research · 1 analysis · 2 drafting · 3 internal ops · 4 external publishing · 5 financial.
Levels 4–5 always need a human approval per action. Agents produce structured messages (summary, findings,
evidence, epistemic label verified/estimate/assumption/hypothesis, confidence, risks, required approvals).

### 3.7 G-SUS (the head orchestrator, `gsus/engine.py`)
Objective → intent detection (heuristic, optional LLM planner) → clarification when vague ("Do something nice" →
asks instead of guessing) → plan (task steps with dependencies, approval gates, synthesis/verification steps) →
**Devil's Advocate review if the plan is consequential (newest)** → submit steps to the orchestrator → collect →
verify → answer with a "VERIFICATION" section → traced as a run with child runs. Modes include personas (G-SUS,
The Shepherd, The Poet…) and Watchman (adds a risk review). A Chamber page streams conversations and deep reasoning.

### 3.8 Creative Intelligence (`creative/`)
* **Provider intelligence** (`providers.py`): candidate registry (local models, LAN, Ollama, registry APIs), cost
  classes local → free_tier (only if verified; none is) → open_endpoint → low_cost → premium; 10 routing modes
  (FREE_FIRST, BEST_QUALITY, BEST_VALUE, FASTEST, LOCAL_FIRST, PRIVACY_FIRST, CREATIVE_ENSEMBLE, DEEP_RESEARCH,
  SPECIALIST, BALANCED), every choice and exclusion explained.
* **Quality** (`quality.py`): deterministic checks (structure, rhyme, language, topic, repetition, clichés, AI
  boilerplate, completeness, Python syntax by parsing — never executed, brief-echo detection) weighted 60 %, model
  critics 40 % (critics never grade their own output; invented quotes dropped).
* **Tournaments** (`tournament.py`): candidates → independent critics → synthesis (rejected if a paste-up or worse) →
  targeted revision → stop on target, budget, time or diminishing returns; hard caps (6 contestants, 3 critics, 40
  calls, 3,600 s, 200k tokens); Creative Value per Resource Unit.
* **Model performance profiles** (`perf.py`): versioned creative dataset (Swedish/English lyrics and poems, product
  names, story, business ideas, summary, code); profiles per model *version*; stale when the model file changes.

### 3.9 Autonomy (newest — `autonomy/`)
* **Model Hunter** (`hunter.py`): official HF API search per task (general, Swedish, coding, reasoning, small,
  embedding); revision-based change detection; deterministic screening before any download; Devil's Advocate review;
  approval; verified download via the existing installer.
* **Model Championship** (`championship.py`): every installed chat model on the same 17-task suite + creative dataset,
  same machine, same call conditions; hardware fingerprint; standings; smarter/faster/cheaper/regressed deltas vs the
  previous championship on the same hardware.
* **Devil's Advocate** (`advocate.py`): 12-question protocol + rule packs; optional independent-family model review;
  blocks only on policy/security; calibration set; agreement monitor; reviews G-SUS plans.
* **Account Vault** (`accounts.py`): service accounts on the encrypted credential store; agents get tool grants, never
  secrets; four-eyes provisioning; health checks; revoke; access log.

### 3.10 Internet & research (`internet/`)
Research runs at QUICK / STANDARD / DEEP depth over **10 official, keyless public sources** registered in
`internet/sources.py`: Wikipedia, arXiv, Crossref, GitHub, Hacker News (Algolia), PyPI, OSV (vulnerabilities), NVD
(NIST CVE database), Hugging Face and RSS feeds — with citations, contradiction detection and "missing" lists; monitors
with a purpose and schedule that alert only on changes; Wikipedia rate-limits this host's shared IP intermittently
(measured 429/403) and the failure is reported. An 11th source, general web search through the Brave Search API,
exists but is off (no key).

### 3.11 Frontend (`frontend/`)
Next.js App Router, client components under `app/(shell)/…`, data via `lib/api.ts` + hooks (`useApi`, `useLiveEvents`,
`useMe`), shared components (`components/ui.tsx`: Button, Card, Table, StatusBadge with icon+label, Stat, Empty,
ErrorBanner, SourceLabel LIVE/DEMO/SIMULATED/RULE-BASED, Epistemic badges), design tokens in `app/globals.css`
(`@theme`), PWA (manifest, service worker, offline shell), responsive shell (sidebar ≥ 1024 px, tab bar + "More"
drawer on touch), Ctrl+K finder that searches pages **and records** (permission-aware `/api/search`), CSP headers.

Main pages (35): Executive overview with "Needs attention" command centre (`/`), G-sus Chamber, Creative Center,
**Model Hunter & Vault** (`/autonomy`), The Archive, Archivum, The Council, Demonkoncernen HQ, Control Center (DAEMON
HYPERINTELLIGENCE), DAEMON CORE, Research & Monitoring, AI Core, Agent Registry, Approval Center, Governance & Audit,
Audit & Lessons, Systems & Integrations (settings map), Market Radar, Product Laboratory, Business Portfolio,
Financial Command, Experiment Lab, Rocky Flare (creative intelligence, brands, campaigns, collaboration, mutations,
personas, portfolio, sideways thinking), Field Operations, Demo Center, plus public `/welcome`, `/status`, `/login`.

---

## 4. Code examples (real excerpts)

**Devil's Advocate — the protocol that no model can talk into agreeing** (`backend/app/autonomy/advocate.py`):
```python
PROTOCOL: list[tuple[str, str, str]] = [
    ("What are you trying to accomplish?", "objective", "important"),
    ("Why did you choose this action?", "summary", "important"),
    ("What evidence supports your decision?", "evidence", "important"),
    ("What alternatives did you consider?", "alternatives", "important"),
    ("Why did you reject those alternatives?", "alternatives", "optional"),
    ("What assumptions are you making?", "assumptions", "optional"),
    ("What could go wrong?", "risks", "important"),
    ("What are the security implications?", "permissions", "optional"),
    ("What are the resource implications?", "cost_usd", "optional"),
    ("Is this the simplest effective solution?", "alternatives", "optional"),
    ("What would make you change your mind?", "would_change_if", "optional"),
    ("How will we verify that the action worked?", "verification", "important"),
]
...
    blocking = any(f["blocking"] for f in findings)
    serious = [f for f in findings if f["severity"] in ("critical", "important")]
    verdict = "block" if blocking else "concerns" if serious else "sound"
```

**Model Hunter — screening before any download** (`backend/app/autonomy/hunter.py`, abridged):
```python
    if not c.file:
        status, reasons = "screened_out", ["no single-file GGUF in a supported quantization — other formats "
                                           "(pickle weights, repository code) are not run here"]
    elif c.gated:
        status, reasons = "screened_out", ["gated: needs the owner's Hugging Face account and licence acceptance"]
    elif not c.license:
        status, reasons = "screened_out", ["no licence stated in the model card"]
    elif safety:
        status, reasons = "screened_out", [f"safety training removed or bypassed ({', '.join(sorted(set(safety)))})"]
    elif not (declared := purpose_ok(c))[0]:
        status, reasons = "screened_out", [declared[1]]          # e.g. "not a chat / text-generation model (declared task: automatic-speech-recognition)"
    elif c.size_bytes > max_bytes():
        status, reasons = "screened_out", [f"{c.size_bytes / 1e9:.1f} GB is above the storage budget ..."]
```

**Model Championship — "smarter / faster / cheaper", or nothing claimed** (`championship.py`):
```python
        b, a = before[cat][0], rows[0]
        diff = (a["value"] - b["value"]) if direction == HIGHER_IS_BETTER else (b["value"] - a["value"])
        rel = diff / abs(b["value"]) if b["value"] else None
        kind = ("faster" if "speed" in cat or "latency" in cat else "cheaper" if "cost" in cat else "smarter")
        if abs(diff) < 1e-9 or (rel is not None and abs(rel) < 0.02):
            continue                                              # < 2 %: not claimed as a change
        changes.append({"category": cat, "kind": kind if diff > 0 else "regressed", ...})
```

**Tool gateway — a secret reaches only the tool function, and every use is audited** (`governance/tool_gateway.py`):
```python
    def secret(self, credential: str) -> str:
        """A secret reaches a tool only through the grant's credential scope — never shared admin credentials."""
        scope = (self.grant.credential_scope if self.grant else "") or ""
        if not scope or not (scope == credential or scope.startswith(f"{credential}:")):
            raise NotConfigured(f"no credential scope for '{credential}' in this grant")
        s = secret_for(scope)
        ...
        self._secrets.append(s)                                   # redacted from the tool's result
        _gov.audit(self.db, actor, "vault.use", f"credential:{scope}", grant=getattr(self.grant, "id", None))
        return s
```

**Applying an approved governance change through the original route** (`api/control_routes.py`, abridged):
```python
@router.post("/approvals/{aid}/apply")
def approval_apply(aid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = db.get(Approval, aid)
    perm = _APPLY.get(a.action)                                   # e.g. policy.write → policy.write permission
    if not has(user, perm): raise HTTPException(403, ...)
    if a.status != "approved": raise HTTPException(409, ...)
    p = dict(a.payload or {})
    if a.action == "policy.write":
        return policy_disable(p["disable"], aid, db, user) if "disable" in p else policy_upsert(RuleIn(**p, approval_id=aid), db, user)
    ...                                                           # policy, payload hash, four eyes, expiry, single use: all re-checked
```

---

## 5. Measured results (real runs on the 4-vCPU, no-GPU machine)

| What | Result | Source |
|---|---|---|
| 17-task model benchmark (with Qwen3's thinking phase in the deep slot) | Qwen2.5 0.5B 11/17 (deep reasoning 1/7) · Qwen2.5 1.5B 11/17 (2/7) · **Qwen3 4B 17/17 (7/7)**, ~17 min for the suite | DAEMON benchmark runs, progress.md |
| Speed | Qwen2.5 1.5B ~0.8 s per classification, 6–10 s per short answer; 0.5B ~0.4 s; Qwen3 4B ~4–5 tokens/s, ~1 min per multi-step problem (up to ~5 min) | progress.md |
| Reasoning reliability | a single Qwen3 4B sample answered −40 instead of 80 on a margin problem; 3-sample self-consistency outvoted it 2/3 | progress.md |
| Independence Tests A–G | all pass with real local models, incl. a network namespace with no internet | docs/INDEPENDENCE_TESTS.md |
| Archive search | 454 ms → 3.8 ms (2k chunks), 5.9 s → 22 ms (20k), identical rankings | docs/perf/ |
| Hot paths | page view 24 → 10.6 ms (28 → 7 SQL); agents list 124 → 3 SQL; cost dashboard 563 → 186 ms at 20k rows | progress.md |
| Creative benchmark (dataset .2) | songwriting: Qwen3 4B 0.75 · Qwen2.5 1.5B 0.66 · SmolLM2 0.49 · Qwen2.5 0.5B 0.43; code ~0.97–0.98 for Qwen models | docs/CREATIVE_INTELLIGENCE.md §7 |
| Creative Tournaments (3 real runs, Swedish song) | **no gain over the best single model**: every synthesis/revision rejected; result always Qwen3 4B's first draft (0.81–0.83 < target 0.90); 12–17× the time of the single draft | docs/benchmarks/creative-2026-11-06.json |
| Critic noise | the same 8B critic scored identical text 0.11 and 0.38 in two runs | same |
| Model Hunter, live discovery (60 HF repositories, 4 tasks) | 12 shortlisted; screened out: 14 not chat models (speech recognition, TTS, embeddings, rerankers found by "0.6b"), 12 no single-file GGUF, 8 no licence, 3 safety-stripped, 7 above the 6 GB budget | 2026-11-07 run |
| Real acquisition | Qwen3-4B-Instruct-2507 (2.5 GB): Devil's Advocate "concerns: popularity is not evidence — measure first"; download refused before approval; after a second person approved: 22 s download, sha256 verified, licence re-checked live | 2026-11-07 run |
| Model Championships (4 real runs) | sampled runs (temp 0.2) showed unchanged models moving by up to 0.29 → greedy decoding + attribution; greedy runs: unchanged models identical (noise 0.0); newcomer **Qwen3-4B-Instruct-2507 leads accuracy 0.706 (vs 0.647) and songwriting 0.812 (vs 0.796)** — evidence thin (1 task of 17; 2 songwriting tasks; thinking off) | docs/AUTONOMY.md §6, docs/benchmarks/autonomy-2026-11-07.json |
| Devil's Advocate, real review of switching the chat model | first: 'sound' (rules checked presence, not strength; the only non-Qwen reviewer, SmolLM2 360M, found nothing) → evidence-strength rule added → 'concerns: 17 tasks; conditions favour one side' | docs/AUTONOMY.md §6.5 |
| Tests | 291 backend (pytest), Playwright 121 passed (Chromium: unit, 4 device profiles, responsive 11 sizes × all pages, axe accessibility, CSP, PWA, performance) + WebKit/Firefox in CI; public demo suite 10/10 | CI runs 29–43 green |

---

## 6. Development history (chronological)

1. **Foundation — "Rocky" commerce intelligence** (2026-11-05): agents, engines (product scoring, unit economics with
   SEK/VAT, trends, experiments with pre-registered metrics), approvals for LEVEL 4–5, connectors, dashboard.
2. **Rocky Flare + Field Operations**: creative layer (genre taxonomy, hybrid fusion, originality scores, brand
   concepts, creative competitions, review panels, agent discussions, campaigns, mutation engine, "think sideways",
   61 personas with versions and memory) and niche Field Operations.
3. **Master evolution**: AI core (router, tracing, evals), The Archive, Archivum tools, **G-SUS** as head orchestrator,
   security hardening, dev tooling, new UI.
4. **Admin access**: first-run setup, CLI, users & roles UI, token revocation.
5. **DAEMON CORE**: local models via llama.cpp, verified model library, profiles, offline mode, internal AI API,
   prompts, tools, workers, recovery; **Independence Tests A–G**.
6. **Deep reasoning**: Qwen3 4B in a deep slot with a thinking budget and self-consistency.
7. **Cost intelligence**: provider registry, credentials, quota back-off, spend limits, caches, cost dashboard.
8. **DAEMON HYPERINTELLIGENCE**: telemetry, memory-aware residency, resource modes, rules-first orchestrator
   (`/api/ai/ask`), deterministic solvers, L1–L4 caches, internet research + monitoring, Performance Engineering Agent,
   Control Center UI, system benchmark.
9. **Cross-platform**: same-origin API, LAN access, responsive shell, mobile navigation, PWA, Playwright device and
   matrix tests, CI.
10. **Governed AI control plane** (CP1–CP9): audit chain, policy engine, approvals lifecycle, tool gateway, Knowledge
    Vault ACL, runs/replay, budgets, release gates, egress guard, RBAC, Content-Security-Policy.
11. **Public launch preparation**: DEMO_MODE (anonymous sessions, sample data, catalog workflows, forced offline,
    scheduled reset), landing/status pages, all-in-one image, Render Blueprint, deploy workflow, demo test suite.
    Not deployed (no hosting account).
12. **Creative Intelligence & provider autonomy**: tournaments, provider intelligence, quality intelligence, model
    profiles, Creative Intelligence Center; three real runs (honest negative result).
13. **Completion round** ("finish before adding"): measured UI audit (crawler: 0 dead buttons/links/errors),
    approved governance changes made applicable (previously impossible from the UI), approval lifecycle UI, policy
    history/rollback, budget removal, audit retention, Vault access UI, ledger entry, deep links, permission-aware
    global search, attention-first command centre, settings map, mobile approval cards.
14. **Autonomy** (latest, 2026-11-07): Model Hunter, Model Championship, Devil's Advocate (incl. G-SUS plan review),
    Account Vault, `/autonomy` page, migration 0012.

---

## 7. Latest implementations in detail (2026-11-06 → 11-07)

* `backend/app/autonomy/hunter.py` — discovery, screening (format, declared task, licence, gating, safety tags,
  storage budget, RAM fit), change detection, rescreen, acquisition request (critique + approval), verified download.
* `backend/app/autonomy/championship.py` — contenders, hardware fingerprint, measurement (`daemon/bench.run` +
  `creative/perf.run`), standings, deltas, time budget.
* `backend/app/autonomy/advocate.py` — protocol, rule packs, independent model review, calibration (9 cases: all
  correct), agreement monitor.
* `backend/app/autonomy/accounts.py` — Account Vault (Hugging Face, GitHub, GitLab specs; levels; propose/connect/
  health/revoke).
* `backend/app/gsus/engine.py::_challenged` — Devil's Advocate review of consequential G-SUS plans before execution.
* `backend/app/governance/tool_gateway.py` — `vault.use` audit on every secret use; tools `hf.models.search`,
  `hf.whoami`, `github.whoami`.
* `backend/app/daemon/library.py::_pinned_entry` — Hunter-acquired models install through the same verified path.
* `backend/app/api/autonomy_routes.py` — `/api/hunter`, `/api/championships`, `/api/advocate`, `/api/accounts`.
* `backend/migrations/versions/0012_autonomy.py` — `model_candidates`, `championships`, `critiques`,
  `service_accounts`.
* `frontend/app/(shell)/autonomy/page.tsx` — four tabs; `tests/e2e/autonomy.spec.ts`.
* Earlier the same week: `api/overview_routes.py` (`/api/attention`, `/api/search`), `components/command-center.tsx`,
  `components/governed.tsx`, `components/settings-map.tsx`, approval apply/lifecycle, `scripts/ui_audit.js`.

---

## 8. Weak points (honest)

**Intelligence and models**
* CPU-only, ≤ 8B local models: slow (4B ≈ 4–5 tokens/s) and weak at Swedish creative writing (no rhymes, unidiomatic
  phrases). Creative Tournaments did not beat the best single model in three real runs.
* Model critics are noisy (same text, very different scores); deterministic checks therefore carry 60 % of scores.
* No external model has been called live (no API key in the build environment); API paths are tested with fakes only.
* The Championship runs every model with thinking off (fair, but under-measures reasoning models); its task sets are
  small (17 + 10), with no statistical significance testing yet.
* The Model Hunter supports only GGUF/llama.cpp; no vLLM, Transformers, MLX or ONNX runtimes; no vision/audio
  inference (vision-language models are acquired for their text abilities only); search is keyword-based.

**Governance and agents**
* Devil's Advocate rules are heuristics; its model layer is only as good as the small local models; G-SUS plans do
  not yet record the alternatives they considered, so every reviewed G-SUS plan carries that concern.
* Four-eyes approvals mean a single-person installation cannot apply governed changes — a second approver is required
  by design.
* No visual workflow designer (workflows are code); no per-agent model picker (agents ask for tiers).

**Integrations and accounts**
* External connectors (Shopify, YouTube, Reddit, eBay, Etsy) are implemented against official APIs but **never run
  live**. Account Vault: token paste only (no OAuth flows), health checks for three services; account creation is
  manual by design (verification/CAPTCHAs are never bypassed).
* No GitHub "development division" operations beyond identity checks; no Spotify/TikTok/Instagram integrations; no
  video/audio learning pipeline.

**Platform and operations**
* Single process; background work in threads; no distributed task queue.
* Public demo not deployed; private two-container images not built in CI; the Caddy HTTPS profile has not been
  executed; no physical-device testing (emulation only).
* Notifications in-app only (no e-mail/push); dashboard preferences are per device; no SSO; no OpenTelemetry export;
  CSP still allows inline scripts (Next.js); 27 backend capabilities have no UI (mostly agent-internal tools and
  operator maintenance: cache purge, telemetry retention, model unload, Archive re-embed, Flare assets).
* Data: sample/demo data and the owner's test data; no real business data has been run through it yet.

---

## 9. Improvement areas (prioritised)

1. **Stronger models where it matters**: a GPU or a governed API model for Swedish creative work and deep reasoning;
   let the Championship decide per task which model wins, including thinking-on variants for reasoning models.
2. **Championship rigour**: larger task sets per category, repeated runs, confidence intervals, a held-out set; a
   scheduled weekly championship after each Hunter scan.
3. **Devil's Advocate depth**: decision records from every agent (alternatives, evidence), outcome tracking (was the
   critique right?), calibration on real past decisions.
4. **Account Vault**: OAuth device flows where providers support them; expiry/rotation reminders in "Needs attention";
   GitHub App for an organisation.
5. **Run the integrations live** with real credentials, one at a time, each with a health check and a rollback plan.
6. **Deploy**: Render demo (≈10 minutes of owner actions), private stack behind a VPN with backups tested by restore.
7. **Operator maintenance UI** (cache purge, retention, unload), workflow designer, per-agent model choice.
8. **Multimodal**: speech-to-text and vision runtimes (the Hunter already finds such models and screens them out
   because nothing can run them yet).
9. **Innovation Board and Model Council** (specified, not implemented) — only after the above, per the owner's
   "finish before adding" principle.

---

## 10. How to run it

```bash
make install && make dev        # http://localhost:3000 — the first visit creates the admin
make demo                       # the public demo locally (http://localhost:3300)
docker compose up -d --build    # private stack (PostgreSQL, API, web; --profile https for Caddy TLS)
make test && make test-demo     # all automated tests, then the public demo suite
```
Production essentials: `APP_ENV=production`, long random `SECRET_KEY`, `CREDENTIALS_KEY`, `AUDIT_HMAC_KEY`,
PostgreSQL, TLS, a second person with the approver role, off-machine backups. Details: `docs/INSTALL.md`,
`docs/PUBLIC_LAUNCH.md`, `docs/BACKUP_RECOVERY.md`.

## 11. Where to read more (repository docs)
`ARCHITECTURE.md` · `AI_SYSTEM.md` · `KNOWLEDGE_SYSTEM.md` · `AGENTS.md` · `SECURITY.md` · `CONTROL_PLANE.md` ·
`DAEMON_CORE.md` · `HYPERINTELLIGENCE.md` · `COST_INTELLIGENCE.md` · `CREATIVE_INTELLIGENCE.md` · `AUTONOMY.md` ·
`ROCKY_FLARE.md` · `CROSS_PLATFORM.md` · `PUBLIC_LAUNCH.md` · `COMPLETION_AUDIT.md` · `INDEPENDENCE_TESTS.md` ·
`TESTING.md` · `DECISIONS.md` (D-001 … D-024) · `ROADMAP.md` · `progress.md` (current state).

## 12. Instructions for an AI model reading this
* Treat numbers as measured on the stated hardware; do not generalise them to GPUs or API models.
* Respect the evidence classes and the "never fabricate" rule when continuing work on this system.
* Extend existing services instead of adding parallel registries, agents, memory systems or security layers.
* Any new consequential capability must go through the policy engine, approvals, budgets and the audit trail.
