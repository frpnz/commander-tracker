#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from commander_stats.db import connect
from commander_stats.validation import validate_database


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate Commander DB invariants used by the exporter.")
    ap.add_argument("--db", default="data/commander_tracker.sqlite")
    ap.add_argument("--strict-duplicates", action="store_true")
    ap.add_argument("--validation-exceptions", default="data/validation_exceptions.json")
    args = ap.parse_args()

    allowed: set[int] = set()
    exceptions = Path(args.validation_exceptions)
    if exceptions.exists():
        raw = json.loads(exceptions.read_text(encoding="utf-8"))
        allowed = {int(v) for v in (raw.get("duplicate_player_game_ids") or [])}

    conn = connect(str(Path(args.db).resolve()))
    try:
        issues = validate_database(
            conn,
            duplicate_players_are_errors=args.strict_duplicates,
            allowed_duplicate_game_ids=allowed,
        )
    finally:
        conn.close()

    if not issues:
        print("OK: nessuna anomalia trovata")
        return 0

    for issue in issues:
        print(f"{issue.severity.upper():7s} [{issue.code}] {issue.message}")
    return 1 if any(i.severity == "error" for i in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
