#!/usr/bin/env bash
# Restore a backup made by scripts/backup.sh. Stop the server first.
# Verifies SHA256SUMS before touching anything; refuses to overwrite existing data unless --force is given
# (a SQLite database being replaced is kept as <file>.pre-restore).
# Usage: scripts/restore.sh [--force] BACKUP_DIR
set -euo pipefail
FORCE=0
if [[ "${1:-}" == "--force" ]]; then FORCE=1; shift; fi
SRC="${1:?usage: scripts/restore.sh [--force] BACKUP_DIR}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DB_URL="${DATABASE_URL:-sqlite:///./rocky.db}"
ARCHIVE="${ARCHIVE_DIR:-$ROOT/backend/data/archive}"
MODELS="${MODELS_DIR:-$ROOT/backend/data/models}"
( cd "$SRC" && sha256sum -c SHA256SUMS --quiet ) || { echo "checksum verification failed — nothing restored" >&2; exit 3; }
cd "$ROOT/backend"
case "$DB_URL" in
  sqlite:///*)
    DB_FILE="${DB_URL#sqlite:///}"
    if [[ -s "$DB_FILE" && $FORCE == 0 ]]; then echo "$DB_FILE exists — use --force to overwrite (it is kept as .pre-restore)" >&2; exit 4; fi
    if [[ -s "$DB_FILE" ]]; then cp "$DB_FILE" "$DB_FILE.pre-restore"; fi
    cp "$SRC/database.sqlite" "$DB_FILE"
    ;;
  postgresql*)
    PGURL="${DB_URL/postgresql+psycopg/postgresql}"
    TABLES="$(psql "$PGURL" -tAc "select count(*) from information_schema.tables where table_schema='public'")"
    if [[ "$TABLES" != "0" && $FORCE == 0 ]]; then echo "target database is not empty — restore into an empty database, or use --force" >&2; exit 4; fi
    gunzip -c "$SRC/database.sql.gz" | psql -q "$PGURL"
    ;;
  *) echo "unsupported DATABASE_URL: $DB_URL" >&2; exit 2 ;;
esac
if [[ -f "$SRC/archive.tar.gz" ]]; then mkdir -p "$ARCHIVE" && tar -xzf "$SRC/archive.tar.gz" -C "$ARCHIVE"; fi
if [[ -f "$SRC/models.tar" ]]; then mkdir -p "$MODELS" && tar -xf "$SRC/models.tar" -C "$MODELS"; fi
DATABASE_URL="$DB_URL" python3 -m alembic upgrade head   # bring an older backup up to the current schema
echo "restored from $SRC."
echo "If model weights were not in the backup: DAEMON CORE → Models → Install (or import the files offline; checksums in models.json are verified)."
