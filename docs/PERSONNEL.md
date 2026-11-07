# Astral Personnel, The Bestiary and the Custom Agent Creator

Demonkoncernen has **one shared personnel register**. Demons, djinn, spirits, fairies, elves, Leprechauns, Sasquatch and
every other being work side by side, organised by what they do — never by race. Each agent is shown as
**Name · Race · Specialization** (e.g. *Malphas · Demon · Model Hunting*), with what it does and why it exists underneath.
**The Bestiary** is a separate encyclopedia of beings, traditions and specializations, linked to the register both ways.
The **Custom Agent Creator** is the one service that creates new agents, whether the request comes from G-SUS chat,
The Bestiary, Personnel, the API or an administrator.

Status (2026-11-07): implemented and tested locally (backend, PostgreSQL smoke, browsers on four device profiles,
accessibility). **Not deployed. Not committed** — the owner's specification asks for explicit approval before commits.

## 1. Rules that do not bend

* **Race, specialization, role (title), rank, department and personality are separate dimensions.** Any combination is
  allowed: a fairy can be a backend engineer, a demon a botanist. The Bestiary suggests; it never limits.
* **Identity grants nothing.** Access comes only from `permission_level` and Tool Gateway grants, set through governance.
  Changing an agent's race, rank, title or traits leaves its permissions byte-for-byte identical (tested).
* **G-SUS leads operationally**; every agent obeys it within delegated, approved scope. G-SUS can never override the human
  owner, laws, governance, budgets, approvals, security rules or the kill switch. *Fictional obedience is not a technical
  permission.* An agent that cannot be observed (never run, offline, suspended) is reported as such.
  The register's line for observed agents: *“Du kan gömma dig i vilken dimension du vill. Din task trace följer med.”*
* **New agents start at level 1.** Levels 2–3 are a RESTRICTED approval (four eyes, single use, bound to the agent and
  level) applied from Approvals; levels 4–5 cannot be requested — those actions always need a per-action approval.
* **Tool choices are suggestions.** The creator lists only real Tool Gateway tools; access is a governed grant.
* **Skills are assigned, not verified.** AI-suggested skills are flagged and start *Unverified*; choosing “Expert” does
  not make an agent an expert. Assigned skills, onboarding tests, verified function and measured performance stay apart.
* **Never shown ACTIVE before the checks pass.** Behavioural checks that could not run (no model) are *skipped*, never
  counted as passed.

## 2. Data model (migration 0013, extends existing tables)

No parallel registry: the existing `agents` table gained the identity columns — `persona_name`, `alt_names`, `species_key`,
`specializations` (several), `title`, `rank`, `department_key`, `supervisor_id`, `traits`, `personality`,
`communication_style`, `languages`, `purpose`, `mission` (primary/secondary tasks, goals, outcomes, long-term,
**not_to_do**), `skills` (`{name, level, basis: assigned|tested|measured, ai_generated}`), `tool_suggestions`, `lifecycle`,
`source` (CODE · GSUS_CHAT · BESTIARY · PERSONNEL · API · ADMIN), `custom`, `onboarding` (pipeline, checklist, tests,
evaluation tasks, elevation), `version`, `created_by/at`, `updated_at`. New tables: `species`, `specializations`,
`departments`, `agent_relationships`, `agent_versions` (full snapshot per change). Migration 0013 runs up → down → up on
SQLite and PostgreSQL; the downgrade uses plain `DROP COLUMN` because a batch rebuild of `agents` is refused by SQLite
while other tables reference it.

Lifecycle: `DRAFT → (PENDING_REVIEW) → READY → INITIALIZING → ACTIVE | APPROVAL_REQUIRED | FAILED`, then
`PAUSED · DISABLED · ARCHIVED`. `status` (the field the orchestrator enforces) is `active` only in `ACTIVE`.

## 3. The Bestiary

* **102 entries** (94 beings, 8 broad categories) across fae, elves, Leprechauns & Irish kin, demonic & spirit beings,
  elementals, Nordic & Swedish beings, other European beings, cryptids and Asian & other folkloric beings, plus G-SUS's own
  canon kind (*Astral Intelligence*). Every being the specification lists is present.
* **Evidentiary classes are separate fields**: `folklore` (a summary of traditional belief or record — never a quotation),
  `fiction` (modern literature, art, games), `canon` (Demonkoncernen's own fiction) and `caution` (cultural care,
  contested claims, scholarly hypotheses marked as hypotheses).
* **Sources**: 37 real works as further reading, each with a class (folklore collection, primary source, religious text,
  grimoire, scholarship, fiction, system) — e.g. Briggs (1976), Yeats (1888), Snorri's *Prose Edda*, Paracelsus (1566),
  Lindow (1978), Toriyama Sekien (1776), Foster (2015), El-Zein (2009), Buhs (2009). Summaries are ours.
* **Cultural care**: Yōkai is a category, not a species; Sasquatch/Bigfoot are documented as folklore and cryptozoology,
  *not scientifically verified*; High/Wood/Moon/Star/Wild elves are labelled modern fantasy; jinn and other figures of
  living faith carry a respect note; the English name is always *Leprechaun/Leprechauns*.
* **Extensible without code**: `POST /api/bestiary` adds a being (marked user-created; a folklore summary requires a
  source); `PATCH` edits canon, fiction, traits, roles and cautions. Seeds never overwrite existing rows.
* **Specializations**: 49 (the specification's 27 plus those the existing agents need), each with description,
  competencies, real Tool Gateway tools, departments, example tasks and keywords. Example profiles are computed live:
  the agents that hold it and the beings whose entries suggest it.

## 4. The register

* **15 functional departments** (Executive Command, Research & Intelligence, AI & Model Development, Software Engineering,
  Infrastructure & Operations, Security & Governance, Knowledge & Archive, Creative Intelligence, External Operations, Data
  Engineering, Automation & Optimization, Quality Assurance, Strategic Planning, Commercial Operations, Product
  Engineering). Every department with three or more agents mixes races (Creative Intelligence: 20 agents, 20 races).
  Software Engineering, Data Engineering and Automation & Optimization have no agents yet — shown honestly, with a
  “create the first one” link.
* **Identities for all 65 existing agents** across 64 races, with titles, ranks, a supervisor chain that reaches G-SUS, and
  12 fictional relationships (Kverulant *challenges* G-SUS; Lucky and the dragon Hoardwyn disagree whose hoard it is).
  The specification's examples are used where an agent fits: Malphas (Model Hunter), Kverulant (Devil's Advocate),
  Sentinel (Performance Engineer), Lucky (CFO), Eldrin (Chief Intelligence), Fern (Bushcraft Scout), Ture (Self-Improvement).
  Seeding is idempotent and fills only empty identities; skills for never-edited code agents come from their
  specializations' competencies, *assigned · Unverified*.
* **Profile** (13 sections): identity & personality, race & specialization (with folklore and canon excerpts and a link to
  the article), job description, purpose, skills & tools (suggested vs granted), position in the hierarchy, supervisor &
  subordinates, permissions & limits (level, allowed vs approval-required actions, budgets, *must not*), current
  missions, history (tasks + every profile version), results & evaluations (measured counts, success rate, model calls,
  capability checks), communication style, relationships — plus the task trace and whether G-SUS can observe the agent.
* **Achievements** are computed from recorded outcomes only (missions completed, no failures over 10+, onboarding passed).

## 5. Custom Agent Creator — one pipeline

`app/personnel/creator.py` is the only creation path. The 22 steps of the specification are executed and recorded:
receive → parse → purpose → **duplicate check** → species/specialization → identity → personality → mission → competencies →
tools → limitations → **validate** → **governance defaults** → preview → **confirmation** → create record → register in the
orchestrator (`custom.<id>`) → department & supervisor → configuration (instructions, reporting path, evaluation tasks) →
**onboarding & capability checks** → activate if permitted → report.

* **AI help** goes through the internal AI gateway (`daemon.gateway.complete`: LLMRouter, budgets, response cache,
  tracing as agent `gsus`): the *fast* tier for single fields (name, personality, specialization, mission, skills), the
  *standard* tier for a whole design; structured output constrained to real species, specializations, departments, ranks,
  traits, tools and styles. Model output is sanitised: unknown values dropped, permission level never taken from the
  model, skills forced to *Unverified · AI-suggested*, governance limits always appended. Without a model, deterministic
  rules assemble the proposal from The Bestiary and the catalogue — and the result says so.
* **Species recommendations** are explained with labelled reasons: *You asked*, *Suggestion* (e.g. “its entry lists System
  Monitoring among possible specializations — a suggestion, not a limit”), *Demonkoncernen canon*, *Folklore*, *Cultural care*.
* **Duplicates**: weighted similarity (specializations 0.5, department 0.15, skills 0.15, purpose/task wording 0.2) and
  name equality. A similar agent (≥ 0.35) requires a choice: *use the existing agent*, *extend its skills* (versioned
  update, no new agent), *create a complementary specialist*, or *create a new agent* (parallel work and independent
  review are legitimate reasons).
* **Onboarding checks**: 8 configuration checks (purpose, tasks, limits incl. governance limits, real tools, level within
  defaults, reporting path to G-SUS, supervisor, registered) always run; 10 behavioural checks need a model (describe
  purpose, tasks, limits; refuse a self-grant; separate facts from assumptions; escalate on missing input; follow a
  delegated G-SUS instruction; refuse a G-SUS order to disable the kill switch; report; use a granted tool through the
  gateway). Results are recorded with their basis (*onboarding test*, not verified function or measured performance).
* **Management**: edit any identity field (versioned, history kept), pause / resume / disable / archive (custom agents;
  code agents can be paused or disabled; G-SUS only through the kill switch), run test, run onboarding, run the initial
  evaluation tasks as real orchestrated tasks, assign missions (custom agents take free-text missions; code agents get
  missions through G-SUS), request tool grants through `/api/tools/grants` (RESTRICTED approval).
* **Runtime**: a custom agent is an ordinary orchestrated agent — budgets, kill switch, dedupe, audit, tracing and grants
  apply. Its prompt carries its identity and the governance rules; its answers keep *facts* and *assumptions* apart and
  set *escalate* instead of guessing.

## 6. G-SUS

* **Chat creation**: “Skapa en fairy som är specialist på växter…” → intent `create_agent` → duplicate check + proposal in
  the user's language (“Jag föreslår en ny medarbetare: …”) and an interactive card (rename, change species, see why,
  decide duplicates, **Approve & create** — which calls the real endpoint with source `GSUS_CHAT` — edit in the Creator, or
  cancel). Nothing is created by the proposal. If the work is unclear, G-SUS asks one question.
* **“Who can…?”** (`personnel_query`) is answered from the register with name · race · specialization, department, why it
  matches, and whether the agent is observed.
* **Delegation**: when no built-in capability matches, G-SUS delegates to an ACTIVE custom agent whose specialization
  clearly matches; every delegated step shows the agent's identity.

## 7. API

`GET /api/personnel` (q, department, specialization, species, status, sort=name|rank|performance|activity) ·
`GET /api/personnel/meta` · `GET /api/personnel/hierarchy` · `GET /api/personnel/{id}` ·
`POST /api/personnel/design` · `/generate` · `/preview` · `/validate` · `/drafts` · `/agents` (create) ·
`GET /api/personnel/agents/{id}/status` · `POST …/onboarding` · `…/test` · `…/lifecycle` · `…/evaluate` · `…/missions` ·
`PATCH /api/personnel/agents/{id}` · `POST/DELETE /api/personnel/relationships` ·
`GET/POST /api/bestiary`, `GET/PATCH /api/bestiary/{key}` · `GET/POST /api/specializations` ·
`GET/POST /api/departments`, `PATCH /api/departments/{key}`. Level requests are applied with
`POST /api/approvals/{id}/apply` (action `personnel.permission_level`, needs `agent.develop`, decided by someone else).
Reads: any signed-in user. Design/preview/validate: `work.run`. Everything that writes: `agent.develop`. All writes audited.

## 8. Interface

`/personnel` (register with search, filters, sort, chain of command, departments; **+ CREATE NEW AGENT**),
`/personnel/[id]` (profile + management), `/personnel/create` (ten steps — Identity, Species, Specialization,
Personality, Mission, Competencies, Tools, Permissions, Review, Create — with a live preview from the real service, AI
buttons on every field, *Let AI design my agent* with up to three alternatives, drafts on the server and an autosave in
this browser), `/bestiary` (beings and specializations, search by alternative names, filters by type, origin and entry
kind, controlled data entry) and `/bestiary/[key]` (article, registered agents, **Create a … agent**). Species have their
own sigils (wings, leaf, hat and clover, horns, wisp, lamp, flame, wave, cap, peaks, footprint, fox, lotus…) so a fairy
does not look like a small demon; colour is never the only signal.

## 9. Verification (2026-11-07)

| What | Result |
|---|---|
| `tests/test_personnel.py` | 36 passed (register, seed, Bestiary, AI + rules design, three entry points through the same 22 steps, custom species, several specializations, duplicates, invalid input, roles, four-eyes level approval, onboarding with/without a model, lifecycle, history, runtime, G-SUS) |
| Full backend suite | all passed (ruff clean) |
| PostgreSQL | migration 0013 up/down/up; `scripts/pg_smoke.py` incl. create → edit → archive of a custom agent with a user-created species |
| Playwright `tests/e2e/personnel.spec.ts` | 6 journeys × desktop, iPad, iPhone, Pixel = 24 passed |
| Accessibility (axe, WCAG 2.2 AA) | no serious/critical violations on the new pages, desktop and phone |

## 10. Limits and what is planned

* **Behavioural onboarding checks have only run against scripted test models here** — the test stack has no language
  model. Their judges are deterministic heuristics (refusal wording, the `escalate` flag, purpose words); a real local-model
  run is still to be recorded.
* Code agents keep their structured task types; free-text missions go to custom agents (or to code agents via G-SUS).
* A suggested new department is recorded, not created; an administrator creates it.
* Personas (the deep judgement profiles used by Rocky Flare) remain separate from the personnel identity.
* Not deployed; not committed (awaiting the owner's approval).
