from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlmodel import Session, select

from app import Game, GameEntry


def build_dashboard_dataset(session: Session) -> dict:
    """Build a data-first dataset for the Dashboard page.

    The goal is to let GitHub Pages render charts client-side and let the user
    tweak *view parameters* (min games, top N, selected player) without
    re-running backend rendering.

    IMPORTANT: This function pre-computes only base metrics (games, wins,
    winrate, time-series points). Any filtering/sorting/top-N can be done in JS.
    """

    games: List[Game] = session.exec(select(Game)).all()
    entries: List[GameEntry] = session.exec(select(GameEntry)).all()

    # game_id -> entries
    entries_by_game: Dict[int, List[GameEntry]] = defaultdict(list)
    for e in entries:
        entries_by_game[e.game_id].append(e)

    participants_by_game: Dict[int, int] = {gid: len(es) for gid, es in entries_by_game.items()}
    winner_by_game: Dict[int, Optional[str]] = {g.id: g.winner_player for g in games if g.id is not None}
    game_time_by_id: Dict[int, datetime] = {g.id: g.played_at for g in games if g.id is not None}

    # players
    games_by_player: Dict[str, set] = defaultdict(set)
    for e in entries:
        games_by_player[e.player].add(e.game_id)
    players = sorted(games_by_player.keys(), key=lambda x: x.lower())

    # wins per player
    wins_by_player: Dict[str, int] = defaultdict(int)
    for g in games:
        if g.winner_player:
            wins_by_player[g.winner_player] += 1

    # player stats
    player_stats: List[dict] = []
    for p in players:
        games_n = len(games_by_player[p])
        wins_n = int(wins_by_player.get(p, 0))
        wr = (wins_n / games_n) * 100.0 if games_n else 0.0
        player_stats.append({"player": p, "games": games_n, "wins": wins_n, "winrate": round(wr, 1)})

    # pair stats
    pair_stats: Dict[Tuple[str, str], Dict[str, object]] = {}
    for gid, es in entries_by_game.items():
        winner = winner_by_game.get(gid)
        for e in es:
            key = (e.player, e.commander)
            pair_stats.setdefault(key, {"games": set(), "wins": 0})
            pair_stats[key]["games"].add(gid)
            if winner and winner == e.player:
                pair_stats[key]["wins"] += 1

    pair_rows: List[dict] = []
    for (p, c), v in pair_stats.items():
        games_n = len(v["games"])
        wins_n = int(v["wins"])
        wr = (wins_n / games_n) * 100.0 if games_n else 0.0
        pair_rows.append({"player": p, "commander": c, "games": games_n, "wins": wins_n, "winrate": round(wr, 1)})

    # commander stats
    cmd_stats: Dict[str, Dict[str, object]] = {}
    for gid, es in entries_by_game.items():
        winner = winner_by_game.get(gid)
        for e in es:
            c = e.commander
            cmd_stats.setdefault(c, {"games": set(), "wins": 0})
            cmd_stats[c]["games"].add(gid)
            if winner and winner == e.player:
                cmd_stats[c]["wins"] += 1

    commander_rows: List[dict] = []
    for c, v in cmd_stats.items():
        games_n = len(v["games"])
        wins_n = int(v["wins"])
        wr = (wins_n / games_n) * 100.0 if games_n else 0.0
        commander_rows.append({"commander": c, "games": games_n, "wins": wins_n, "winrate": round(wr, 1)})

    # pod stats: precompute for __all__ and for each player
    # __all__: participations counts as "n seats" (matches current behavior)
    pod_all: Dict[int, Dict[str, int]] = defaultdict(lambda: {"participations": 0, "wins": 0})
    for gid, es in entries_by_game.items():
        n = participants_by_game.get(gid, 0)
        if n <= 0:
            continue
        pod_all[n]["participations"] += n
        if winner_by_game.get(gid):
            pod_all[n]["wins"] += 1

    pod_by_player: Dict[str, Dict[int, Dict[str, int]]] = {
        p: defaultdict(lambda: {"participations": 0, "wins": 0}) for p in players
    }
    for gid, es in entries_by_game.items():
        n = participants_by_game.get(gid, 0)
        if n <= 0:
            continue
        winner = winner_by_game.get(gid)
        players_in_game = {e.player for e in es}
        for p in players_in_game:
            if p not in pod_by_player:
                continue
            pod_by_player[p][n]["participations"] += 1
            if winner and winner == p:
                pod_by_player[p][n]["wins"] += 1

    # trend points for each player (cumulative WR over time)
    trend_by_player: Dict[str, Dict[str, list]] = {}
    for p in players:
        gp = sorted(
            [gid for gid, es in entries_by_game.items() if any(e.player == p for e in es)],
            key=lambda gid: game_time_by_id.get(gid, datetime.min),
        )
        labels: List[str] = []
        values: List[float] = []
        total = 0
        wins = 0
        for gid in gp:
            total += 1
            if winner_by_game.get(gid) == p:
                wins += 1
            wr = (wins / total) * 100.0 if total else 0.0
            dt = game_time_by_id.get(gid)
            label = dt.strftime("%Y-%m-%d") if dt else f"game {gid}"
            labels.append(label)
            values.append(round(wr, 1))
        trend_by_player[p] = {"labels": labels, "values": values}

    # dimensions for UI
    pod_sizes = sorted({*pod_all.keys(), *{k for d in pod_by_player.values() for k in d.keys()}})

    return {
        "schema": "dashboard.v1",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "dimensions": {
            "players": players,
            "pod_sizes": pod_sizes,
        },
        "player_stats": player_stats,
        "pair_stats": pair_rows,
        "commander_stats": commander_rows,
        "pod_stats": {
            "__all__": {str(n): pod_all[n] for n in pod_all},
            "by_player": {p: {str(n): pod_by_player[p][n] for n in pod_by_player[p]} for p in players},
        },
        "trend": trend_by_player,
    }
