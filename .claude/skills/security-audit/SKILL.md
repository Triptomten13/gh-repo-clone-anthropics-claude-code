---
name: security-audit
description: Review changes or the whole repo for security issues specific to this platform (auth, permissions, approvals, prompt injection, uploads, secrets, SQL portability). Use before releases or after touching api/, security/, knowledge/ or agents.
---
Check, citing file:line for each finding:
- Every state-changing route has `require_role` and an audit entry; admin-only actions stay admin-only.
- No new path lets an agent raise its own `permission_level` or bypass `Approval` for LEVEL 4–5 actions.
- External/retrieved text reaching a model is wrapped by `security/untrusted.wrap` and covered by `GUARD`.
- Uploads go through `knowledge/extract.extract` (extension + magic + size); files are stored under a generated name, never executed.
- No secrets in code, logs, LLM prompts or API responses (`/api/integrations` reports only missing env names).
- Memory refuses credentials and ID/card numbers (`knowledge/memory.screen`).
- Dependencies: `pip-audit -r backend/requirements.txt`, `npm audit --omit=dev` in frontend.
Report findings by severity; propose fixes; add a regression test for each fixed issue.
