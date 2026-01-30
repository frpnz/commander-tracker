from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from core import session_from
from stats_data import build_stats_dataset


def copy_site(site_src: Path, docs_dir: Path) -> None:
    if not site_src.exists():
        raise FileNotFoundError(f"Missing site_src directory: {site_src}")

    # Start clean for deterministic output (keeps GH pages tidy).
    if docs_dir.exists():
        shutil.rmtree(docs_dir)
    shutil.copytree(site_src, docs_dir)


def write_output(out_dir: Path, payload: dict) -> None:
    docs = out_dir / "docs"
    site_src = out_dir / "site_src"

    copy_site(site_src, docs)
    (docs / "data").mkdir(parents=True, exist_ok=True)

    (docs / "data" / "stats.v1.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Export Stats (JSON + static site) for GitHub Pages.")
    ap.add_argument("--db", required=True, help="Path to commander_tracker.sqlite")
    ap.add_argument("--out", default=".", help="Project root output dir (default: current dir)")
    ap.add_argument("--top-triples", type=int, default=50)
    ap.add_argument("--max-unique", type=int, default=200)
    args = ap.parse_args()

    out_dir = Path(args.out).resolve()

    with session_from(args.db) as session:
        payload = build_stats_dataset(session, top_triples=args.top_triples, max_unique=args.max_unique)

    write_output(out_dir, payload)
    print(f"OK: wrote {out_dir / 'docs'}")
    print("Tip: preview locally with:  python -m http.server -d docs 8000")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
