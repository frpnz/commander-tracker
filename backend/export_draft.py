#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Convenience wrapper for exporting draft stats.

Example:
  python backend/export_draft.py --db data/draft_tracker.sqlite --docs docs

This writes:
  docs/data/draft.v1.json

It does NOT copy the site (that's handled by the commander exporter).
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from draft_stats.compute import compute_draft, write_json


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.environ.get("DRAFT_DB", "data/draft_tracker.sqlite"))
    ap.add_argument("--docs", default="docs")
    args = ap.parse_args(argv)

    db_path = Path(args.db).resolve()
    if not db_path.is_file():
        raise SystemExit(f"Draft DB non trovato: {db_path}")

    out = os.path.join(args.docs, "data", "draft.v1.json")
    data = compute_draft(str(db_path))
    write_json(data, out)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
