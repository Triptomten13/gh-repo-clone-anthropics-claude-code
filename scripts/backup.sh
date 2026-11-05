#!/usr/bin/env bash
# Back up what Demonkoncernen AB needs to recover: database, Archive files and the model manifest.
# Model weights are NOT copied by default (large, re-downloadable, checksum-verified on reinstall);
# pass --with-models to include them (needed for a fully offline restore).
# Usage: scripts/backup.sh [--with-models] [DEST_DIR]     (uses DATABASE_URL, ARCHIVE_DIR, MODELS_DIR like the server)
set -euo pipefail
WITH_MODELS=0
if [[ "${1:-}" == "--with-models" ]]; then WITH_MODELS=1; shift; fi
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-$ROOT/backups}/$(date -u +%Y%m%dT%H%M%SZ)"
DB_URL="${DATABASE_URL:-sqlite:///./rocky.db}"
ARCHIVE="${ARCHIVE_DIR:-$ROOT/backend/data/archive}"
MODELS="${MODELS_DIR:-$ROOT/backend/data/models}"
mkdir -p "$DEST"
cd "$ROOT/backend"
case "$DB_URL" in
  sqlite:///*)
    DB_FILE="${DB_URL#sqlite:///}"
    # consistent online copy through SQLite's backup API (safe while the server runs)
    python3 -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()" \
      "$DB_FILE" "$DEST/database.sqlite"
    ;;
  postgresql*)
    PGURL="${DB_URL/postgresql+psycopg/postgresql}"
    pg_dump --no-owner "$PGURL" | gzip > "$DEST/database.sql.gz"
    ;;
  *) echo "unsupported DATABASE_URL: $DB_URL" >&2; exit 2 ;;
esac
if [[ -d "$ARCHIVE" ]]; then tar -czf "$DEST/archive.tar.gz" -C "$ARCHIVE" .; else echo "no archive dir at $ARCHIVE (skipped)"; fi
# manifest: installed models with verified checksums + DAEMON settings (enough to restore models offline or from the Hub)
DATABASE_URL="$DB_URL" python3 - "$DEST/models.json" <<'PY'
import json, sys
sys.path.insert(0, ".")
from app.db import SessionLocal
from app.models import LocalModel, SystemState
s = SessionLocal()
rows = [{"key": m.key, "file": m.source_file, "repo": m.source_repo, "sha256": m.sha256_actual, "license": m.license}
        for m in s.query(LocalModel).filter(LocalModel.status == "installed")]
st = s.get(SystemState, "daemon")
json.dump({"installed": rows, "daemon_settings": st.value if st else None}, open(sys.argv[1], "w"), indent=2)
PY
if [[ $WITH_MODELS == 1 && -d "$MODELS" ]]; then tar -cf "$DEST/models.tar" -C "$MODELS" --exclude='*.part' .; fi
( cd "$DEST" && sha256sum -- * > SHA256SUMS )
echo "backup written to $DEST"
