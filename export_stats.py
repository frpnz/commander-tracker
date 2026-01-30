#!/usr/bin/env python3
"""
Export static stats for GitHub Pages.

Generates:
- docs/data/stats.v1.json
- docs/stats/index.html (+ assets)

No third-party dependencies.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
from typing import Any, Dict


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def compute_stats(conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    Computes aggregations used by the static frontend:
      - by_player
      - by_player_commander
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
    by_player = [dict(r) for r in cur.fetchall()]

    # By player + commander (+ bracket del deck)
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
        ORDER BY games DESC, wins DESC, player ASC,
                 commander ASC
    """)
    by_pair = [dict(r) for r in cur.fetchall()]

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

    return {
        "version": "v1",
        "generated_utc": __import__("datetime").datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "counts": {"games": n_games, "entries": n_entries},
        "filters": {"players": players, "commanders": commanders, "brackets": brackets},
        "by_player": by_player,
        "by_player_commander": by_pair,
    }


def _copy_site(docs_dir: str) -> None:
    """Copy ./site into docs_dir (static site root)."""
    src = os.path.join(os.path.dirname(__file__), "site")
    if os.path.exists(docs_dir):
        shutil.rmtree(docs_dir)
    os.makedirs(docs_dir, exist_ok=True)

    for root, _, files in os.walk(src):
        rel = os.path.relpath(root, src)
        out_root = os.path.join(docs_dir, rel) if rel != "." else docs_dir
        os.makedirs(out_root, exist_ok=True)
        for fn in files:
            shutil.copy(os.path.join(root, fn), os.path.join(out_root, fn))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="Path to commander_tracker.sqlite")
    ap.add_argument("--docs", default="docs", help="Output docs directory (default: docs)")
    args = ap.parse_args()

    docs_dir = os.path.abspath(args.docs)

    # (Re)create static site root
    _copy_site(docs_dir)

    # Export JSON data
    os.makedirs(os.path.join(docs_dir, "data"), exist_ok=True)
    conn = _connect(args.db)
    stats = compute_stats(conn)
    conn.close()

    json_path = os.path.join(docs_dir, "data", "stats.v1.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
