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

## 6. Real runs on this machine

Filled in from `docs/benchmarks/autonomy-2026-11-07.json`.
