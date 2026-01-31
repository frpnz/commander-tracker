from __future__ import annotations

import argparse
import json
from pathlib import Path

from .db import connect
from .compute import compute_stats
from .site import copy_static_site

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="export_stats", description="Export static stats site (GitHub Pages friendly).")
    ap.add_argument("--db", required=True, help="Path to commander_tracker.sqlite")
    ap.add_argument("--docs", default="docs", help="Output docs directory (default: docs)")
    ap.add_argument("--site", default=None, help="Path to frontend/site (default: <repo>/frontend/site)")
    return ap

def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]  # .../backend/commander_stats -> repo root
    site_dir = Path(args.site) if args.site else (repo_root / "frontend" / "site")
    docs_dir = Path(args.docs).resolve()

    # (Re)create static site root
    copy_static_site(str(site_dir), str(docs_dir))

    # Export JSON data
    data_dir = docs_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    conn = connect(str(Path(args.db).resolve()))
    try:
        stats = compute_stats(conn)
    finally:
        conn.close()

    json_path = data_dir / "stats.v1.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    # Export JSON schema alongside the data for a visible contract
    schema_src = repo_root / "backend" / "stats.v1.schema.json"
    if schema_src.exists():
        (data_dir / "stats.v1.schema.json").write_text(schema_src.read_text(encoding="utf-8"), encoding="utf-8")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
