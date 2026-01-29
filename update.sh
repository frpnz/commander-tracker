#!/usr/bin/env bash
set -euo pipefail

# ==== CONFIG (modifica se serve) ====
REPO_DIR="${REPO_DIR:-$(pwd)}"                 # se lo lanci dalla root repo, va bene così
EXPORT_CMD="${EXPORT_CMD:-python3 export_static_json.py}"
REMOTE="${REMOTE:-origin}"
BRANCH="${BRANCH:-main}"                      # cambia in master se usi master
DO_PULL="${DO_PULL:-0}"                       # 0 = default: NO pull (per lavorare con modifiche locali)
# ===================================

usage() {
  cat <<'EOF'
Uso:
  ./deploy_pages.sh [messaggio commit]

Env opzionali:
  REPO_DIR=/path/al/repo
  EXPORT_CMD="python3 export_static_json.py"
  REMOTE=origin
  BRANCH=main
  DO_PULL=0|1

Esempi:
  ./deploy_pages.sh
  ./deploy_pages.sh "Update partite"
  DO_PULL=1 ./deploy_pages.sh "Sync + export"
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

MSG="${1:-}"
if [[ -z "$MSG" ]]; then
  TS="$(date '+%Y-%m-%d %H:%M:%S')"
  MSG="Export static (Pages) - ${TS}"
fi

cd "$REPO_DIR"

# Safety: assicurati di essere in un repo git
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
  echo "Errore: non sei dentro un repository git (REPO_DIR=$REPO_DIR)"
  exit 1
}

echo "== Repo: $(pwd)"
echo "== Target push: $REMOTE/$BRANCH"
echo "== Export: $EXPORT_CMD"
echo "== DO_PULL: $DO_PULL"

# Passo 0: pull opzionale (DISABILITATO DI DEFAULT)
# Nota: se lo abiliti e hai modifiche locali, usiamo autostash per non bloccare.
if [[ "$DO_PULL" == "1" ]]; then
  echo "== Git pull --rebase (autostash) from $REMOTE/$BRANCH"
  git fetch "$REMOTE" "$BRANCH" --prune
  git pull --rebase --autostash "$REMOTE" "$BRANCH"
fi

# Passo 1: export
echo "== Running export"
eval "$EXPORT_CMD"

# Passo 2: git add/commit (solo se ci sono cambi)
echo "== Git status"
if git status --porcelain | grep -q .; then
  echo "== Changes detected: committing"
  git add -A
  git commit -m "$MSG"
else
  echo "== No changes to commit. Skipping commit."
fi

# Passo 3: push
echo "== Pushing to $REMOTE/$BRANCH"
git push "$REMOTE" "$BRANCH"

echo "✅ Done."
