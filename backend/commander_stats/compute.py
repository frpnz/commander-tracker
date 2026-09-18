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


def _pod_sizes(conn: sqlite3.Connection) -> List[int]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT pod_size
        FROM (
            SELECT g.id AS game_id, COUNT(ge.id) AS pod_size
            FROM game g
            JOIN gameentry ge ON ge.game_id = g.id
            GROUP BY g.id
        ) x
        GROUP BY pod_size
        ORDER BY pod_size ASC
        """
    )
    out: List[int] = []
    for r in cur.fetchall():
        try:
            v = int(r["pod_size"])
        except Exception:
            try:
                v = int(r[0])
            except Exception:
                continue
        if v > 0:
            out.append(v)
    return out


def _filtered_connection_by_pod_size(conn: sqlite3.Connection, pod_size: int) -> sqlite3.Connection:
    """Return an in-memory copy containing only games with the requested player count."""
    mem = sqlite3.connect(":memory:")
    mem.row_factory = sqlite3.Row
    conn.backup(mem)
    cur = mem.cursor()
    cur.execute("PRAGMA foreign_keys = OFF;")
    cur.execute(
        """
        CREATE TEMP TABLE _keep_game_ids AS
        SELECT g.id AS id
        FROM game g
        JOIN gameentry ge ON ge.game_id = g.id
        GROUP BY g.id
        HAVING COUNT(ge.id) = ?
        """,
        (int(pod_size),),
    )
    cur.execute("DELETE FROM gameentry WHERE game_id NOT IN (SELECT id FROM _keep_game_ids);")
    cur.execute("DELETE FROM game WHERE id NOT IN (SELECT id FROM _keep_game_ids);")
    cur.execute("DROP TABLE _keep_game_ids;")
    mem.commit()
    return mem




def _filtered_connection_by_multiplayer_only(conn: sqlite3.Connection) -> sqlite3.Connection:
    """Return an in-memory copy containing only multiplayer games (3+ players)."""
    mem = sqlite3.connect(":memory:")
    mem.row_factory = sqlite3.Row
    conn.backup(mem)
    cur = mem.cursor()
    cur.execute("PRAGMA foreign_keys = OFF;")
    cur.execute(
        """
        CREATE TEMP TABLE _keep_game_ids AS
        SELECT g.id AS id
        FROM game g
        JOIN gameentry ge ON ge.game_id = g.id
        GROUP BY g.id
        HAVING COUNT(ge.id) >= 3
        """
    )
    cur.execute("DELETE FROM gameentry WHERE game_id NOT IN (SELECT id FROM _keep_game_ids);")
    cur.execute("DELETE FROM game WHERE id NOT IN (SELECT id FROM _keep_game_ids);")
    cur.execute("DROP TABLE _keep_game_ids;")
    mem.commit()
    return mem


def compute_stats(conn: sqlite3.Connection, generated_utc: str | None = None, *, include_player_count_splits: bool = True) -> Dict[str, Any]:
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

    pod_sizes = _pod_sizes(conn)

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
                "pod_size": 0,
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
            g["pod_size"] = len(g.get("entries") or [])
            games_detail.append(g)

    # Numeric bracket helper shared by meta-profile and calibration metrics.
    def _to_float_bracket(v):
        if v is None or v == "":
            return None
        try:
            return float(v)
        except Exception:
            return None

    # Build a per-game view used by the context-aware metrics below.
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

    if generated_utc is None:
        generated_utc = _deterministic_generated_utc(conn)

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

    payload = {
            "version": "v1",
            "generated_utc": generated_utc,
            "counts": {"games": n_games, "entries": n_entries},
            "filters": {"players": players, "commanders": commanders, "brackets": brackets, "pod_sizes": pod_sizes},
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

    if include_player_count_splits:
        by_player_count: Dict[str, Dict[str, Any]] = {}

        # Special aggregate used by the frontend filter: all multiplayer Commander
        # pods, excluding 1v1/two-player games. Keep it next to numeric splits so
        # every page can switch datasets without recalculating metrics client-side.
        sub_multi = _filtered_connection_by_multiplayer_only(conn)
        try:
            by_player_count["multiplayer"] = compute_stats(
                sub_multi,
                generated_utc=generated_utc,
                include_player_count_splits=False,
            )
        finally:
            sub_multi.close()

        for pod_size in pod_sizes:
            sub = _filtered_connection_by_pod_size(conn, pod_size)
            try:
                by_player_count[str(pod_size)] = compute_stats(
                    sub,
                    generated_utc=generated_utc,
                    include_player_count_splits=False,
                )
            finally:
                sub.close()
        payload["by_player_count"] = by_player_count

    return payload
