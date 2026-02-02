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

# esporta stats
"$PY" backend/export_stats.py --db "$DB_PATH" --docs "$DOCS_DIR"

# commit/push solo se ci sono modifiche
if [[ -n "$(git status --porcelain)" ]]; then
  git add -A
  git commit -m "$MSG"
  git push
  echo "✅ Pubblicato: $MSG"
else
  echo "ℹ️ Nessuna modifica da pushare"
fi

