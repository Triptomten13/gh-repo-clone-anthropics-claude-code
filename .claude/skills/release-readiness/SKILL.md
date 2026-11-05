---
name: release-readiness
description: Decide whether the current branch is ready to ship — verification, migrations, docs, progress log, security checklist. Use before tagging or merging a release.
---
1. Run `/test-and-verify` (all steps) and `/security-audit`.
2. Migrations: new head applies and downgrades on SQLite and PostgreSQL; no edits to applied migrations.
3. Docs reflect reality: `docs/*` and `progress.md` updated; unfinished features listed as such.
4. `.env.example` lists every new setting; `docker compose config` validates.
5. Produce a short go/no-go with blocking issues first.
