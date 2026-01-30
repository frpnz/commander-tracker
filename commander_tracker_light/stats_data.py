from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from sqlmodel import Session, select

from commander_tracker_light.db import (
    Game,
    GameEntry,
    bpi_label,
    build_entries_by_game,
    compute_table_bracket_avg,
    win_weight_from_delta,
)


def build_stats_dataset(
    session: Session,
    *,
    top_triples: int = 50,
    max_unique: int = 200,
) -> dict:
    """Build the data used by the /stats page, but as a JSON-ready dict.

    Notes
    - This intentionally keeps all *numeric outcomes* computed in Python.
    - The static frontend may slice / filter / sort, but should not recompute
      domain stats from raw games.
    """

    # sanitize the same way the route does
    try:
        top_triples = int(top_triples)
    except Exception:
        top_triples = 50
    top_triples = max(10, min(500, top_triples))

    try:
        max_unique = int(max_unique)
    except Exception:
        max_unique = 200
    max_unique = max(10, min(5000, max_unique))

    games = session.exec(select(Game)).all()
    entries = session.exec(select(GameEntry)).all()

    entries_by_game = build_entries_by_game(entries)
    participants_by_game: Dict[int, int] = {gid: len(es) for gid, es in entries_by_game.items()}
    sizes = sorted({n for n in participants_by_game.values() if n > 0})

    winner_by_game: Dict[int, Optional[str]] = {g.id: g.winner_player for g in games if g.id is not None}

    # overall
    player_games: Dict[str, set] = {}
    player_wins: Dict[str, int] = {}
    player_commanders: Dict[str, set] = {}
    player_commander_counts: Dict[Tuple[str, str], int] = {}

    pair_games: Dict[Tuple[str, str], set] = {}
    pair_wins: Dict[Tuple[str, str], int] = {}

    # per pod-size
    player_by_size: Dict[Tuple[str, int], Dict[str, object]] = {}
    pair_by_size: Dict[Tuple[str, str, int], Dict[str, object]] = {}

    for gid, es in entries_by_game.items():
        n = participants_by_game.get(gid, 0)
        winner = winner_by_game.get(gid)

        for e in es:
            p, c = e.player, e.commander

            # overall
            player_games.setdefault(p, set()).add(gid)
            player_commanders.setdefault(p, set()).add(c)
            key = (p, c)
            player_commander_counts[key] = player_commander_counts.get(key, 0) + 1
            pair_games.setdefault(key, set()).add(gid)

            if winner and winner == p:
                player_wins[p] = player_wins.get(p, 0) + 1
                pair_wins[key] = pair_wins.get(key, 0) + 1

            # per size: player
            pk = (p, n)
            player_by_size.setdefault(pk, {"games": set(), "wins": 0})
            player_by_size[pk]["games"].add(gid)
            if winner and winner == p:
                player_by_size[pk]["wins"] += 1

            # per size: player+commander
            ck = (p, c, n)
            pair_by_size.setdefault(ck, {"games": set(), "wins": 0})
            pair_by_size[ck]["games"].add(gid)
            if winner and winner == p:
                pair_by_size[ck]["wins"] += 1

    # overall tables
    player_rows: List[dict] = []
    for p, gset in player_games.items():
        games_n = len(gset)
        wins_n = player_wins.get(p, 0)
        winrate = (wins_n / games_n * 100.0) if games_n else 0.0

        best_commander = None
        best_count = -1
        for (pp, cc), cnt in player_commander_counts.items():
            if pp == p and cnt > best_count:
                best_count, best_commander = cnt, cc

        player_rows.append(
            {
                "player": p,
                "games": games_n,
                "wins": wins_n,
                "winrate": winrate,
                "unique_commanders": len(player_commanders.get(p, set())),
                "top_commander": best_commander,
                "top_commander_games": best_count if best_count >= 0 else 0,
            }
        )
    player_rows.sort(key=lambda r: (-r["games"], r["player"].lower()))

    pair_rows: List[dict] = []
    for (p, c), gset in pair_games.items():
        games_n = len(gset)
        wins_n = pair_wins.get((p, c), 0)
        winrate = (wins_n / games_n * 100.0) if games_n else 0.0
        pair_rows.append({"player": p, "commander": c, "games": games_n, "wins": wins_n, "winrate": winrate})
    pair_rows.sort(key=lambda r: (-r["games"], r["player"].lower(), r["commander"].lower()))

    # per size tables
    player_by_size_tables: Dict[int, List[dict]] = {}
    pair_by_size_tables: Dict[int, List[dict]] = {}

    for n in sizes:
        prow = []
        for (p, nn), v in player_by_size.items():
            if nn != n:
                continue
            games_n = len(v["games"])
            wins_n = int(v["wins"])
            winrate = (wins_n / games_n * 100.0) if games_n else 0.0
            prow.append({"player": p, "games": games_n, "wins": wins_n, "winrate": winrate})
        prow.sort(key=lambda r: (-r["games"], r["player"].lower()))
        player_by_size_tables[n] = prow

        crow = []
        for (p, c, nn), v in pair_by_size.items():
            if nn != n:
                continue
            games_n = len(v["games"])
            wins_n = int(v["wins"])
            winrate = (wins_n / games_n * 100.0) if games_n else 0.0
            crow.append({"player": p, "commander": c, "games": games_n, "wins": wins_n, "winrate": winrate})
        crow.sort(key=lambda r: (-r["games"], r["player"].lower(), r["commander"].lower()))
        pair_by_size_tables[n] = crow

    # -----------------------------
    # Bracket stats (descriptive)
    # -----------------------------
    bracket_entry_counts: Dict[str, int] = {}
    for e in entries:
        k = str(e.bracket) if e.bracket is not None else "n/a"
        bracket_entry_counts[k] = bracket_entry_counts.get(k, 0) + 1

    # Compute table average bracket per game (ignoring n/a) and winner bracket
    table_avg_by_game: Dict[int, Optional[float]] = {}
    winner_bracket_by_game: Dict[int, Optional[int]] = {}
    for gid, es in entries_by_game.items():
        try:
            table_avg_by_game[gid] = compute_table_bracket_avg(es)
        except Exception:
            table_avg_by_game[gid] = None

        w = winner_by_game.get(gid)
        bw = None
        if w:
            for e in es:
                if e.player == w:
                    bw = e.bracket
                    break
        winner_bracket_by_game[gid] = bw

    bracket_winner_counts: Dict[str, int] = {}
    for gid, bw in winner_bracket_by_game.items():
        k = str(bw) if bw is not None else "n/a"
        bracket_winner_counts[k] = bracket_winner_counts.get(k, 0) + 1

    # Winrate by bracket (overall across entries)
    bracket_games: Dict[str, set] = {}
    bracket_wins: Dict[str, int] = {}
    for gid, es in entries_by_game.items():
        w = winner_by_game.get(gid)
        for e in es:
            k = str(e.bracket) if e.bracket is not None else "n/a"
            bracket_games.setdefault(k, set()).add(gid)
            if w and w == e.player:
                bracket_wins[k] = bracket_wins.get(k, 0) + 1

    bracket_rows: List[dict] = []
    for k in sorted(bracket_games.keys(), key=lambda x: (x == "n/a", x)):
        g = len(bracket_games[k])
        w = int(bracket_wins.get(k, 0))
        wr = (w / g * 100.0) if g else 0.0
        bracket_rows.append({"bracket": k, "games": g, "wins": w, "winrate": wr})

    # Unique triples (Commander, Player, Bracket) as a simple data-hygiene list
    unique_triples_counts: Dict[Tuple[str, str, str], int] = {}
    for e in entries:
        bkey = str(e.bracket) if e.bracket is not None else "n/a"
        key = (e.commander, e.player, bkey)
        unique_triples_counts[key] = unique_triples_counts.get(key, 0) + 1

    unique_triples_rows = [
        {"commander": c, "player": p, "bracket": b, "entries": cnt}
        for (c, p, b), cnt in unique_triples_counts.items()
    ]
    unique_triples_rows.sort(
        key=lambda r: (r["commander"].lower(), r["player"].lower(), (r["bracket"] == "n/a", r["bracket"]))
    )
    unique_triples_rows = unique_triples_rows[:max_unique]

    # Triples (player, commander, bracket) descriptive table
    triples: Dict[Tuple[str, str, str], Dict[str, object]] = {}
    for gid, es in entries_by_game.items():
        w = winner_by_game.get(gid)
        bavg = table_avg_by_game.get(gid)

        for e in es:
            bkey = str(e.bracket) if e.bracket is not None else "n/a"
            key = (e.player, e.commander, bkey)
            rec = triples.setdefault(
                key,
                {
                    "games": set(),
                    "wins": 0,
                    "weighted_wins": 0.0,
                    "weighted_games": 0.0,
                    "deltas": [],
                    "table_avgs": [],
                },
            )
            rec["games"].add(gid)
            rec["weighted_games"] += 1.0
            if bavg is not None:
                rec["table_avgs"].append(float(bavg))

            if w and w == e.player:
                rec["wins"] += 1
                if (e.bracket is not None) and (bavg is not None):
                    delta = float(e.bracket) - float(bavg)
                    rec["deltas"].append(delta)
                    w_eff = float(win_weight_from_delta(delta))
                    rec["weighted_wins"] += w_eff
                    rec["weighted_games"] += (w_eff - 1.0)
                else:
                    rec["weighted_wins"] += 1.0

    triple_rows: List[dict] = []
    for (p, c, b), rec in triples.items():
        games_n = len(rec["games"])
        wins_n = int(rec["wins"])
        wr = (wins_n / games_n * 100.0) if games_n else 0.0

        ww = float(rec["weighted_wins"])
        wg = float(rec.get("weighted_games") or games_n)
        wwr = (ww / wg * 100.0) if wg else 0.0

        deltas = rec["deltas"]
        bpi = (sum(deltas) / len(deltas)) if deltas else None
        bpi_q = bpi_label(bpi) if bpi is not None else "n/a"
        cov = (len(deltas) / wins_n * 100.0) if wins_n else None

        tavgs = rec["table_avgs"]
        avg_table = (sum(tavgs) / len(tavgs)) if tavgs else None

        triple_rows.append(
            {
                "player": p,
                "commander": c,
                "bracket": b,
                "games": games_n,
                "wins": wins_n,
                "winrate": wr,
                "weighted_wr": wwr,
                "bpi": bpi,
                "bpi_label": bpi_q,
                "delta_coverage": cov,
                "avg_table_bracket": avg_table,
            }
        )

    triple_rows.sort(
        key=lambda r: (
            -r["games"],
            -(r["weighted_wr"] or 0.0),
            -(r["winrate"] or 0.0),
            r["player"].lower(),
            r["commander"].lower(),
        )
    )
    triple_rows = triple_rows[:top_triples]

    # final payload
    return {
        "schema": "stats.v1",
        "sizes": sizes,
        "player_rows": player_rows,
        "pair_rows": pair_rows,
        "player_by_size_tables": {str(k): v for k, v in player_by_size_tables.items()},
        "pair_by_size_tables": {str(k): v for k, v in pair_by_size_tables.items()},
        "bracket_entry_counts": bracket_entry_counts,
        "bracket_winner_counts": bracket_winner_counts,
        "bracket_rows": bracket_rows,
        "unique_triples_rows": unique_triples_rows,
        "triple_rows": triple_rows,
        "limits": {"top_triples": top_triples, "max_unique": max_unique},
    }
