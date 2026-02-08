from __future__ import annotations

from typing import Any, Dict, List, Tuple
import datetime
import sqlite3
import math

def _rows_to_dicts(rows) -> List[Dict[str, Any]]:
    return [dict(r) for r in rows]


def _iso_utc_from_sqlite_dt(dt_str: str) -> str:
    """Convert a SQLite DATETIME string to ISO-8601 UTC with trailing 'Z'.

    The project DB stores played_at values like "YYYY-MM-DD HH:MM:SS".
    We keep the same moment but render it in a stable, explicit UTC form.
    """
    dt_str = (dt_str or "").strip()
    if not dt_str:
        return "1970-01-01T00:00:00Z"

    # Accept either "YYYY-MM-DD HH:MM:SS" or ISO-ish strings.
    try:
        if "T" in dt_str:
            dt = datetime.datetime.fromisoformat(dt_str.replace("Z", ""))
        else:
            dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    except Exception:
        # If parsing fails, fall back to a safe constant rather than
        # reintroducing non-determinism.
        return "1970-01-01T00:00:00Z"

    return dt.replace(microsecond=0).isoformat() + "Z"


def _deterministic_generated_utc(conn: sqlite3.Connection) -> str:
    """A deterministic 'generated_utc' tied to the DB content.

    Using the wall-clock time makes exports change on every run, which is noisy
    for Git commits. We instead use the most recent played_at in the DB.
    """
    cur = conn.cursor()
    cur.execute("SELECT MAX(played_at) AS max_played_at FROM game;")
    row = cur.fetchone()
    max_played_at = None
    if row is not None:
        # sqlite3.Row supports dict-style access in this project.
        try:
            max_played_at = row["max_played_at"]
        except Exception:
            max_played_at = row[0]
    return _iso_utc_from_sqlite_dt(max_played_at or "")

def compute_stats(conn: sqlite3.Connection, generated_utc: str | None = None) -> Dict[str, Any]:
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

    # --- Games list (for the static frontend) ---
    # Export a compact denormalized view of games + entries so the frontend can
    # render "last N games" without direct DB access.
    cur.execute(
        """
        SELECT
            g.id          AS game_id,
            g.played_at   AS played_at,
            g.notes       AS notes,
            g.winner_player AS winner_player,
            ge.player     AS player,
            ge.commander  AS commander,
            ge.bracket    AS bracket
        FROM game g
        JOIN gameentry ge ON ge.game_id = g.id
        ORDER BY
            COALESCE(g.played_at, '') DESC,
            g.id DESC,
            ge.id ASC
        """
    )
    _grows = _rows_to_dicts(cur.fetchall())
    games_detail_map: Dict[int, Dict[str, Any]] = {}
    for r in _grows:
        gid = int(r.get("game_id") or 0)
        g = games_detail_map.get(gid)
        if g is None:
            g = {
                "id": gid,
                "played_at": r.get("played_at"),
                "notes": r.get("notes"),
                "winner_player": r.get("winner_player"),
                "entries": [],
            }
            games_detail_map[gid] = g
        g["entries"].append(
            {
                "player": r.get("player"),
                "commander": r.get("commander"),
                "bracket": r.get("bracket"),
            }
        )
    # Keep order as in the query above.
    seen: set[int] = set()
    games_detail: List[Dict[str, Any]] = []
    for r in _grows:
        gid = int(r.get("game_id") or 0)
        if gid in seen:
            continue
        seen.add(gid)
        g = games_detail_map.get(gid)
        if g:
            games_detail.append(g)

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
        ORDER BY g.id ASC, ge.id ASC
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

    # --- Meta Wins: Winning Bracket Delta (WBD) ---
    # For each win, measure how far above/below the winner's bracket is compared
    # to the average bracket of the *other* players at the table.
    #
    #   d = b_winner - avg(brackets_others)
    #   WBD(player) = mean(d over that player's wins)
    #   WBD(commander) = mean(d over that commander's wins)
    #
    # We only include a win in WBD if we can compute both b_winner and the
    # average of other players' brackets (numeric, excluding winner).
    wbd_by_player: Dict[str, Dict[str, Any]] = {}
    wbd_by_player_commander: Dict[Tuple[str, str], Dict[str, Any]] = {}

    # --- Meta Profile: Meta Deviation Index (MDI) + Meta Pressure Index (MPI) ---
    # Independent of outcome, for each player and game:
    #   d = b_player - avg(brackets_other_players)  (excluding the player)
    #   MDI = mean(d)
    #   MPI = mean(|d|)
    # We only include a game in MDI/MPI if we can compute both b_player and
    # the average of other players' brackets (numeric, excluding player).
    meta_by_player: Dict[str, Dict[str, Any]] = {}
    meta_by_player_commander: Dict[Tuple[str, str], Dict[str, Any]] = {}

    # --- Over-Expected Win Rate (OEWR) ---
    # Signed performance above/below what we'd expect from relative bracket power.
    #
    # For each game with numeric brackets for *all* players:
    #   expected_p_i = softmax(k * bracket_i)
    #   residual_i = actual_win_i - expected_p_i
    #   OEWR(player) = mean(residual_i)
    #
    # Interpretation:
    #   OEWR > 0  -> player wins more often than expected given brackets
    #   OEWR < 0  -> player wins less often than expected given brackets
    #
    # We keep this inside the "meta profile" family because it is a per-table
    # context-aware normalization. The parameter k controls how strongly bracket
    # differences influence expected win probability.
    OEWR_K = 0.80

    # --- Commander calibration (CPR-Z + posterior bracket) ---
    # We treat each commander as a "hypothesis" about bracket strength.
    # CPR-Z aggregates per-appearance residuals (actual - expected) under
    # current brackets; B_post searches for a bracket shift that makes the
    # commander unbiased (mean residual ~ 0).
    calib_by_commander: Dict[str, Dict[str, Any]] = {}
    calib_occurrences: Dict[str, List[Tuple[str, float, Dict[str, float]]]] = {}
    calib_brackets_seen: Dict[str, List[int]] = {}

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

        avg_other = None
        delta_val = None
        if bw is None or not others:
            w = 1.0
        else:
            avg_other = sum(others) / len(others)
            delta_val = float(bw) - float(avg_other)
            w = _weight(delta_val)

        # --- Meta Wins (WBD) aggregation ---
        # Only the winner contributes, and only if we can compute delta.
        if winner:
            winner_commander = ""
            for e in entries:
                if e.get("player") == winner:
                    winner_commander = e.get("commander") or ""
                    break

            # By player
            curw = wbd_by_player.get(winner)
            if curw is None:
                curw = {"player": winner, "wins_total": 0, "wins_used": 0, "wbd_sum": 0.0}
                wbd_by_player[winner] = curw
            curw["wins_total"] += 1
            if delta_val is not None:
                curw["wins_used"] += 1
                curw["wbd_sum"] += float(delta_val)

            # By player + commander
            keyc = (winner, winner_commander)
            curc = wbd_by_player_commander.get(keyc)
            if curc is None:
                curc = {"player": winner, "commander": winner_commander, "wins_total": 0, "wins_used": 0, "wbd_sum": 0.0}
                wbd_by_player_commander[keyc] = curc
            curc["wins_total"] += 1
            if delta_val is not None:
                curc["wins_used"] += 1
                curc["wbd_sum"] += float(delta_val)

        # --- Meta Profile (MDI/MPI) aggregation ---
        # Every player contributes (independent of outcome). We compute deltas
        # using numeric brackets only and excluding the player from the table
        # average.
        sum_all = 0.0
        count_all = 0
        br_by_player: Dict[str, float] = {}
        for e in entries:
            p = e.get("player") or ""
            bb = _to_float_bracket(e.get("bracket"))
            if bb is None:
                continue
            br_by_player[p] = float(bb)
            sum_all += float(bb)
            count_all += 1

        # --- OEWR aggregation ---
        # Only compute when we have a complete numeric bracket vector.
        # (This avoids renormalizing away missing data.)
        can_oewr = (winner is not None) and (len(entries) > 0) and (count_all == len(entries)) and (winner in br_by_player)
        expected_by_player: Dict[str, float] = {}
        if can_oewr:
            # Stable softmax: subtract max before exp.
            bvals = list(br_by_player.values())
            bmax = max(bvals) if bvals else 0.0
            exps: Dict[str, float] = {}
            denom = 0.0
            for p, bp in br_by_player.items():
                ev = math.exp(OEWR_K * (float(bp) - float(bmax)))
                exps[p] = ev
                denom += ev
            if denom > 0.0:
                for p, ev in exps.items():
                    expected_by_player[p] = ev / denom
            else:
                can_oewr = False

        for e in entries:
            p = e.get("player") or ""
            c = e.get("commander") or ""

            # Track total games even when bracket is missing/unusable.
            curm = meta_by_player.get(p)
            if curm is None:
                curm = {
                    "player": p,
                    "games_total": 0,
                    "games_used": 0,
                    "mdi_sum": 0.0,
                    "mpi_sum": 0.0,
                    "oewr_used": 0,
                    "oewr_sum": 0.0,
                    "oewr_var_sum": 0.0,
                }
                meta_by_player[p] = curm
            curm["games_total"] += 1

            curmc = meta_by_player_commander.get((p, c))
            if curmc is None:
                curmc = {
                    "player": p,
                    "commander": c,
                    "games_total": 0,
                    "games_used": 0,
                    "mdi_sum": 0.0,
                    "mpi_sum": 0.0,
                    "oewr_used": 0,
                    "oewr_sum": 0.0,
                    "oewr_var_sum": 0.0,
                }
                meta_by_player_commander[(p, c)] = curmc
            curmc["games_total"] += 1

            bp = br_by_player.get(p)
            if bp is None:
                continue
            if count_all <= 1:
                continue
            sum_others = sum_all - float(bp)
            count_others = count_all - 1
            if count_others <= 0:
                continue
            avg_others = sum_others / float(count_others)
            d = float(bp) - float(avg_others)

            curm["games_used"] += 1
            curm["mdi_sum"] += d
            curm["mpi_sum"] += abs(d)

            curmc["games_used"] += 1
            curmc["mdi_sum"] += d
            curmc["mpi_sum"] += abs(d)

            # OEWR: residual vs expected probability (signed).
            if can_oewr:
                exp_p = expected_by_player.get(p)
                if exp_p is not None:
                    actual = 1.0 if p == winner else 0.0
                    residual = float(actual) - float(exp_p)
                    curm["oewr_used"] += 1
                    curm["oewr_sum"] += residual
                    curm["oewr_var_sum"] += float(exp_p) * (1.0 - float(exp_p))
                    curmc["oewr_used"] += 1
                    curmc["oewr_sum"] += residual
                    curmc["oewr_var_sum"] += float(exp_p) * (1.0 - float(exp_p))

                    # Commander calibration aggregation (per commander, not per player).
                    # Track how this commander performs vs expected given the table brackets.
                    curc = calib_by_commander.get(c)
                    if curc is None:
                        curc = {
                            "commander": c,
                            "games": 0,
                            "wins": 0,
                            "residual_sum": 0.0,
                            "var_sum": 0.0,
                        }
                        calib_by_commander[c] = curc
                    curc["games"] += 1
                    curc["wins"] += int(actual)

                    curc["residual_sum"] += residual
                    curc["var_sum"] += float(exp_p) * (1.0 - float(exp_p))

                    # Track brackets seen for this commander (should usually be constant).
                    bseen = calib_brackets_seen.get(c)
                    if bseen is None:
                        bseen = []
                        calib_brackets_seen[c] = bseen
                    try:
                        bint = int(float(bp))
                        if 1 <= bint <= 5:
                            bseen.append(bint)
                    except Exception:
                        pass

                    # Store per-appearance occurrence for posterior bracket search.
                    occ = calib_occurrences.get(c)
                    if occ is None:
                        occ = []
                        calib_occurrences[c] = occ
                    occ.append((p, float(actual), dict(br_by_player)))

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

    # --- Meta Wins (global): bracket -> wins / win_rate ---
    # We aggregate by bracket (not per-player) to keep it "meta".
    # This is useful to visualize correlation/trend between bracket (1-5)
    # and win rate.
    cur.execute(
        """
        SELECT
            ge.bracket AS bracket,
            COUNT(*) AS games,
            SUM(CASE WHEN g.winner_player = ge.player THEN 1 ELSE 0 END) AS wins
        FROM gameentry ge
        JOIN game g ON g.id = ge.game_id
        WHERE ge.bracket IS NOT NULL
        GROUP BY ge.bracket
        ORDER BY ge.bracket ASC
        """
    )
    _bb = _rows_to_dicts(cur.fetchall())
    meta_wins_by_bracket = []
    for r in _bb:
        try:
            b = int(r.get("bracket"))
        except Exception:
            # Skip non-numeric brackets
            continue
        games_n = int(r.get("games") or 0)
        wins_n = int(r.get("wins") or 0)
        win_rate = (wins_n / games_n) if games_n > 0 else None
        meta_wins_by_bracket.append(
            {
                "bracket": b,
                "games": games_n,
                "wins": wins_n,
                "win_rate": win_rate,
            }
        )

    
    # Commander win rate by (fixed) bracket (global, not by player)
    # Each point represents a commander; bracket is expected to be numeric (1..5).
    cur.execute(
        """
        SELECT
            ge.commander AS commander,
            ge.bracket   AS bracket,
            COUNT(*)     AS games,
            SUM(CASE WHEN g.winner_player = ge.player THEN 1 ELSE 0 END) AS wins
        FROM gameentry ge
        JOIN game g ON g.id = ge.game_id
        WHERE ge.commander IS NOT NULL AND ge.commander != ''
          AND ge.bracket IS NOT NULL
        GROUP BY ge.commander, ge.bracket
        HAVING COUNT(*) >= 3
        ORDER BY ge.bracket ASC, ge.commander ASC
        """
    )
    _cb = _rows_to_dicts(cur.fetchall())
    meta_wins_commander_winrate = []
    for r in _cb:
        commander = (r.get("commander") or "").strip()
        try:
            b = int(r.get("bracket"))
        except Exception:
            continue
        games_n = int(r.get("games") or 0)
        wins_n = int(r.get("wins") or 0)
        if not commander or games_n <= 0:
            continue
        win_rate = wins_n / games_n
        meta_wins_commander_winrate.append(
            {
                "commander": commander,
                "bracket": b,
                "games": games_n,
                "wins": wins_n,
                "win_rate": win_rate,
            }
        )

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

    if generated_utc is None:
        generated_utc = _deterministic_generated_utc(conn)

    # Finalize meta wins outputs (WBD)
    meta_wins_by_player = []
    for r in wbd_by_player.values():
        used = int(r.get("wins_used") or 0)
        wbd = (float(r.get("wbd_sum") or 0.0) / used) if used > 0 else None
        meta_wins_by_player.append(
            {
                "player": r.get("player") or "",
                "wins_total": int(r.get("wins_total") or 0),
                "wins_used": used,
                "wbd": wbd,
            }
        )
    meta_wins_by_player.sort(
        key=lambda r: (
            # Put players with no usable wins at the bottom
            1 if r.get("wbd") is None else 0,
            -abs(float(r.get("wbd") or 0.0)),
            -int(r.get("wins_used") or 0),
            str(r.get("player") or ""),
        )
    )

    meta_wins_by_player_commander = []
    for r in wbd_by_player_commander.values():
        used = int(r.get("wins_used") or 0)
        wbd = (float(r.get("wbd_sum") or 0.0) / used) if used > 0 else None
        meta_wins_by_player_commander.append(
            {
                "player": r.get("player") or "",
                "commander": r.get("commander") or "",
                "wins_total": int(r.get("wins_total") or 0),
                "wins_used": used,
                "wbd": wbd,
            }
        )
    meta_wins_by_player_commander.sort(
        key=lambda r: (
            str(r.get("player") or ""),
            # put usable first
            1 if r.get("wbd") is None else 0,
            -int(r.get("wins_used") or 0),
            -abs(float(r.get("wbd") or 0.0)),
            str(r.get("commander") or ""),
        )
    )

    # Finalize meta profile outputs (MDI/MPI)
    meta_profile_by_player = []
    for r in meta_by_player.values():
        used = int(r.get("games_used") or 0)
        used_oewr = int(r.get("oewr_used") or 0)
        mdi = (float(r.get("mdi_sum") or 0.0) / used) if used > 0 else None
        mpi = (float(r.get("mpi_sum") or 0.0) / used) if used > 0 else None
        oewr = (float(r.get("oewr_sum") or 0.0) / used_oewr) if used_oewr > 0 else None
        var_sum = float(r.get("oewr_var_sum") or 0.0)
        oewr_z = (float(r.get("oewr_sum") or 0.0) / math.sqrt(var_sum)) if var_sum > 0.0 else None

        meta_profile_by_player.append(
            {
                "player": r.get("player") or "",
                "games_total": int(r.get("games_total") or 0),
                "games_used": used,
                "oewr_used": used_oewr,
                "mdi": mdi,
                "mpi": mpi,
                "oewr": oewr,
                "oewr_z": oewr_z,
            }
        )
    meta_profile_by_player.sort(
        key=lambda r: (
            1 if r.get("mdi") is None else 0,
            -int(r.get("games_used") or 0),
            -float(r.get("mpi") or 0.0),
            str(r.get("player") or ""),
        )
    )

    meta_profile_by_player_commander = []
    for r in meta_by_player_commander.values():
        used = int(r.get("games_used") or 0)
        used_oewr = int(r.get("oewr_used") or 0)
        mdi = (float(r.get("mdi_sum") or 0.0) / used) if used > 0 else None
        mpi = (float(r.get("mpi_sum") or 0.0) / used) if used > 0 else None
        oewr = (float(r.get("oewr_sum") or 0.0) / used_oewr) if used_oewr > 0 else None
        var_sum = float(r.get("oewr_var_sum") or 0.0)
        oewr_z = (float(r.get("oewr_sum") or 0.0) / math.sqrt(var_sum)) if var_sum > 0.0 else None

        meta_profile_by_player_commander.append(
            {
                "player": r.get("player") or "",
                "commander": r.get("commander") or "",
                "games_total": int(r.get("games_total") or 0),
                "games_used": used,
                "oewr_used": used_oewr,
                "mdi": mdi,
                "mpi": mpi,
                "oewr": oewr,
                "oewr_z": oewr_z,
            }
        )
    meta_profile_by_player_commander.sort(
        key=lambda r: (
            str(r.get("player") or ""),
            1 if r.get("mdi") is None else 0,
            -int(r.get("games_used") or 0),
            -float(r.get("mpi") or 0.0),
            str(r.get("commander") or ""),
        )
    )

    
    # --- Commander bracket calibration output ---
    def _mode_int(vals: List[int]) -> int | None:
        if not vals:
            return None
        counts: Dict[int, int] = {}
        for v in vals:
            counts[v] = counts.get(v, 0) + 1
        # highest count then smallest value
        return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]

    commander_calibration = []
    # Posterior bracket search grid (quarter brackets)
    BPOST_STEP = 0.25
    BPOST_MIN = 1.0
    BPOST_MAX = 5.0

    def _expected_probs_with_override(br_map: Dict[str, float], override_player: str, override_b: float) -> Dict[str, float] | None:
        # Stable softmax; returns None if denom is 0
        bvals = []
        for p, b in br_map.items():
            bvals.append(float(override_b) if p == override_player else float(b))
        bmax = max(bvals) if bvals else 0.0
        exps: Dict[str, float] = {}
        denom = 0.0
        for p, b in br_map.items():
            bb = float(override_b) if p == override_player else float(b)
            ev = math.exp(OEWR_K * (bb - float(bmax)))
            exps[p] = ev
            denom += ev
        if denom <= 0.0:
            return None
        return {p: (ev / denom) for p, ev in exps.items()}

    for c, curc in calib_by_commander.items():
        games_c = int(curc.get("games") or 0)
        wins_c = int(curc.get("wins") or 0)
        var_sum_c = float(curc.get("var_sum") or 0.0)
        cpr_z = (float(curc.get("residual_sum") or 0.0) / math.sqrt(var_sum_c)) if var_sum_c > 0.0 else None

        prior_mode = _mode_int(calib_brackets_seen.get(c) or [])
        bracket_prior = prior_mode

        # Posterior bracket estimation (quarter steps)
        #
        # Bayesian view (lightweight, deterministic): treat each appearance of a
        # commander as a Bernoulli outcome for the pilot player (win / not-win),
        # with success probability given by the same softmax model used for OEWR.
        #
        #   p(win | theta) = softmax_k(brackets with pilot overridden to theta)[pilot]
        #
        # Posterior on a fixed grid theta∈[1,5] with step 0.25:
        #   log post(theta) ∝ log prior(theta) + Σ_i log Bernoulli(y_i; p_i(theta))
        #
        # We then report b_post as the posterior mean E[theta|D].
        b_post = None
        b_post_sd = None
        b_post_map = None
        occ = calib_occurrences.get(c) or []
        if occ:
            # Deterministic posterior on a fixed grid
            steps = int(round((BPOST_MAX - BPOST_MIN) / BPOST_STEP))

            # Prior: weakly concentrate around the modal declared bracket if available,
            # otherwise use a broad prior centered at 3.
            prior_mu = float(bracket_prior) if bracket_prior is not None else 3.0
            prior_sigma = 0.90  # broad, to let data dominate quickly

            def _log_prior(theta: float) -> float:
                # Truncated-normal-shaped prior (up to an additive constant)
                z = (theta - prior_mu) / prior_sigma
                return -0.5 * (z * z)

            def _log_bernoulli(y: float, p: float) -> float:
                # Clamp for numerical safety; keeps determinism
                pp = min(max(float(p), 1e-12), 1.0 - 1e-12)
                if float(y) >= 0.5:
                    return math.log(pp)
                return math.log(1.0 - pp)

            cand_thetas: List[float] = []
            log_posts: List[float] = []
            for si in range(steps + 1):
                theta = BPOST_MIN + si * BPOST_STEP
                lp = _log_prior(theta)
                # Likelihood: pilot win / not-win under softmax model
                used = 0
                for (p_c, actual_c, br_map) in occ:
                    probs = _expected_probs_with_override(br_map, p_c, theta)
                    if probs is None:
                        continue
                    pwin = probs.get(p_c)
                    if pwin is None:
                        continue
                    lp += _log_bernoulli(float(actual_c), float(pwin))
                    used += 1
                if used <= 0:
                    continue
                cand_thetas.append(float(theta))
                log_posts.append(float(lp))

            if cand_thetas:
                # Normalize with log-sum-exp
                m = max(log_posts)
                exps = [math.exp(lp - m) for lp in log_posts]
                z = sum(exps)
                if z > 0.0:
                    ws = [e / z for e in exps]
                    # Posterior mean / sd
                    mean = sum(w * t for (w, t) in zip(ws, cand_thetas))
                    var = sum(w * (t - mean) ** 2 for (w, t) in zip(ws, cand_thetas))
                    b_post = float(mean)
                    b_post_sd = float(math.sqrt(var))
                    # MAP (useful for debugging / UX if desired)
                    imax = max(range(len(log_posts)), key=lambda i: log_posts[i])
                    b_post_map = float(cand_thetas[imax])

        commander_calibration.append(
            {
                "commander": c,
                "bracket_prior": bracket_prior,
                "b_post": b_post,
                "b_post_sd": b_post_sd,
                "b_post_map": b_post_map,
                "games": games_c,
                "wins": wins_c,
                "cpr_z": cpr_z,
            }
        )
    commander_calibration.sort(
        key=lambda r: (
            1 if r.get("cpr_z") is None else 0,
            -abs(float(r.get("cpr_z") or 0.0)),
            -int(r.get("games") or 0),
            str(r.get("commander") or ""),
        )
    )

    return {
            "version": "v1",
            "generated_utc": generated_utc,
            "counts": {"games": n_games, "entries": n_entries},
            "filters": {"players": players, "commanders": commanders, "brackets": brackets},
            # Full games list (new in v1 output, backward compatible)
            "games": games_detail,
            "by_player": by_player,
            "by_player_commander": by_player_commander,
            "commander_calibration": commander_calibration,
            "meta_profile": {
                "method": "delta_player_minus_avg_table_excl_player",
                "oewr_method": "softmax_expected_win_residual",
                "oewr_k": OEWR_K,
                "saturation_mdi": {"min": -1.0, "max": 1.0},
                "min_games_default": 3,
            },
            "meta_profile_by_player": meta_profile_by_player,
            "meta_profile_by_player_commander": meta_profile_by_player_commander,
        }
