#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# Commander Tracker - Secure Server Setup (Ubuntu)
# - UFW: allow 22/80/443
# - Caddy: HTTPS + BasicAuth + reverse_proxy -> 127.0.0.1:8000
# - systemd: uvicorn on localhost only
# ============================================================================
#
# Usage:
#   sudo bash setup_server.sh
#
# Prompts:
#   - App directory (where app.py lives)
#   - Linux user to run service (e.g. ubuntu)
#   - Domain (recommended) or your public IP (domain strongly recommended)
#   - BasicAuth username + password
#
# Notes:
#   - Your DNS must point DOMAIN -> server IP (A record) for HTTPS to work.
#   - This script does NOT open port 8000 to the internet.
# ============================================================================

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: missing command: $1"
    exit 1
  }
}

if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: run as root (use sudo)."
  exit 1
fi

echo "== Commander Tracker secure setup =="

read -rp "App directory (full path, e.g. /home/ubuntu/commander-tracker): " APP_DIR
read -rp "Linux user to run the app (e.g. ubuntu): " RUN_USER
read -rp "Domain (recommended) (e.g. dashboard.example.com): " DOMAIN
read -rp "BasicAuth username (e.g. fra): " AUTH_USER
read -rsp "BasicAuth password: " AUTH_PASS
echo

if [[ ! -d "${APP_DIR}" ]]; then
  echo "ERROR: APP_DIR not found: ${APP_DIR}"
  exit 1
fi

if ! id -u "${RUN_USER}" >/dev/null 2>&1; then
  echo "ERROR: user not found: ${RUN_USER}"
  exit 1
fi

# ---------------------------
# Install packages
# ---------------------------
echo "== Installing base packages =="
apt-get update -y
apt-get install -y curl ufw ca-certificates

# ---------------------------
# Firewall
# ---------------------------
echo "== Configuring UFW firewall =="
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
ufw status

# ---------------------------
# Install Caddy (official repo)
# ---------------------------
echo "== Installing Caddy =="
apt-get install -y debian-keyring debian-archive-keyring apt-transport-https

curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg

curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  > /etc/apt/sources.list.d/caddy-stable.list

apt-get update -y
apt-get install -y caddy

need_cmd caddy

# ---------------------------
# Caddyfile (HTTPS + BasicAuth)
# ---------------------------
echo "== Writing Caddyfile =="
HASH="$(caddy hash-password --plaintext "${AUTH_PASS}")"

cat > /etc/caddy/Caddyfile <<EOF
${DOMAIN} {

  encode gzip

  basicauth * {
    ${AUTH_USER} ${HASH}
  }

  reverse_proxy 127.0.0.1:8000
}
EOF

chown root:root /etc/caddy/Caddyfile
chmod 644 /etc/caddy/Caddyfile

systemctl enable caddy
systemctl restart caddy

echo "== Caddy status =="
systemctl --no-pager status caddy | sed -n '1,15p'

# ---------------------------
# systemd service for Uvicorn
# ---------------------------
echo "== Creating systemd service for uvicorn =="

SERVICE_NAME="commander-tracker"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

# Try to detect venv uvicorn first; fallback to "python -m uvicorn"
UVICORN_BIN="${APP_DIR}/.venv/bin/uvicorn"
if [[ -x "${UVICORN_BIN}" ]]; then
  EXEC_START="${UVICORN_BIN} app:app --host 127.0.0.1 --port 8000"
else
  # Use python if present in venv; otherwise system python
  PY_BIN="${APP_DIR}/.venv/bin/python"
  if [[ -x "${PY_BIN}" ]]; then
    EXEC_START="${PY_BIN} -m uvicorn app:app --host 127.0.0.1 --port 8000"
  else
    EXEC_START="python3 -m uvicorn app:app --host 127.0.0.1 --port 8000"
  fi
fi

cat > "${SERVICE_PATH}" <<EOF
[Unit]
Description=Commander Tracker (FastAPI)
After=network.target

[Service]
User=${RUN_USER}
WorkingDirectory=${APP_DIR}
ExecStart=${EXEC_START}
Restart=always
RestartSec=2
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

echo "== App service status =="
systemctl --no-pager status "${SERVICE_NAME}" | sed -n '1,20p'

# ---------------------------
# Final hints
# ---------------------------
echo
echo "✅ Done."
echo "Now:"
echo " - Ensure DNS A record: ${DOMAIN} -> this server IP"
echo " - Visit: https://${DOMAIN}"
echo
echo "Useful commands:"
echo "  sudo systemctl status ${SERVICE_NAME}"
echo "  sudo journalctl -u ${SERVICE_NAME} -f"
echo "  sudo systemctl status caddy"
echo "  sudo journalctl -u caddy -f"
