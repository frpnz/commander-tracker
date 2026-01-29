#!/usr/bin/env bash
source .venv/bin/activate
python export_static_json.py
git add .
git commit -m "update data"
git push
echo "✅ Done."
