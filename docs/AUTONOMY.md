# Model Hunter, Model Championship, Devil's Advocate, Account Vault

The owner's priorities for this initiative:

* **Model Hunter** — measure real performance on *this* hardware and *our* tasks, instead of chasing leaderboards.
* **Devil's Advocate** — able to question even G-SUS and the main orchestrator; never just another agent that agrees.
* **Account Vault** — practical autonomy for agents without passwords, API keys or account permissions spreading
  between models.
* **Model Championship** — new models compete against the installed ones on the same tests, the same hardware and the
  same tasks, so Demonkoncernen can *show* when it became smarter, faster or cheaper.

Everything extends what existed: the verified model library, the two benchmark suites, the encrypted credential store,
the tool gateway, the policy engine and four-eyes approvals. Status words: IMPLEMENTED AND VERIFIED · PARTIALLY
IMPLEMENTED · REQUIRES CREDENTIALS · REQUIRES USER APPROVAL · BLOCKED BY PLATFORM · NOT IMPLEMENTED.

## 1. Model Hunter (`backend/app/autonomy/hunter.py`)

`DISCOVER → SCREEN → REVIEW → APPROVE → DOWNLOAD + VERIFY → CHAMPIONSHIP`

* **Discover**: the official Hugging Face API (`/api/models?search=…&filter=gguf&expand[]=sha…`) per task — general,
  Swedish, coding, reasoning, small, embedding. **Change detection**: a repository whose revision is unchanged costs one
  search request and no detail calls.
* **Screen before any download** (deterministic, each reason states its evidence): single-file GGUF only (no pickle
  weights, no repository code — nothing from a repository is ever executed); the repository must *declare* a chat or
  embedding task (`pipeline_tag`); a licence must be stated; not gated; not safety-stripped (abliterated / uncensored);
  within the storage budget (`MODEL_HUNTER_MAX_GB`, default 6) and the machine's RAM (`hardware.fit`). Parameter counts
  come from the GGUF header, not from names. Downloads and likes are recorded and never treated as evidence.
* **Review → approve → download**: the Devil's Advocate reviews the acquisition; `models.acquire` is APPROVAL_REQUIRED
  (a second person); the download goes through the **existing verified installer** — licence and sha256 re-checked
  against the live Hub, trusted hosts only, checksum verified — as a pinned library entry. A changed upstream file is
  refused.

## 2. Model Championship (`championship.py`)

Every installed chat model runs the **17-task DAEMON suite** (deterministic graders) and the **creative dataset**
(rule-based scoring with the brief-echo check), called the same way (by model key, thinking off, same token limits —
stated in the result), on the same machine, in the same run. Stored with it: the hardware fingerprint (CPU, cores, RAM,
GPU, runtime version) and the suite versions. Standings per category (accuracy, each skill, each creative category,
tokens/s, p50 latency, cost per success — lower is better where it should be). The result is compared only with the
previous championship on the **same hardware and suites**: *smarter* (quality up), *faster*, *cheaper*, *regressed*,
new leaders — and nothing is claimed when the best result did not change (< 2 %). Smaller models run first and a time
budget stops a championship before it runs for hours; one runs at a time (local models share the CPU).

## 3. Devil's Advocate (`advocate.py`)

Built so it cannot simply agree:

1. **A model-independent first layer**: the 12-question protocol (objective, reason, evidence, alternatives, why
   rejected, assumptions, what could go wrong, security, resources, simplest solution, what would change your mind,
   verification) and rule packs for model acquisitions, account requests, G-SUS plans and model selections. No model —
   not the proposer, not the strongest one — can talk these checks into agreeing.
2. **An optional second layer**: a model from a *different family* than the proposer constructs the strongest
   counter-argument. A finding counts only with evidence **and** an alternative; it can raise concerns, never block.
3. **Blocks only on policy and security** (unsafe format, unknown licence, does not fit, budget broken, irreversible
   without approval, agent asking for broad scopes, paid without approval). Everything else is a recommendation with
   severity and confidence.
4. **"Sound" is a real outcome** and lists what was checked.
5. **Measured**: a calibration set of known-bad and known-good decisions; an agreement monitor warns of rubber-stamping
   (> 90 % "sound" over ≥ 20 reviews) and of obstruction (< 10 %).
6. **It challenges G-SUS itself**: before a consequential G-SUS plan (a step handled by an agent of level ≥ 3) runs,
   the plan is reviewed; a block stops the run before any task is submitted. Steps that governance already stops for a
   human approval are not blocked twice.

It asks for auditable decision records, never for a model's hidden chain of thought.

## 4. Account Vault (`accounts.py`)

* An account is a `ServiceAccount` record (service, identity, purpose, level 0–4, scopes, the ten-point justification,
  the Devil's Advocate critique, the approval). Its secret lives encrypted in the **existing** credential store under
  the scope `<service>:<account id>`.
* **Agents never receive a secret.** They get a *tool grant* naming the scope; the governed tool runs on the server, the
  gateway hands the secret only to that tool function and redacts it from the result; every use is written to the audit
  trail (`vault.use`, tamper-evident) and shown per account.
* Levels 0–1 research and prepare; level ≥ 2 needs a second approver; paid services are RESTRICTED. A **person** signs up
  (e-mail/phone verification and CAPTCHAs are never bypassed), creates a least-privilege token and connects it with the
  owner attestation. One account per identity — duplicates are challenged.
* Health checks use the services' official identity endpoints (Hugging Face `whoami-v2`, GitHub `/user`, GitLab
  `/user`); expiry warnings; revoke disconnects the secret and removes every grant that used it.

## 5. Verification

`backend/tests/test_autonomy.py` (fake Hub, fake models, fake service endpoints — no network) and
`frontend/tests/e2e/autonomy.spec.ts`; migration 0012 up/down/up on SQLite and PostgreSQL 16; PostgreSQL smoke including
the new endpoints. Real runs: §6.

## 6. Real runs on this machine (2026-11-07)

Hardware: Intel Xeon @ 2.1 GHz, 4 cores, ~17 GB RAM, no GPU, llama.cpp 0.3.36. Evidence:
`docs/benchmarks/autonomy-2026-11-07.json`.

### 6.1 Model Hunter — live discovery (official Hugging Face API)

Four searches (Swedish, small, general, coding), 15 repositories each, **60 repositories in ~10 s**, nothing downloaded.
**12 shortlisted.** Screened out before any download:

| Reason | Repositories |
|---|---|
| not a chat / text-generation model (speech recognition, text-to-speech, embeddings, rerankers) | 14 |
| no single-file GGUF in a supported quantization | 12 |
| no licence stated in the model card | 8 |
| above the 6 GB storage budget (16–22 GB repositories) | 7 |
| safety training removed (abliterated / uncensored) | 3 |

The first run did **not** check the declared task: a search for small models shortlisted speech-recognition and
text-to-speech GGUFs as chat models. The screening now requires the repository to declare a chat or embedding task
(`pipeline_tag`). Most-downloaded results included 27B–35B models and an abliterated fine-tune — popularity is not a fit.

### 6.2 Real acquisition through the governed path

`unsloth/Qwen3-4B-Instruct-2507-GGUF` (Q4_K_M, 2.5 GB, Apache-2.0), a newer non-thinking release of the installed
Qwen3 4B:

1. Devil's Advocate: **concerns** — "the case for this model rests on popularity or public leaderboards, not on our
   tasks"; alternative: "run it in the Model Championship against the installed models".
2. Approval filed (`models.acquire`, APPROVAL_REQUIRED); an attempt to download before approval was refused.
3. A second person (approver role) approved; the existing installer downloaded it in **22 s**, verified the sha256 and
   re-checked the licence against the live Hub (`…@a06e946bb6b6`).

### 6.3 Model Championships — and what they taught us

**Championships #1 and #2** (sampling as in normal use: temperature 0.2, random seed): #1 = the five installed chat
models (978 s), #2 = the same five + the newcomer (920 s). The comparison reported *"faster, smarter in 5 categories;
2 regressions"* — but the **unchanged** models moved between the two runs:

| Same model, same tasks, 15 minutes apart | #1 | #2 |
|---|---|---|
| SmolLM2 360M accuracy (17 tasks) | 0.588 | 0.647 |
| SmolLM2 360M songwriting | 0.464 | 0.666 |
| SmolLM2 360M poetry | 0.747 | 0.468 |
| Qwen2.5 0.5B accuracy | 0.647 | 0.706 |
| Qwen2.5 1.5B deep reasoning | 0.29 | 0.43 |

So most of the "progress" was sampling luck. Two fixes followed, with tests: championships now decode **greedily**
(temperature 0, top_k 1, fixed seed — recorded in the suite signature, so they are never compared with sampled runs),
and the comparison **attributes**: models that ran unchanged in both championships are controls whose own movement is the
noise floor, and only a new or changed model that leads by more than that floor counts as smarter, faster or cheaper.

**Championships #3 and #4** (greedy): results in §6.4.

### 6.4 Greedy championships (#3 baseline 714 s, #4 with the newcomer 975 s)

**Reproducible now**: every unchanged model scored *exactly* the same on every quality category in #3 and #4 (noise
0.0). Only speed and latency moved (up to 2.2 tokens/s and 0.49 s — a shared CPU), and the comparison reported those as
variance, not progress.

| Model (thinking off for all) | Accuracy /17 | Tokens/s | Songwriting | Brainstorming | Programming | Time |
|---|---|---|---|---|---|---|
| SmolLM2 360M | 0.529 | 27.3 | 0.441 | 0.601 | 0.883 | 40 s |
| Qwen2.5 0.5B | 0.647 | 14.7 | 0.421 | 0.596 | 0.983 | 37 s |
| Qwen2.5 1.5B | 0.647 | 8.6 | 0.738 | 0.939 | 0.983 | 79 s |
| Qwen3 4B | 0.588 | 4.6 | 0.774 | 0.913 | 0.967 | 214 s |
| **Qwen3-4B-Instruct-2507 (newcomer)** | **0.706** | 5.5 | **0.812** | **0.958** | 0.967 | 251 s |
| Qwen3 8B | 0.647 | 2.0 | 0.796 | 0.953 | 0.883 | 355 s |

Verdict of #4 vs #3: **smarter in 2 categories, attributable to Qwen3-4B-Instruct-2507** — accuracy 0.647 → 0.706
and songwriting 0.796 (Qwen3 8B) → 0.812; brainstorming 0.953 → 0.958 is under the 2 % threshold and was not claimed.
It is also 18 % faster than the Qwen3 4B it would replace (5.5 vs 4.6 tokens/s).

**How strong is that?** Weak but real: accuracy +0.059 is **one more task out of 17**; songwriting rests on **2 tasks**
and clears the 2 % threshold by a hair; and championships run every model **without its thinking phase** — the
incumbent Qwen3 4B scores 17/17 *with* thinking in the deep slot. Nothing was switched automatically.

### 6.5 Devil's Advocate on the switch (real, with its model layer)

Decision record: "replace Qwen3 4B with Qwen3-4B-Instruct-2507 as the default chat model", with the championship as
evidence. First review (4 s): **sound** — every protocol question was answered, and the rules checked that evidence
*existed*, not how strong it was. The independent model layer had only **SmolLM2 360M** available: independence
excludes the proposer's family, and every other installed model is a Qwen. It produced no usable finding. A rule for
evidence strength (sample size, deciding margin, test conditions) was added; the second review returned **concerns:
"the evidence rests on 17 task(s)"** and **"the test conditions may favour one side"**. Lesson: a critic needs a
capable model from *another* family — the next thing the Model Hunter should bring in (Llama, Gemma, Mistral or Phi).

## 7. Capability matrix

| Capability | Status | Evidence / remaining |
|---|---|---|
| Model discovery on Hugging Face (official API, change detection) | **IMPLEMENTED AND VERIFIED** | tests + real run (60 repositories) |
| Pre-download screening (format, declared task, licence, gating, safety, budget, RAM) | **IMPLEMENTED AND VERIFIED** | tests + real run; the declared-task rule came from the real run |
| Governed acquisition + verified download | **IMPLEMENTED AND VERIFIED** — REQUIRES USER APPROVAL | real 2.5 GB acquisition, four eyes |
| Model registry with licence, sha256, revision, provenance | **IMPLEMENTED AND VERIFIED** | the existing library, pinned entries |
| Runtimes beyond llama.cpp (vLLM, Transformers, MLX, ONNX), vision/audio inference | **NOT IMPLEMENTED** | the Hunter screens such models out because nothing can run them |
| Model Championship (same tasks, hardware, run; attribution) | **IMPLEMENTED AND VERIFIED** | 4 real championships; greedy decoding and attribution came from the first two |
| Championship statistics (repeats, confidence intervals, larger task sets) | **NOT IMPLEMENTED** | 17 + 10 tasks today |
| Scheduled scans and championships | **PARTIALLY IMPLEMENTED** | agent task types exist (`model.discover`, `model.championship`); no recurring schedule configured |
| Devil's Advocate rule layer, calibration, agreement monitor | **IMPLEMENTED AND VERIFIED** | 9/9 calibration; evidence-strength rule from the real review |
| Devil's Advocate on G-SUS plans | **IMPLEMENTED AND VERIFIED** | tests; G-SUS plans do not yet record alternatives, so reviewed plans carry that concern |
| Independent-family model review | **IMPLEMENTED**, weak in practice | only SmolLM2 360M is outside the Qwen family here |
| Account Vault: proposals, critique, four eyes, encrypted storage, grants, audit, revoke | **IMPLEMENTED AND VERIFIED** | tests incl. a token that never appears in results, API, audit, model calls or tool records |
| Live account health checks (Hugging Face, GitHub, GitLab) | **REQUIRES CREDENTIALS** | official endpoints implemented; no account is connected here |
| OAuth flows, automatic rotation | **NOT IMPLEMENTED** | token paste by the owner; expiry warnings only |
| Account creation on third-party sites | **BLOCKED BY PLATFORM** (by design) | e-mail/phone verification and CAPTCHAs are never bypassed — a person signs up |
| GitHub development division (repositories, PRs, CI via agents) | **NOT IMPLEMENTED** | identity check only (`github.whoami`) |
| Model Council beyond Creative Tournaments, Innovation Board, multimodal learning | **NOT IMPLEMENTED** | deferred under the "finish before adding" principle |
