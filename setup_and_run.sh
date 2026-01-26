#!/usr/bin/env bash
set -euo pipefail

# ===== Config =====
VENV_DIR=".venv"
APP_MODULE="app.app:app"   # cambia se il tuo entrypoint è diverso
HOST="127.0.0.1"
PORT="8000"
# ================

echo "==> [1/5] Checking python..."
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "ERROR: $PYTHON_BIN not found. Install Python 3.10+."
  exit 1
fi

echo "==> [2/5] Creating venv in ${VENV_DIR}..."
"$PYTHON_BIN" -m venv "$VENV_DIR"

echo "==> [3/5] Activating venv & upgrading pip..."
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip wheel setuptools

echo "==> [4/5] Installing requirements..."
if [[ ! -f "requirements.txt" ]]; then
  echo "ERROR: requirements.txt not found in current directory."
  exit 1
fi
pip install -r requirements.txt

echo "==> Installing Playwright Chromium (needed for PDF export)..."
python -m playwright install chromium

echo "==> [5/5] Starting server..."
echo "    Open: http://${HOST}:${PORT}"
exec uvicorn "$APP_MODULE" --host "$HOST" --port "$PORT" --reload
