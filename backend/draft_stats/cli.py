from __future__ import annotations

import argparse
import os
from pathlib import Path

from .compute import compute_draft, write_json


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Export draft tournament stats to a JSON file for the static site.")
    p.add_argument(
        "--db",
        default=os.environ.get("DRAFT_DB", os.path.join(os.path.dirname(__file__), "..", "..", "data", "draft_tracker.sqlite")),
        help="Path to draft SQLite DB (default: ./data/draft_tracker.sqlite or env DRAFT_DB)",
    )
    p.add_argument(
        "--out",
        default=os.environ.get("DRAFT_OUT", os.path.join(os.path.dirname(__file__), "..", "..", "docs", "data", "draft.v1.json")),
        help="Output JSON path (default: ./docs/data/draft.v1.json)",
    )
    args = p.parse_args(argv)

    data = compute_draft(args.db)
    write_json(data, args.out)

    print(f"Wrote {args.out} (tournaments={data['counts']['tournaments']}, players={data['counts']['players']})")
    return 0
