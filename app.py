from __future__ import annotations

import csv
import io
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Field, Session, SQLModel, create_engine, select

# =============================================================================
# DB MODELS
# =============================================================================

class Game(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    played_at: datetime = Field(default_factory=datetime.utcnow)
    notes: Optional[str] = None
    winner_player: Optional[str] = None  # opzionale


class GameEntry(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id", index=True)
    player: str = Field(index=True)
    commander: str = Field(index=True)


# =============================================================================
# APP SETUP
# =============================================================================

app = FastAPI()
templates = Jinja2Templates(directory="templates")

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "commander_tracker.sqlite"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)


@app.on_event("startup")
def on_startup() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)


# =============================================================================
# HELPERS
# =============================================================================

def parse_entries(text: str) -> List[Tuple[str, str]]:
    """
    Formato atteso (una riga per player):
      Player - Commander
    """
    out: List[Tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if "-" not in line:
            raise ValueError(f"Riga non valida (manca '-'): {line}")
        player, commander = [x.strip() for x in line.split("-", 1)]
        if not player or not commander:
            raise ValueError(f"Riga non valida: {line}")
        out.append((player, commander))
    if not out:
        raise ValueError("Nessuna entry trovata.")
    return out


def load_game_rows(limit: int = 50) -> List[Tuple[Game, List[GameEntry]]]:
    with get_session() as session:
        games = session.exec(select(Game).order_by(Game.played_at.desc()).limit(limit)).all()
        rows: List[Tuple[Game, List[GameEntry]]] = []
        for g in games:
            entries = session.exec(select(GameEntry).where(GameEntry.game_id == g.id)).all()
            rows.append((g, entries))
        return rows


def build_entries_by_game(entries: List[GameEntry]) -> Dict[int, List[GameEntry]]:
    by_game: Dict[int, List[GameEntry]] = {}
    for e in entries:
        by_game.setdefault(e.game_id, []).append(e)
    return by_game


# =============================================================================
# BASIC ROUTES / DEBUG
# =============================================================================

@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/whoami", response_class=HTMLResponse)
def whoami() -> HTMLResponse:
    here = Path(__file__).resolve()
    return HTMLResponse(
        f"<h1>WHOAMI</h1><p>file: {here}</p><p>pid: {os.getpid()}</p>",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/debug", response_class=HTMLResponse)
def debug() -> HTMLResponse:
    db_exists = DB_PATH.exists()
    db_stat = DB_PATH.stat() if db_exists else None

    with get_session() as session:
        games_n = session.exec(select(Game)).all()
        entries_n = session.exec(select(GameEntry)).all()
        last_game = session.exec(select(Game).order_by(Game.id.desc()).limit(1)).first()

    html = f"""
    <h1>DEBUG</h1>
    <p><b>DB_PATH</b>: {DB_PATH}</p>
    <p><b>DB exists</b>: {db_exists}</p>
    <p><b>DB size</b>: {db_stat.st_size if db_stat else "n/a"}</p>
    <p><b>DB mtime</b>: {db_stat.st_mtime if db_stat else "n/a"}</p>
    <p><b>Games</b>: {len(games_n)}</p>
    <p><b>Entries</b>: {len(entries_n)}</p>
    <p><b>Last game</b>: {last_game}</p>
    <p><b>PID</b>: {os.getpid()}</p>
    """
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@app.get("/stats.json")
def stats_json() -> JSONResponse:
    with get_session() as session:
        games = session.exec(select(Game)).all()
        entries = session.exec(select(GameEntry)).all()
    return JSONResponse(
        {"games": len(games), "entries": len(entries), "sample": [e.model_dump() for e in entries[:5]]}
    )


# =============================================================================
# UI: INDEX / ADD / EDIT / DELETE
# =============================================================================

@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    game_rows = load_game_rows(limit=50)
    return templates.TemplateResponse("index.html", {"request": request, "game_rows": game_rows})


@app.get("/add", response_class=HTMLResponse)
def add_form(request: Request, error: Optional[str] = None) -> HTMLResponse:
    return templates.TemplateResponse("add_game.html", {"request": request, "error": error})


@app.post("/add")
def add_game(
    request: Request,
    entries_text: str = Form(...),
    winner_player: str = Form(""),
    notes: str = Form(""),
):
    try:
        entries = parse_entries(entries_text)
    except ValueError as e:
        return templates.TemplateResponse(
            "add_game.html",
            {"request": request, "error": str(e)},
            status_code=400,
        )

    winner = winner_player.strip() or None
    notes_clean = notes.strip() or None

    with get_session() as session:
        g = Game(winner_player=winner, notes=notes_clean)
        session.add(g)
        session.commit()
        session.refresh(g)

        for player, commander in entries:
            session.add(GameEntry(game_id=g.id, player=player, commander=commander))

        session.commit()

    return RedirectResponse(url="/", status_code=303)


@app.get("/edit/{game_id}", response_class=HTMLResponse)
def edit_form(request: Request, game_id: int) -> HTMLResponse:
    with get_session() as session:
        g = session.get(Game, game_id)
        if not g:
            raise HTTPException(status_code=404, detail="Game not found")

        entries = session.exec(select(GameEntry).where(GameEntry.game_id == game_id)).all()

    entries_text = "\n".join([f"{e.player} - {e.commander}" for e in entries])
    return templates.TemplateResponse(
        "edit_game.html",
        {"request": request, "game": g, "entries_text": entries_text, "error": None},
    )


@app.post("/edit/{game_id}")
def edit_game(
    request: Request,
    game_id: int,
    entries_text: str = Form(...),
    winner_player: str = Form(""),
    notes: str = Form(""),
):
    try:
        entries = parse_entries(entries_text)
    except ValueError as e:
        with get_session() as session:
            g = session.get(Game, game_id)
        return templates.TemplateResponse(
            "edit_game.html",
            {"request": request, "game": g, "entries_text": entries_text, "error": str(e)},
            status_code=400,
        )

    winner = winner_player.strip() or None
    notes_clean = notes.strip() or None

    with get_session() as session:
        g = session.get(Game, game_id)
        if not g:
            raise HTTPException(status_code=404, detail="Game not found")

        g.winner_player = winner
        g.notes = notes_clean
        session.add(g)
        session.commit()

        old_entries = session.exec(select(GameEntry).where(GameEntry.game_id == game_id)).all()
        for oe in old_entries:
            session.delete(oe)
        session.commit()

        for player, commander in entries:
            session.add(GameEntry(game_id=game_id, player=player, commander=commander))
        session.commit()

    return RedirectResponse(url="/", status_code=303)


@app.post("/delete_game")
def delete_game(game_id: int = Form(...)) -> RedirectResponse:
    with get_session() as session:
        entries = session.exec(select(GameEntry).where(GameEntry.game_id == game_id)).all()
        for e in entries:
            session.delete(e)

        g = session.get(Game, game_id)
        if g:
            session.delete(g)

        session.commit()

    return RedirectResponse(url="/", status_code=303)


# =============================================================================
# STATS (overall + per pod size)
# =============================================================================

@app.get("/stats", response_class=HTMLResponse)
def stats(request: Request) -> HTMLResponse:
    with get_session() as session:
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
    player_rows = []
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

    pair_rows = []
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

    resp = templates.TemplateResponse(
        "stats.html",
        {
            "request": request,
            "player_rows": player_rows,
            "pair_rows": pair_rows,
            "sizes": sizes,
            "player_by_size_tables": player_by_size_tables,
            "pair_by_size_tables": pair_by_size_tables,
        },
    )
    resp.headers["Cache-Control"] = "no-store"
    return resp


# =============================================================================
# DASHBOARD (Chart.js)
# =============================================================================

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, min_games: int = 3) -> HTMLResponse:
    with get_session() as session:
        games = session.exec(select(Game)).all()
        entries = session.exec(select(GameEntry)).all()

    # game_id -> entries
    entries_by_game: Dict[int, List[GameEntry]] = {}
    for e in entries:
        entries_by_game.setdefault(e.game_id, []).append(e)

    # Distribuzione pod size
    pod_counts: Dict[int, int] = {}
    for _, es in entries_by_game.items():
        n = len(es)
        pod_counts[n] = pod_counts.get(n, 0) + 1

    # winner per game
    winner_by_game: Dict[int, Optional[str]] = {g.id: g.winner_player for g in games if g.id is not None}

    # Vittorie per player
    wins_by_player: Dict[str, int] = {}
    for g in games:
        if g.winner_player:
            wins_by_player[g.winner_player] = wins_by_player.get(g.winner_player, 0) + 1

    # Partite per player
    games_by_player: Dict[str, set] = {}
    for e in entries:
        games_by_player.setdefault(e.player, set()).add(e.game_id)
    games_by_player_counts = {p: len(s) for p, s in games_by_player.items()}

    # Commander più giocati
    commander_counts: Dict[str, int] = {}
    for e in entries:
        commander_counts[e.commander] = commander_counts.get(e.commander, 0) + 1

    # --- TOP PAIRING per WINRATE (con soglia min_games) ---
    pair_stats: Dict[Tuple[str, str], Dict[str, object]] = {}

    for gid, es in entries_by_game.items():
        winner = winner_by_game.get(gid)
        for e in es:
            key = (e.player, e.commander)
            pair_stats.setdefault(key, {"games": set(), "wins": 0})
            pair_stats[key]["games"].add(gid)
            if winner and winner == e.player:
                pair_stats[key]["wins"] += 1

    top_pairs = []
    for (p, c), v in pair_stats.items():
        games_n = len(v["games"])
        if games_n < max(1, min_games):
            continue
        wins_n = int(v["wins"])
        winrate = (wins_n / games_n) * 100.0 if games_n else 0.0
        top_pairs.append((p, c, games_n, wins_n, winrate))

    top_pairs.sort(key=lambda x: (-x[4], -x[2], x[0].lower(), x[1].lower()))
    top_pairs = top_pairs[:10]

    def top_k(d: Dict[str, int], k: int = 10):
        return sorted(d.items(), key=lambda x: (-x[1], x[0].lower()))[:k]

    pod_labels = [f"{n}p" for n in sorted(pod_counts.keys())]
    pod_values = [pod_counts[int(lbl[:-1])] for lbl in pod_labels]

    top_games = top_k(games_by_player_counts, 10)
    top_wins = top_k(wins_by_player, 10)
    top_cmd = top_k(commander_counts, 10)

    payload = {
        "pod": {"labels": pod_labels, "values": pod_values},
        "topPlayersGames": {"labels": [x[0] for x in top_games], "values": [x[1] for x in top_games]},
        "topPlayersWins": {"labels": [x[0] for x in top_wins], "values": [x[1] for x in top_wins]},
        "topCommanders": {"labels": [x[0] for x in top_cmd], "values": [x[1] for x in top_cmd]},
        "topPairingsWinrate": {
            "minGames": max(1, min_games),
            "labels": [f"{p} — {c}" for (p, c, _, _, _) in top_pairs],
            "values": [round(wr, 1) for (_, _, _, _, wr) in top_pairs],
            "rows": [
                {"player": p, "commander": c, "games": g, "wins": w, "winrate": round(wr, 1)}
                for (p, c, g, w, wr) in top_pairs
            ],
        },
    }

    resp = templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "chart_data": payload,   # ✅ dict, non stringa JSON
            "min_games": max(1, min_games),
        },
    )
    resp.headers["Cache-Control"] = "no-store"
    return resp



# =============================================================================
# EXPORT
# =============================================================================

@app.get("/export_flat.csv")
def export_flat_csv() -> StreamingResponse:
    """Export 'flat': una riga per player in una partita."""
    with get_session() as session:
        games = session.exec(select(Game)).all()
        entries = session.exec(select(GameEntry)).all()

    game_by_id = {g.id: g for g in games}

    def generate():
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow(["game_id", "played_at_utc", "winner_player", "notes", "player", "commander"])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        for e in entries:
            g = game_by_id.get(e.game_id)
            if not g:
                continue
            writer.writerow([g.id, g.played_at.isoformat(), g.winner_player or "", g.notes or "", e.player, e.commander])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="commander_tracker_export_flat.csv"'},
    )


@app.get("/export_games.csv")
def export_games_csv() -> StreamingResponse:
    """
    Export 'per-game': una riga per partita con lineup + winner + participants.
    Columns:
      game_id, played_at_utc, participants, winner_player, notes, players, commanders, lineup
    """
    with get_session() as session:
        games = session.exec(select(Game).order_by(Game.played_at.asc())).all()
        entries = session.exec(select(GameEntry)).all()

    entries_by_game = build_entries_by_game(entries)

    def generate():
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow(["game_id", "played_at_utc", "participants", "winner_player", "notes", "players", "commanders", "lineup"])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        for g in games:
            if g.id is None:
                continue
            es = entries_by_game.get(g.id, [])
            es_sorted = sorted(es, key=lambda x: x.player.lower())  # ordine stabile

            participants = len(es_sorted)
            players = " | ".join([e.player for e in es_sorted])
            commanders = " | ".join([e.commander for e in es_sorted])
            lineup = " | ".join([f"{e.player}={e.commander}" for e in es_sorted])

            writer.writerow(
                [
                    g.id,
                    g.played_at.isoformat(),
                    participants,
                    g.winner_player or "",
                    g.notes or "",
                    players,
                    commanders,
                    lineup,
                ]
            )
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="commander_tracker_export_games.csv"'},
    )

