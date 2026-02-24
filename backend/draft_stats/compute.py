from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .db import connect, ensure_schema

SCHEMA_VERSION = "draft.v1"


def _parse_dt(s: str) -> datetime:
    # Stored like "YYYY-MM-DD HH:MM:SS" or ISO.
    ss = (s or "").strip().replace("T", " ")
    try:
        return datetime.fromisoformat(ss)
    except ValueError:
        return datetime.fromisoformat(ss[:19])


def compute_draft(db_path: str) -> dict[str, Any]:
    conn = connect(db_path)
    ensure_schema(conn)

    tournaments_rows = conn.execute(
        "SELECT id, played_at, name, format, rounds, notes FROM tournament ORDER BY played_at DESC, id DESC"
    ).fetchall()

    tournaments: list[dict[str, Any]] = []
    by_player: dict[str, dict[str, Any]] = {}

    max_played_at: datetime | None = None

    for t in tournaments_rows:
        tid = int(t["id"])
        played_at = str(t["played_at"])
        dt = _parse_dt(played_at)
        if (max_played_at is None) or (dt > max_played_at):
            max_played_at = dt

        standings_rows = conn.execute(
            """
            SELECT player, wins, losses, draws, via_pct
            FROM standing
            WHERE tournament_id = ?
            ORDER BY wins DESC, draws DESC, via_pct DESC, player ASC
            """,
            (tid,),
        ).fetchall()

        standings: list[dict[str, Any]] = []
        for r in standings_rows:
            player = str(r["player"]).strip()
            w = int(r["wins"])
            l = int(r["losses"])
            d = int(r["draws"])
            via = r["via_pct"]
            total = w + l + d
            mwp = (w + 0.5 * d) / total if total > 0 else None

            standings.append(
                {
                    "player": player,
                    "record": {"w": w, "l": l, "d": d},
                    "matches": total,
                    "match_win_pct": mwp,
                    "via_pct": float(via) if via is not None else None,
                }
            )

            p = by_player.setdefault(
                player,
                {
                    "player": player,
                    "tournaments": 0,
                    "matches": 0,
                    "wins": 0,
                    "losses": 0,
                    "draws": 0,
                    "match_win_pct": None,
                    "via_avg": None,
                    "via_n": 0,
                    "best_rank": None,
                    "avg_rank": None,
                    "_rank_sum": 0,
                },
            )

            p["tournaments"] += 1
            p["matches"] += total
            p["wins"] += w
            p["losses"] += l
            p["draws"] += d
            if via is not None:
                p["via_n"] += 1
                p["via_avg"] = (p["via_avg"] or 0.0) + float(via)

        # Compute ranks based on ordering we selected
        for idx, s in enumerate(standings, start=1):
            s["rank"] = idx
            # aggregate ranks
            player = s["player"]
            p = by_player[player]
            p["_rank_sum"] += idx
            if p["best_rank"] is None or idx < p["best_rank"]:
                p["best_rank"] = idx

        # Optional playoffs
        pm_rows = conn.execute(
            """
            SELECT stage, player_a, player_b, winner
            FROM playoff_match
            WHERE tournament_id = ?
            ORDER BY CASE stage WHEN 'SF' THEN 1 WHEN 'F' THEN 2 ELSE 9 END, id ASC
            """,
            (tid,),
        ).fetchall()
        playoff_matches: list[dict[str, Any]] = []
        champion: str | None = None
        for r in pm_rows:
            stage = str(r["stage"]).strip().upper()
            pa = str(r["player_a"]).strip()
            pb = str(r["player_b"]).strip()
            wnr = str(r["winner"]).strip()
            playoff_matches.append({"stage": stage, "player_a": pa, "player_b": pb, "winner": wnr})
            if stage in ("F", "FINAL"):
                champion = wnr

        tournaments.append(
            {
                "id": tid,
                "played_at": played_at,
                "name": str(t["name"]),
                "format": str(t["format"]),
                "rounds": int(t["rounds"]) if t["rounds"] is not None else None,
                "notes": str(t["notes"]) if t["notes"] is not None else "",
                "standings": standings,
                "playoffs": {"matches": playoff_matches, "champion": champion} if playoff_matches else None,
            }
        )

    # finalize aggregates
    out_players: list[dict[str, Any]] = []
    for p in by_player.values():
        matches = int(p["matches"])
        w = int(p["wins"])
        d = int(p["draws"])
        p["match_win_pct"] = (w + 0.5 * d) / matches if matches > 0 else None
        if p["via_n"]:
            p["via_avg"] = float(p["via_avg"]) / int(p["via_n"])
        else:
            p["via_avg"] = None
        p["avg_rank"] = float(p["_rank_sum"]) / int(p["tournaments"]) if p["tournaments"] else None
        p.pop("_rank_sum", None)
        out_players.append(p)

    out_players.sort(key=lambda x: (-float(x["match_win_pct"] or 0.0), x["player"].casefold()))

    generated = max_played_at or datetime.utcnow()

    return {
        "schema": SCHEMA_VERSION,
        # Keep deterministic like commander exporter: use max played_at, not now.
        "generated_utc": generated.replace(microsecond=0).isoformat() + "Z",
        "counts": {
            "tournaments": len(tournaments),
            "players": len(out_players),
        },
        "tournaments": tournaments,
        "by_player": out_players,
    }


def write_json(data: dict[str, Any], out_path: str) -> None:
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
