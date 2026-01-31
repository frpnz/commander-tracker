from __future__ import annotations

from typing import Any, Dict, List, Tuple
import datetime
import sqlite3
import math

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

    # --- Weighted winrate (delta winner bracket vs avg table bracket excluding winner) ---
    # Delta: Δ = b_winner - avg(brackets_other_players)
    # (the average is computed excluding the winner).
    # Weight: w(Δ)=clip(exp(-k*Δ), w_min, w_max)
    # Chosen to be visible but not excessive.
    K = 0.30
    W_MIN = 0.70
    W_MAX = 1.40

    def _to_float_bracket(v):
        if v is None or v == "":
            return None
        try:
            return float(v)
        except Exception:
            return None

    def _clip(x: float, lo: float, hi: float) -> float:
        return lo if x < lo else hi if x > hi else x

    def _weight(delta: float) -> float:
        return _clip(math.exp(-K * delta), W_MIN, W_MAX)

    # We compute weighted aggregations by iterating per game to have access to
    # the winner and the full table brackets.
    cur.execute(
        """
        SELECT
            g.id AS game_id,
            g.winner_player AS winner_player,
            ge.player AS player,
            ge.commander AS commander,
            ge.bracket AS bracket
        FROM gameentry ge
        JOIN game g ON g.id = ge.game_id
        ORDER BY g.id ASC
        """
    )
    rows_entries = _rows_to_dicts(cur.fetchall())

    # game_id -> {winner:str, entries:[{player, commander, bracket}]}
    games: Dict[int, Dict[str, Any]] = {}
    for r in rows_entries:
        gid = int(r["game_id"])
        g = games.get(gid)
        if g is None:
            g = {"winner": r.get("winner_player"), "entries": []}
            games[gid] = g
        g["entries"].append(
            {
                "player": r.get("player"),
                "commander": r.get("commander"),
                "bracket": r.get("bracket"),
            }
        )

    # Aggregation maps
    by_player_w: Dict[str, Dict[str, Any]] = {}
    by_pair_w: Dict[Tuple[str, str, Any], Dict[str, Any]] = {}

    for g in games.values():
        winner = g.get("winner")
        entries = g.get("entries") or []

        # Winner bracket
        bw = None
        for e in entries:
            if e.get("player") == winner:
                bw = _to_float_bracket(e.get("bracket"))
                break

        # Average bracket excluding winner (only numeric brackets)
        others: List[float] = []
        for e in entries:
            if e.get("player") == winner:
                continue
            bb = _to_float_bracket(e.get("bracket"))
            if bb is not None:
                others.append(bb)

        if bw is None or not others:
            w = 1.0
        else:
            avg_other = sum(others) / len(others)
            delta = float(bw) - float(avg_other)
            w = _weight(delta)

        for e in entries:
            p = e.get("player") or ""
            c = e.get("commander") or ""
            b = e.get("bracket")

            # By player
            curp = by_player_w.get(p)
            if curp is None:
                curp = {"player": p, "wins": 0, "games": 0, "wins_w": 0.0, "games_w": 0.0}
                by_player_w[p] = curp
            curp["games"] += 1
            curp["games_w"] += w
            if p == winner:
                curp["wins"] += 1
                curp["wins_w"] += w

            # By player + commander + bracket
            key = (p, c, b)
            curpc = by_pair_w.get(key)
            if curpc is None:
                curpc = {"player": p, "commander": c, "bracket": b, "wins": 0, "games": 0, "wins_w": 0.0, "games_w": 0.0}
                by_pair_w[key] = curpc
            curpc["games"] += 1
            curpc["games_w"] += w
            if p == winner:
                curpc["wins"] += 1
                curpc["wins_w"] += w

    # Convert to lists and sort (similar to unweighted)
    by_player_weighted = list(by_player_w.values())
    by_player_weighted.sort(
        key=lambda r: (
            -float(r.get("games_w") or 0.0),
            -float(r.get("wins_w") or 0.0),
            str(r.get("player") or ""),
        )
    )

    by_player_commander_weighted = list(by_pair_w.values())
    by_player_commander_weighted.sort(
        key=lambda r: (
            -float(r.get("games_w") or 0.0),
            -float(r.get("wins_w") or 0.0),
            str(r.get("player") or ""),
            str(r.get("commander") or ""),
        )
    )

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
        "by_player_weighted": by_player_weighted,
        "by_player_commander_weighted": by_player_commander_weighted,
        "weighted": {
            "method": "delta_winner_minus_avg_table_excl_winner",
            "k": K,
            "w_min": W_MIN,
            "w_max": W_MAX,
        },
    }
