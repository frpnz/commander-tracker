#!/usr/bin/env bash
set -e

echo "Installing Python dependencies"
pip install -r requirements.txt

echo "Installing Playwright Chromium browser"
python -m playwright install chromium

echo "Installing system dependencies for Chromium"
python -m playwright install-deps chromium

echo "Setup completed successfully"