#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/Projects/commander-tracker}"
DB_PATH="${DB_PATH:-$REPO_DIR/data/commander_tracker.sqlite}"
DRAFT_DB_PATH="${DRAFT_DB_PATH:-$REPO_DIR/data/draft_tracker.sqlite}"
DOCS_DIR="${DOCS_DIR:-$REPO_DIR/docs}"
MSG="${1:-update data}"

cd "$REPO_DIR"

if [[ -n "${PYTHON_BIN:-}" ]]; then
  PY="$PYTHON_BIN"
elif [[ -x "$REPO_DIR/.venv/bin/python" ]]; then
  PY="$REPO_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY="$(command -v python3)"
else
  echo "ERRORE: Python 3 non trovato"
  exit 1
fi

for db in "$DB_PATH" "$DRAFT_DB_PATH"; do
  if [[ ! -f "$db" ]]; then
    echo "ERRORE: DB non trovato in $db"
    exit 1
  fi
done

# Flush WAL state without depending on the sqlite3 CLI.
"$PY" - "$DB_PATH" "$DRAFT_DB_PATH" <<'PY'
import sqlite3, sys
for path in sys.argv[1:]:
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA wal_checkpoint(FULL)")
    finally:
        conn.close()
PY

# Hardening gate: stdlib tests + DB invariants before touching docs/.
"$PY" -m unittest discover -s tests -v
"$PY" backend/validate_db.py --db "$DB_PATH"

# Rebuild the complete static artifact. The exporter validates Commander data.
"$PY" backend/export_stats.py \
  --db "$DB_PATH" \
  --draft-db "$DRAFT_DB_PATH" \
  --docs "$DOCS_DIR"

# Keep source frontend and generated Pages artifact in the same commit.
git add -A -- frontend/site docs data/validation_exceptions.json

# Stage the repository DBs when the default in-repo paths are used.
if [[ "$DB_PATH" == "$REPO_DIR/data/commander_tracker.sqlite" ]]; then
  git add -- data/commander_tracker.sqlite
fi
if [[ "$DRAFT_DB_PATH" == "$REPO_DIR/data/draft_tracker.sqlite" ]]; then
  git add -- data/draft_tracker.sqlite
fi

if ! git diff --cached --quiet; then
  git commit -m "$MSG"
  git push
  echo "Pubblicato/Salvato: $MSG"
else
  echo "Nessuna modifica da pubblicare"
fi
