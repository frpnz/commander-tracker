#!/usr/bin/env bash
set -e

echo "Installing Python dependencies"
pip install -r requirements.txt

echo "Installing system deps for Playwright Chromium (Ubuntu 24.04+ compatible)"
sudo apt update
sudo apt install -y \
  libasound2t64 \
  libnss3 \
  libatk-bridge2.0-0 \
  libxss1 \
  libgbm1 \
  libxshmfence1 \
  libxrandr2 \
  libxcomposite1 \
  libxcursor1 \
  libxdamage1 \
  libxi6 \
  libdrm2 \
  libgtk-3-0t64 \
  libcups2 \
  libatspi2.0-0

echo "Installing Playwright Chromium browser"
python -m playwright install chromium

echo "Setup completed successfully"