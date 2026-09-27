#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

from commander_stats.db import connect
from commander_stats.ingest import insert_games_atomic
from commander_stats.validation import PayloadValidationError, normalize_game_payload


def _load_payloads(paths: list[Path]) -> list[dict]:
    payloads: list[object] = []
    for path in paths:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError(f"File non trovato: {path}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON non valido in {path}: {exc}") from exc

        if isinstance(raw, list):
            payloads.extend(raw)
        else:
            payloads.append(raw)

    if not payloads:
        raise ValueError("Nessuna partita da importare")

    normalized: list[dict] = []
    for idx, item in enumerate(payloads, start=1):
        try:
            normalized.append(normalize_game_payload(item, label=f"Elemento #{idx}"))
        except PayloadValidationError as exc:
            raise ValueError(str(exc)) from exc
    return normalized


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Importa uno o piu payload game.v1 nel DB Commander come transazione atomica."
    )
    ap.add_argument("files", nargs="+", help="File JSON; ogni file puo contenere un oggetto o un array di partite")
    ap.add_argument("--db", default="data/commander_tracker.sqlite", help="Path al DB Commander")
    args = ap.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.is_file():
        print(f"ERRORE: DB Commander non trovato: {db_path}", file=sys.stderr)
        return 2

    try:
        games = _load_payloads([Path(p) for p in args.files])
    except (OSError, ValueError) as exc:
        print(f"ERRORE: {exc}", file=sys.stderr)
        return 2

    try:
        conn = connect(str(db_path))
        try:
            ids = insert_games_atomic(conn, games)
        finally:
            conn.close()
    except sqlite3.Error as exc:
        print(f"ERRORE SQLite: {exc}", file=sys.stderr)
        return 1

    print(f"OK: importate {len(ids)} partite (id: {', '.join(map(str, ids))})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
