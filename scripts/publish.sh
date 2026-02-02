#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/Projects/commander-tracker}"
DB_PATH="${DB_PATH:-$REPO_DIR/data/commander_tracker.sqlite}"
DOCS_DIR="${DOCS_DIR:-$REPO_DIR/docs}"
VENV_DIR="${VENV_DIR:-$REPO_DIR/.venv}"

MSG="${1:-update data}"

cd "$REPO_DIR"

# usa python del venv senza "source" (più affidabile per script)
PY="$VENV_DIR/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "ERRORE: python venv non trovato in $PY"
  exit 1
fi

if [[ ! -f "$DB_PATH" ]]; then
  echo "ERRORE: DB non trovato in $DB_PATH"
  exit 1
fi

# (consigliato) evita diff inutili da WAL/SHM e rende il db consistente
# non fallire se sqlite3 non esiste (es. macchina senza cli)
if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$DB_PATH" "PRAGMA wal_checkpoint(FULL);"
fi

# esporta stats
"$PY" backend/export_stats.py --db "$DB_PATH" --docs "$DOCS_DIR"

# Stage selettivo: docs/data + db
# (docs/data triggera Pages; il DB no, grazie al paths: docs/** nel workflow)
NEED_COMMIT=0

if ! git diff --quiet -- docs/data; then
  git add -A docs/data
  NEED_COMMIT=1
fi

if ! git diff --quiet -- "$DB_PATH"; then
  git add "$DB_PATH"
  NEED_COMMIT=1
fi

if [[ "$NEED_COMMIT" -eq 1 ]]; then
  git commit -m "$MSG"
  git push
  echo "✅ Pubblicato/Salvato: $MSG"
else
  echo "ℹ️ Nessuna modifica in docs/data o nel DB"
fi

