# Backup and recovery

## What must survive

| Data | Where | Backed up by |
|---|---|---|
| Database (users, agents, tasks, approvals, audit, Archive metadata/chunks/vectors, memory, canon, DAEMON settings, model library, credentials *encrypted*, costs) | SQLite file or PostgreSQL | `scripts/backup.sh` / compose `backup` service |
| Archive original files | `ARCHIVE_DIR` | `scripts/backup.sh` / compose `backup` service |
| Model weights | `MODELS_DIR` | manifest always (`models.json`: key, file, repo, sha256, licence); weights only with `--with-models` |
| Secrets | `.env` (`SECRET_KEY`, `CREDENTIALS_KEY`) | **you** — keep them in a password manager; without the key, stored credentials cannot be decrypted (they must then be re-entered) |

## Backup

```bash
scripts/backup.sh                    # → backups/<UTC timestamp>/ {database.*, archive.tar.gz, models.json, SHA256SUMS}
scripts/backup.sh --with-models /mnt/offsite   # include weights (needed for a fully offline restore)
```

SQLite is copied with SQLite's online backup API (consistent while the server runs); PostgreSQL with `pg_dump`.
Docker: the `backup` service writes `rocky-<date>.sql.gz` and `archive-<date>.tar.gz` daily, keeping 14 days.

## Restore

```bash
# stop the server first
scripts/restore.sh backups/20261105T145748Z          # refuses to overwrite existing data
scripts/restore.sh --force backups/20261105T145748Z  # overwrite; an existing SQLite file is kept as *.pre-restore
```

The script verifies `SHA256SUMS` before touching anything (a tampered backup is refused), restores the database and the
Archive files, restores weights if present, and runs `alembic upgrade head` so an older backup reaches the current schema.
If weights were not in the backup, reinstall them in DAEMON CORE → Models (or import the files offline — the checksums
in `models.json` are verified).

**Tested 2026-11-05:** backup of the Independence-test database → restore into a separate file and Archive directory:
the refusal without `--force`, the forced restore (memory items, 4 installed models, 3 Archive files), and the refusal
of a deliberately modified backup all behaved as described.

## Crash recovery (no backup needed)

On start the API requeues tasks a crash left `running` (or fails them if no attempts remain) and resumes queued work
(`RESUME_TASKS_ON_START`, default on). Independence Test F kills the server with SIGKILL and verifies settings, active
models, memory, documents and the interrupted task all recover.

Test your restore regularly — an untested backup is a hope, not a backup.
