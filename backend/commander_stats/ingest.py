from __future__ import annotations

import sqlite3
from typing import Any


def insert_games_atomic(conn: sqlite3.Connection, games: list[dict[str, Any]]) -> list[int]:
    """Insert already-normalized games as one all-or-nothing transaction."""
    ids: list[int] = []
    try:
        conn.execute("BEGIN")
        cur = conn.cursor()
        for game in games:
            cur.execute(
                "INSERT INTO game (played_at, notes, winner_player) VALUES (?, ?, ?)",
                (game["played_at"], game.get("notes"), game.get("winner_player")),
            )
            game_id = int(cur.lastrowid)
            cur.executemany(
                "INSERT INTO gameentry (game_id, player, commander, bracket) VALUES (?, ?, ?, ?)",
                [
                    (game_id, e["player"], e["commander"], e.get("bracket"))
                    for e in game["entries"]
                ],
            )
            ids.append(game_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return ids
