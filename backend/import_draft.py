#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
import sys

from admin_draft_stdlib import parse_companion_text, parse_playoffs_text
from draft_stats.db import connect, ensure_schema


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Sostituisce standings e playoff di un torneo Draft usando il formato MTG Companion."
    )
    ap.add_argument("--db", default="data/draft_tracker.sqlite", help="Path al DB Draft")
    ap.add_argument("--tournament-id", type=int, required=True, help="ID del torneo esistente")
    ap.add_argument("--standings", required=True, help="File di testo con standings MTG Companion")
    ap.add_argument("--playoffs", help="File di testo opzionale con playoff SF/F")
    args = ap.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.is_file():
        print(f"ERRORE: DB Draft non trovato: {db_path}", file=sys.stderr)
        return 2

    standings_path = Path(args.standings)
    playoffs_path = Path(args.playoffs) if args.playoffs else None

    try:
        standings_text = standings_path.read_text(encoding="utf-8")
        playoffs_text = playoffs_path.read_text(encoding="utf-8") if playoffs_path else ""
        rows = parse_companion_text(standings_text)
        playoffs = parse_playoffs_text(playoffs_text) if playoffs_text.strip() else []
    except FileNotFoundError as exc:
        print(f"ERRORE: file non trovato: {exc.filename}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print(f"ERRORE: {exc}", file=sys.stderr)
        return 2

    conn = connect(str(db_path))
    try:
        ensure_schema(conn)
        conn.execute("PRAGMA foreign_keys=ON")
        exists = conn.execute("SELECT 1 FROM tournament WHERE id=?", (args.tournament_id,)).fetchone()
        if not exists:
            print(f"ERRORE: torneo Draft id={args.tournament_id} non trovato", file=sys.stderr)
            return 2

        try:
            conn.execute("BEGIN")
            conn.execute("DELETE FROM standing WHERE tournament_id=?", (args.tournament_id,))
            conn.execute("DELETE FROM playoff_match WHERE tournament_id=?", (args.tournament_id,))
            conn.executemany(
                "INSERT INTO standing(tournament_id, player, wins, losses, draws, via_pct) VALUES(?,?,?,?,?,?)",
                [
                    (args.tournament_id, r["player"], int(r["w"]), int(r["l"]), int(r["d"]), float(r["via_pct"]))
                    for r in rows
                ],
            )
            conn.executemany(
                "INSERT INTO playoff_match(tournament_id, stage, player_a, player_b, winner) VALUES(?,?,?,?,?)",
                [
                    (args.tournament_id, m["stage"], m["player_a"], m["player_b"], m["winner"])
                    for m in playoffs
                ],
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    except sqlite3.Error as exc:
        print(f"ERRORE SQLite: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    suffix = f"; playoff: {len(playoffs)} match" if playoffs else ""
    print(f"OK: torneo {args.tournament_id}: {len(rows)} standings importati{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
