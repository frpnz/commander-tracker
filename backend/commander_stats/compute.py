from __future__ import annotations

from typing import Any, Dict, List
import datetime
import sqlite3

def _rows_to_dicts(rows) -> List[Dict[str, Any]]:
    return [dict(r) for r in rows]

def compute_stats(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Compute aggregations used by the static frontend.

    Output contract (stats.v1.json):
      - version: str (currently "v1")
      - generated_utc: ISO-8601 UTC timestamp with trailing "Z"
      - counts: {games:int, entries:int}
      - filters: {players:[str], commanders:[str], brackets:[str]}
      - by_player: [{player:str, games:int, wins:int}]
      - by_player_commander: [{player:str, commander:str, bracket:str|None, games:int, wins:int}]
    """
    cur = conn.cursor()

    # By player
    cur.execute("""
        SELECT
            ge.player AS player,
            COUNT(*) AS games,
            SUM(CASE WHEN g.winner_player = ge.player THEN 1 ELSE 0 END) AS wins
        FROM gameentry ge
        JOIN game g ON g.id = ge.game_id
        GROUP BY ge.player
        ORDER BY games DESC, wins DESC, player ASC
    """)
    by_player = _rows_to_dicts(cur.fetchall())

    # By player + commander (+ bracket)
    cur.execute("""
        SELECT
            ge.player AS player,
            ge.commander AS commander,
            ge.bracket AS bracket,
            COUNT(*) AS games,
            SUM(CASE WHEN g.winner_player = ge.player THEN 1 ELSE 0 END) AS wins
        FROM gameentry ge
        JOIN game g ON g.id = ge.game_id
        GROUP BY ge.player, ge.commander, ge.bracket
        ORDER BY games DESC, wins DESC, player ASC, commander ASC
    """)
    by_player_commander = _rows_to_dicts(cur.fetchall())

    # Distinct filter values
    cur.execute("SELECT DISTINCT player FROM gameentry ORDER BY player ASC;")
    players = [r["player"] for r in cur.fetchall()]

    cur.execute("SELECT DISTINCT commander FROM gameentry ORDER BY commander ASC;")
    commanders = [r["commander"] for r in cur.fetchall()]

    cur.execute("SELECT DISTINCT bracket FROM gameentry WHERE bracket IS NOT NULL ORDER BY bracket ASC;")
    brackets = [r["bracket"] for r in cur.fetchall()]

    # High-level counts
    cur.execute("SELECT COUNT(*) AS n FROM game;")
    n_games = int(cur.fetchone()["n"])

    cur.execute("SELECT COUNT(*) AS n FROM gameentry;")
    n_entries = int(cur.fetchone()["n"])

    generated_utc = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    return {
        "version": "v1",
        "generated_utc": generated_utc,
        "counts": {"games": n_games, "entries": n_entries},
        "filters": {"players": players, "commanders": commanders, "brackets": brackets},
        "by_player": by_player,
        "by_player_commander": by_player_commander,
    }
