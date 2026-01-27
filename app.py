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
from sqlalchemy import func

import tempfile
from typing import Dict, List, Optional, Tuple

from fastapi import Request
from fastapi.responses import HTMLResponse, StreamingResponse
from playwright.sync_api import sync_playwright
from sqlmodel import select
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
    bracket: Optional[int] = Field(default=None, index=True)


# =============================================================================
# APP SETUP
# =============================================================================

app = FastAPI()
templates = Jinja2Templates(directory="templates")

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "commander_tracker.sqlite"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)


def migrate_schema() -> None:
    """Esegue piccole migrazioni incrementali sul DB SQLite (ALTER TABLE).

    Nota: SQLModel.metadata.create_all NON aggiunge colonne su tabelle esistenti.
    """
    with engine.connect() as conn:
        # Verifica se la tabella esiste già
        res = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='gameentry';"
        ).fetchone()
        if not res:
            return

        cols = conn.exec_driver_sql("PRAGMA table_info('gameentry');").fetchall()
        col_names = {c[1] for c in cols}  # (cid, name, type, notnull, dflt_value, pk)
        if "bracket" not in col_names:
            conn.exec_driver_sql("ALTER TABLE gameentry ADD COLUMN bracket INTEGER;")
            conn.commit()


@app.on_event("startup")
def on_startup() -> None:
    migrate_schema()
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)


# =============================================================================
# HELPERS
# =============================================================================

def parse_entries(text: str) -> List[Tuple[str, str, Optional[int]]]:
    """
    Formato atteso (una riga per player):
      Player - Commander - Bracket

    Dove Bracket è:
      - un intero da 1 a 5
      - oppure 'n/a' (o vuoto) per indicare assente

    Per retro-compatibilità, è accettato anche:
      Player - Commander
    """
    out: List[Tuple[str, str, Optional[int]]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        # Preferisci separatore " - " (più robusto se nei nomi ci sono trattini)
        sep = " - " if " - " in line else "-"
        parts = [p.strip() for p in line.split(sep)]

        if len(parts) < 2:
            raise ValueError(f"Riga non valida: {line}")

        player = parts[0]
        if not player:
            raise ValueError(f"Riga non valida: {line}")

        bracket: Optional[int] = None
        commander_parts = parts[1:]

        # Se ci sono 3+ parti, interpretiamo l'ultima come bracket
        if len(parts) >= 3:
            bracket_token = parts[-1].strip().lower()
            commander_parts = parts[1:-1]

            if bracket_token in {"", "n/a", "na", "none", "null"}:
                bracket = None
            else:
                try:
                    bracket_val = int(bracket_token)
                except ValueError:
                    raise ValueError(f"Bracket non valido (usa 1-5 o n/a): {line}")
                if bracket_val < 1 or bracket_val > 5:
                    raise ValueError(f"Bracket fuori range (1-5): {line}")
                bracket = bracket_val

        commander = f" {sep.strip()} ".join([c for c in commander_parts if c]).strip()
        if not commander:
            raise ValueError(f"Riga non valida: {line}")

        out.append((player, commander, bracket))

    if not out:
        raise ValueError("Nessuna entry trovata.")
    return out

# =============================================================================
# BRACKET METRICS (used in bracket-wise dashboards)
# =============================================================================

def compute_table_bracket_avg(entries: List[GameEntry]) -> Optional[float]:
    """Average bracket at the table (ignoring n/a). Returns None if no brackets."""
    vals = [e.bracket for e in entries if e.bracket is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def compute_winner_bracket(entries: List[GameEntry], winner_player: Optional[str]) -> Optional[int]:
    if not winner_player:
        return None
    for e in entries:
        if e.player == winner_player:
            return e.bracket
    return None


def compute_player_bracket(entries: List[GameEntry], player: str) -> Optional[int]:
    for e in entries:
        if e.player == player:
            return e.bracket
    return None


def win_weight_from_delta(delta_b: float, alpha: float = 0.5) -> float:
    """Weight applied to a win based on bracket mismatch.

    delta_b = B_winner - B_avg (winner bracket minus table average)

    - If delta_b > 0  (winner bracket ABOVE the pod average): penalize the win
        w = 1 / (1 + alpha * delta_b)
    - If delta_b == 0: neutral
        w = 1
    - If delta_b < 0  (winner bracket BELOW the pod average): reward the win
        w = 1 + alpha * (-delta_b)

    Note: downstream "weighted winrate" computations use a win-weighted denominator
    (i.e., a win with weight w also makes that game count as w in the denominator),
    so winrates remain bounded in [0, 100].
    """
    try:
        a = float(alpha)
    except Exception:
        a = 0.0
    if a < 0:
        a = 0.0

    d = float(delta_b)
    if d > 0:
        return 1.0 / (1.0 + a * d)
    if d < 0:
        return 1.0 + a * (-d)
    return 1.0


def bpi_label(bpi: Optional[float]) -> str:
    """Qualitative label for BPI (mean deltaB in wins)."""
    if bpi is None:
        return "n/a"
    if bpi >= 2.0:
        return "pubstomp"
    if bpi >= 1.0:
        return "over"
    if bpi <= -1.0:
        return "underdog"
    return "fair"

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

def get_known_players_and_commanders() -> Tuple[List[str], List[str]]:
    """
    Ritorna (players, commanders) distinti presenti nel DB (da GameEntry),
    ordinati case-insensitive e puliti da stringhe vuote.
    """
    with get_session() as session:
        players = session.exec(select(GameEntry.player).distinct()).all()
        commanders = session.exec(select(GameEntry.commander).distinct()).all()

    players_clean = sorted({p.strip() for p in players if p and p.strip()}, key=lambda s: s.lower())
    commanders_clean = sorted({c.strip() for c in commanders if c and c.strip()}, key=lambda s: s.lower())
    return players_clean, commanders_clean


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
    players, commanders = get_known_players_and_commanders()
    return templates.TemplateResponse(
        "add_game.html",
        {"request": request, "error": error, "players": players, "commanders": commanders},
    )


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
        players, commanders = get_known_players_and_commanders()
        return templates.TemplateResponse(
            "add_game.html",
            {"request": request, "error": str(e), "players": players, "commanders": commanders},
            status_code=400,
        )


    winner = winner_player.strip() or None
    notes_clean = notes.strip() or None

    with get_session() as session:
        g = Game(winner_player=winner, notes=notes_clean)
        session.add(g)
        session.commit()
        session.refresh(g)

        for player, commander, bracket in entries:
            session.add(GameEntry(game_id=g.id, player=player, commander=commander, bracket=bracket))

        session.commit()

    return RedirectResponse(url="/", status_code=303)


@app.get("/edit/{game_id}", response_class=HTMLResponse)
def edit_form(request: Request, game_id: int) -> HTMLResponse:
    with get_session() as session:
        g = session.get(Game, game_id)
        if not g:
            raise HTTPException(status_code=404, detail="Game not found")

        entries = session.exec(select(GameEntry).where(GameEntry.game_id == game_id)).all()

    entries_text = "\n".join([
        f"{e.player} - {e.commander} - {(e.bracket if e.bracket is not None else 'n/a')}" for e in entries
    ])
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

        for player, commander, bracket in entries:
            session.add(GameEntry(game_id=game_id, player=player, commander=commander, bracket=bracket))
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
def stats(request: Request, top_triples: int = 50, max_unique: int = 200) -> HTMLResponse:
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

    # -----------------------------
    # Bracket stats (descriptive)
    # -----------------------------
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

    # Bracket distributions
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

    bracket_rows = []
    for k in sorted(bracket_games.keys(), key=lambda x: (x == "n/a", x)):
        g = len(bracket_games[k])
        w = int(bracket_wins.get(k, 0))
        wr = (w / g * 100.0) if g else 0.0
        bracket_rows.append({"bracket": k, "games": g, "wins": w, "winrate": wr})

    # Unique triples (Commander, Player, Bracket) as a simple data-hygiene list
    # Note: we keep bracket as string so that "n/a" is an explicit bucket.
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
                    "weighted_games": 0.0,  # win-weighted denominator (keeps WR in [0,100])
                    "deltas": [],
                    "table_avgs": [],
                },
            )
            rec["games"].add(gid)
            # baseline: each participation counts as 1 game in the weighted denominator
            rec["weighted_games"] += 1.0
            if bavg is not None:
                rec["table_avgs"].append(float(bavg))

            if w and w == e.player:
                rec["wins"] += 1
                # weighted win
                if (e.bracket is not None) and (bavg is not None):
                    delta = float(e.bracket) - float(bavg)
                    rec["deltas"].append(delta)
                    w_eff = float(win_weight_from_delta(delta))
                    rec["weighted_wins"] += w_eff
                    # A win with weight w also makes that game count as w in the denominator
                    rec["weighted_games"] += (w_eff - 1.0)
                else:
                    # If delta isn't computable, treat as unweighted win (neutral)
                    rec["weighted_wins"] += 1.0

    triple_rows = []
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
        key=lambda r: (-r["games"], -(r["weighted_wr"] or 0.0), -(r["winrate"] or 0.0), r["player"].lower(), r["commander"].lower())
    )
    triple_rows = triple_rows[:top_triples]

    top_options = [10, 25, 50, 100, 200, 500]
    max_unique_options = [25, 50, 100, 200, 500, 1000, 2000, 5000]
    resp = templates.TemplateResponse(
        "stats.html",
        {
            "request": request,
            "player_rows": player_rows,
            "pair_rows": pair_rows,
            "sizes": sizes,
            "player_by_size_tables": player_by_size_tables,
            "pair_by_size_tables": pair_by_size_tables,
            "top_triples": top_triples,
            "top_options": top_options,
            "max_unique": max_unique,
            "max_unique_options": max_unique_options,
            "bracket_entry_counts": bracket_entry_counts,
            "bracket_winner_counts": bracket_winner_counts,
            "bracket_rows": bracket_rows,
            "unique_triples_rows": unique_triples_rows,
            "triple_rows": triple_rows,
        },
    )
    resp.headers["Cache-Control"] = "no-store"
    return resp

# =============================================================================
# DASHBOARD (Chart.js)
# =============================================================================

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    player: str = "__all__",          # "__all__" = tutti
    min_pg: int = 3,
    min_pair: int = 3,
    min_cmd: int = 3,
    top_players: int = 10,
    top_pairs: int = 10,
    top_cmd: int = 10,
) -> HTMLResponse:
    min_pg = max(1, int(min_pg))
    min_pair = max(1, int(min_pair))
    min_cmd = max(1, int(min_cmd))
    top_players = max(1, min(50, int(top_players)))
    top_pairs = max(1, min(50, int(top_pairs)))
    top_cmd = max(1, min(50, int(top_cmd)))

    with get_session() as session:
        games = session.exec(select(Game)).all()
        entries = session.exec(select(GameEntry)).all()

    # game_id -> entries
    entries_by_game: Dict[int, List[GameEntry]] = {}
    for e in entries:
        entries_by_game.setdefault(e.game_id, []).append(e)

    participants_by_game: Dict[int, int] = {gid: len(es) for gid, es in entries_by_game.items()}

    winner_by_game: Dict[int, Optional[str]] = {g.id: g.winner_player for g in games if g.id is not None}
    game_time_by_id: Dict[int, datetime] = {g.id: g.played_at for g in games if g.id is not None}

    # elenco player + partite per player
    games_by_player: Dict[str, set] = {}
    for e in entries:
        games_by_player.setdefault(e.player, set()).add(e.game_id)
    all_players = sorted(games_by_player.keys(), key=lambda x: x.lower())

    # selezione player
    player = (player or "").strip()
    if player == "":
        player = "__all__"
    if player != "__all__" and player not in games_by_player:
        player = "__all__"

    # wins per player
    wins_by_player: Dict[str, int] = {}
    for g in games:
        if g.winner_player:
            wins_by_player[g.winner_player] = wins_by_player.get(g.winner_player, 0) + 1

    games_count_by_player = {p: len(s) for p, s in games_by_player.items()}

    # -------------------------------------------------------------------------
    # 1) Winrate Player (top N) + Scatter WR vs Games (sample size)
    # -------------------------------------------------------------------------
    player_wr_rows = []
    for p, games_n in games_count_by_player.items():
        if games_n < min_pg:
            continue
        wins_n = wins_by_player.get(p, 0)
        wr = (wins_n / games_n) * 100.0 if games_n else 0.0
        player_wr_rows.append((p, games_n, wins_n, wr))

    # top players by WR (tie-break by games)
    player_wr_rows.sort(key=lambda x: (-x[3], -x[1], x[0].lower()))
    player_wr_top = player_wr_rows[:top_players]

    scatter_rows = []
    for (p, games_n, wins_n, wr) in player_wr_rows:
        # Bubble radius: cresce con games ma in modo “smooth”
        # r minimo 4, massimo 18 circa
        r = 4 + min(14, int((games_n ** 0.5) * 3))
        scatter_rows.append(
            {"player": p, "games": games_n, "wins": wins_n, "winrate": round(wr, 1), "r": r}
        )

    # -------------------------------------------------------------------------
    # 2) Top pairing player+commander per winrate (con soglia min_pair)
    # -------------------------------------------------------------------------
    pair_stats: Dict[Tuple[str, str], Dict[str, object]] = {}
    for gid, es in entries_by_game.items():
        winner = winner_by_game.get(gid)
        for e in es:
            key = (e.player, e.commander)
            pair_stats.setdefault(key, {"games": set(), "wins": 0})
            pair_stats[key]["games"].add(gid)
            if winner and winner == e.player:
                pair_stats[key]["wins"] += 1

    pair_rows = []
    for (p, c), v in pair_stats.items():
        games_n = len(v["games"])
        if games_n < min_pair:
            continue
        wins_n = int(v["wins"])
        wr = (wins_n / games_n) * 100.0 if games_n else 0.0
        pair_rows.append((p, c, games_n, wins_n, wr))

    pair_rows.sort(key=lambda x: (-x[4], -x[2], x[0].lower(), x[1].lower()))
    pair_rows = pair_rows[:top_pairs]

    # -------------------------------------------------------------------------
    # 3) Winrate per pod size (BAR) — per player selezionato o tutti
    # -------------------------------------------------------------------------
    pod_participations: Dict[int, int] = {}
    pod_wins: Dict[int, int] = {}

    for gid, es in entries_by_game.items():
        n = participants_by_game.get(gid, 0)
        if n <= 0:
            continue

        winner = winner_by_game.get(gid)

        if player == "__all__":
            pod_participations[n] = pod_participations.get(n, 0) + n
            if winner:
                pod_wins[n] = pod_wins.get(n, 0) + 1
        else:
            participated = any(e.player == player for e in es)
            if not participated:
                continue
            pod_participations[n] = pod_participations.get(n, 0) + 1
            if winner and winner == player:
                pod_wins[n] = pod_wins.get(n, 0) + 1

    pod_sizes = sorted(pod_participations.keys())
    pod_wr_values = []
    pod_denoms = []
    for n in pod_sizes:
        denom = pod_participations.get(n, 0)
        wins = pod_wins.get(n, 0)
        wr = (wins / denom) * 100.0 if denom else 0.0
        pod_wr_values.append(round(wr, 1))
        pod_denoms.append(denom)

    pod_baseline = [round((1.0 / n) * 100.0, 1) for n in pod_sizes]

    # -------------------------------------------------------------------------
    # 4) Top Commander per Winrate (con soglia min_cmd)
    # -------------------------------------------------------------------------
    cmd_stats: Dict[str, Dict[str, object]] = {}
    for gid, es in entries_by_game.items():
        winner = winner_by_game.get(gid)
        for e in es:
            c = e.commander
            cmd_stats.setdefault(c, {"games": set(), "wins": 0})
            cmd_stats[c]["games"].add(gid)
            if winner and winner == e.player:
                cmd_stats[c]["wins"] += 1

    cmd_rows = []
    for c, v in cmd_stats.items():
        games_n = len(v["games"])
        if games_n < min_cmd:
            continue
        wins_n = int(v["wins"])
        wr = (wins_n / games_n) * 100.0 if games_n else 0.0
        cmd_rows.append((c, games_n, wins_n, wr))

    cmd_rows.sort(key=lambda x: (-x[3], -x[1], x[0].lower()))
    cmd_rows = cmd_rows[:top_cmd]

    # -------------------------------------------------------------------------
    # 5) Trend winrate cumulativo (solo per player specifico)
    # -------------------------------------------------------------------------
    trend_points = []
    if player != "__all__":
        gp = sorted(
            [gid for gid, es in entries_by_game.items() if any(e.player == player for e in es)],
            key=lambda gid: game_time_by_id.get(gid, datetime.min),
        )
        total = 0
        wins = 0
        for gid in gp:
            total += 1
            if winner_by_game.get(gid) == player:
                wins += 1
            wr = (wins / total) * 100.0 if total else 0.0
            dt = game_time_by_id.get(gid)
            label = dt.strftime("%Y-%m-%d") if dt else f"game {gid}"
            trend_points.append((label, round(wr, 1)))

    payload = {
        "params": {
            "player": player,
            "min_pg": min_pg,
            "min_pair": min_pair,
            "min_cmd": min_cmd,
            "top_players": top_players,
            "top_pairs": top_pairs,
            "top_cmd": top_cmd,
        },
        "players": all_players,

        # 1a) Bar top WR
        "playerWinrate": {
            "labels": [p for (p, _, _, _) in player_wr_top],
            "values": [round(wr, 1) for (_, _, _, wr) in player_wr_top],
            "rows": [{"player": p, "games": g, "wins": w, "winrate": round(wr, 1)} for (p, g, w, wr) in player_wr_top],
        },
        # 1b) Scatter WR vs games (sample size)
        "playerScatter": {
            "minGames": min_pg,
            "rows": scatter_rows,  # [{player,games,wins,winrate}]
        },

        # 2) Pairing
        "pairingWinrate": {
            "labels": [f"{p} — {c}" for (p, c, _, _, _) in pair_rows],
            "values": [round(wr, 1) for (_, _, _, _, wr) in pair_rows],
            "rows": [{"player": p, "commander": c, "games": g, "wins": w, "winrate": round(wr, 1)} for (p, c, g, w, wr) in pair_rows],
        },

        # 3) Pod WR
        "podWinrate": {
            "player": player,
            "labels": [f"{n}p" for n in pod_sizes],
            "values": pod_wr_values,
            "baseline": pod_baseline,
            "denom": pod_denoms,
            "mode": "all" if player == "__all__" else "player",
        },

        # 4) Commander WR
        "commanderWinrate": {
            "labels": [c for (c, _, _, _) in cmd_rows],
            "values": [round(wr, 1) for (_, _, _, wr) in cmd_rows],
            "rows": [{"commander": c, "games": g, "wins": w, "winrate": round(wr, 1)} for (c, g, w, wr) in cmd_rows],
        },

        # 5) Trend
        "trend": {
            "player": player,
            "labels": [x[0] for x in trend_points],
            "values": [x[1] for x in trend_points],
        },
    }

    resp = templates.TemplateResponse("dashboard.html", {"request": request, "chart_data": payload})
    resp.headers["Cache-Control"] = "no-store"
    return resp




# =============================================================================
# EXPORT
# =============================================================================

@app.get("/export.csv")
def export_csv() -> StreamingResponse:
    """
    Export unico (base): una riga per partita con lineup + winner + participants.
    Columns:
      game_id, played_at_utc, participants, winner_player, notes, lineup
    """
    with get_session() as session:
        games = session.exec(select(Game).order_by(Game.played_at.asc())).all()
        entries = session.exec(select(GameEntry)).all()

    # game_id -> [entries...]
    entries_by_game: Dict[int, List[GameEntry]] = {}
    for e in entries:
        entries_by_game.setdefault(e.game_id, []).append(e)

    def generate():
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow(["game_id", "played_at_utc", "participants", "winner_player", "notes", "lineup"])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        for g in games:
            if g.id is None:
                continue

            es = entries_by_game.get(g.id, [])
            # ordine stabile (alfabetico player). Se preferisci ordine inserimento, dimmelo.
            es_sorted = sorted(es, key=lambda x: (x.player or "").lower())

            participants = len(es_sorted)
            lineup = " | ".join([f"{e.player}={e.commander}" for e in es_sorted])

            writer.writerow([
                g.id,
                g.played_at.isoformat(),
                participants,
                g.winner_player or "",
                g.notes or "",
                lineup,
            ])

            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="commander_tracker_export.csv"'},
    )


from playwright.sync_api import sync_playwright
from fastapi.responses import StreamingResponse
import tempfile

@app.get("/dashboard.pdf")
def dashboard_pdf(
    request: Request,
    player: str = "__all__",
    min_pg: int = 3,
    min_pair: int = 3,
    min_cmd: int = 3,
    top_players: int = 10,
    top_pairs: int = 10,
    top_cmd: int = 10,
    trend_top: int = 8,
    trend_min_games: int = 0,
):
    # ricostruisci la query string identica alla dashboard
    qs = request.url.query
    url = f"http://127.0.0.1:8000/dashboard"
    if qs:
        url += f"?{qs}"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        # viewport coerente con A4 landscape (~96dpi)
        page = browser.new_page(viewport={"width": 1684, "height": 1191})

        # usa media "screen" così la pagina rende come desktop
        page.emulate_media(media="screen")

        page.goto(url, wait_until="networkidle")

        # attesa rendering (più generosa)
        page.wait_for_timeout(1800)

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            page.pdf(
                path=tmp.name,
                format="A4",
                landscape=True,
                print_background=True,
                prefer_css_page_size=True,  # ✅ rispetta meglio eventuale CSS di stampa
                margin={
                    "top": "8mm",
                    "bottom": "8mm",
                    "left": "8mm",
                    "right": "8mm",
                },
            )
            pdf_path = tmp.name

        browser.close()

    return StreamingResponse(
        open(pdf_path, "rb"),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=commander_dashboard.pdf"},
    )

@app.get("/dashboard_mini", response_class=HTMLResponse)
def dashboard_mini(
    request: Request,
    min_pg: int = 3,       # min partite per stats player
    min_pair: int = 1,     # min partite per stats pairing (come richiesto)
    top_players: int = 10,
    top_pairs: int = 10,
) -> HTMLResponse:
    # sanitizzazione parametri
    min_pg = max(1, int(min_pg))
    min_pair = max(1, int(min_pair))
    top_players = max(1, min(50, int(top_players)))
    top_pairs = max(1, min(50, int(top_pairs)))

    with get_session() as session:
        games = session.exec(select(Game)).all()
        entries = session.exec(select(GameEntry)).all()

    # game_id -> entries
    entries_by_game: Dict[int, List[GameEntry]] = {}
    for e in entries:
        entries_by_game.setdefault(e.game_id, []).append(e)

    # winner per game
    winner_by_game: Dict[int, Optional[str]] = {g.id: g.winner_player for g in games if g.id is not None}

    # games per player
    games_by_player: Dict[str, set] = {}
    for e in entries:
        games_by_player.setdefault(e.player, set()).add(e.game_id)
    games_count_by_player = {p: len(s) for p, s in games_by_player.items()}

    # wins per player
    wins_by_player: Dict[str, int] = {}
    for g in games:
        if g.winner_player:
            wins_by_player[g.winner_player] = wins_by_player.get(g.winner_player, 0) + 1

    # ---------------------------------------------------------------------
    # A) Player winrate (bar) + Player bubble (wr vs games)
    # ---------------------------------------------------------------------
    player_winrate_rows: List[Tuple[str, int, int, float]] = []
    player_bubble_rows: List[dict] = []

    for p, games_n in games_count_by_player.items():
        if games_n < min_pg:
            continue
        wins_n = wins_by_player.get(p, 0)
        wr = (wins_n / games_n) * 100.0 if games_n else 0.0

        r = 4 + min(14, int((games_n ** 0.5) * 3))
        player_bubble_rows.append({"player": p, "games": games_n, "wins": wins_n, "winrate": round(wr, 1), "r": r})
        player_winrate_rows.append((p, games_n, wins_n, wr))

    # bar: top players by WR, tie-break games
    player_winrate_rows.sort(key=lambda x: (-x[3], -x[1], x[0].lower()))
    player_top = player_winrate_rows[:top_players]

    # ---------------------------------------------------------------------
    # B) Pair stats (player+commander) + pairing bar + pairing bubble
    # ---------------------------------------------------------------------
    pair_stats: Dict[Tuple[str, str], Dict[str, object]] = {}
    for gid, es in entries_by_game.items():
        winner = winner_by_game.get(gid)
        for e in es:
            key = (e.player, e.commander)
            pair_stats.setdefault(key, {"games": set(), "wins": 0})
            pair_stats[key]["games"].add(gid)
            if winner and winner == e.player:
                pair_stats[key]["wins"] += 1

    pairing_rows: List[Tuple[str, str, int, int, float]] = []
    pairing_bubble_rows: List[dict] = []

    for (p, c), v in pair_stats.items():
        games_n = len(v["games"])
        if games_n < min_pair:
            continue
        wins_n = int(v["wins"])
        wr = (wins_n / games_n) * 100.0 if games_n else 0.0

        pairing_rows.append((p, c, games_n, wins_n, wr))

        r = 4 + min(14, int((games_n ** 0.5) * 3))
        pairing_bubble_rows.append(
            {"player": p, "commander": c, "games": games_n, "wins": wins_n, "winrate": round(wr, 1), "r": r}
        )

    # bar: top pairings by WR, tie-break games
    pairing_rows.sort(key=lambda x: (-x[4], -x[2], x[0].lower(), x[1].lower()))
    pairing_top = pairing_rows[:top_pairs]

    payload = {
        "params": {
            "min_pg": min_pg,
            "min_pair": min_pair,
            "top_players": top_players,
            "top_pairs": top_pairs,
        },

        # top-left
        "playerWinrate": {
            "labels": [p for (p, _, _, _) in player_top],
            "values": [round(wr, 1) for (_, _, _, wr) in player_top],
            "rows": [{"player": p, "games": g, "wins": w, "winrate": round(wr, 1)} for (p, g, w, wr) in player_top],
        },

        # bottom-left
        "playerBubble": {
            "minGames": min_pg,
            "rows": player_bubble_rows,
        },

        # top-right
        "pairingWinrate": {
            "labels": [f"{p} — {c}" for (p, c, _, _, _) in pairing_top],
            "values": [round(wr, 1) for (_, _, _, _, wr) in pairing_top],
            "rows": [
                {"player": p, "commander": c, "games": g, "wins": w, "winrate": round(wr, 1)}
                for (p, c, g, w, wr) in pairing_top
            ],
        },

        # bottom-right
        "pairingBubble": {
            "minGames": min_pair,
            "rows": pairing_bubble_rows,
        },
    }

    resp = templates.TemplateResponse("dashboard_mini.html", {"request": request, "chart_data": payload})
    resp.headers["Cache-Control"] = "no-store"
    return resp

@app.get("/dashboard_mini_bracket", response_class=HTMLResponse)
def dashboard_mini_bracket(
    request: Request,
    min_pg: int = 3,
    min_pair: int = 1,
    top_players: int = 10,
    top_pairs: int = 10,
    alpha: float = 0.5,
) -> HTMLResponse:
    """Bracket-wise mini dashboard (original /dashboard_mini remains unchanged)."""
    min_pg = max(1, int(min_pg))
    min_pair = max(1, int(min_pair))
    top_players = max(1, min(50, int(top_players)))
    top_pairs = max(1, min(50, int(top_pairs)))

    # Bracket weight parameter (alpha) controls how strongly wins are:
    # - down-weighted when the winner bracket is above the table average
    # - up-weighted when the winner bracket is below the table average
    try:
        alpha = float(alpha)
    except Exception:
        alpha = 0.5
    # clamp to a sane range (allow 0 = no weighting)
    if alpha < 0:
        alpha = 0.0
    if alpha > 5:
        alpha = 5.0

    with get_session() as session:
        games = session.exec(select(Game)).all()
        entries = session.exec(select(GameEntry)).all()

    entries_by_game: Dict[int, List[GameEntry]] = {}
    for e in entries:
        entries_by_game.setdefault(e.game_id, []).append(e)

    winner_by_game: Dict[int, Optional[str]] = {g.id: g.winner_player for g in games if g.id is not None}

    # games per player (participations)
    games_by_player: Dict[str, set] = {}
    for e in entries:
        games_by_player.setdefault(e.player, set()).add(e.game_id)
    games_count_by_player = {p: len(s) for p, s in games_by_player.items()}

    # --- bracket-wise aggregates ---
    weighted_wins_by_player: Dict[str, float] = {}
    weighted_games_by_player: Dict[str, float] = {}  # win-weighted denominator (<= keeps WR in [0,100])
    bracket_games_by_player: Dict[str, int] = {}  # games where we can compute player's impact (player bracket + avg)
    meta_delta_sum_by_player: Dict[str, float] = {}

    # pairing (player, commander)
    pair_games: Dict[Tuple[str, str], set] = {}
    pair_weighted_wins: Dict[Tuple[str, str], float] = {}
    pair_weighted_games: Dict[Tuple[str, str], float] = {}  # win-weighted denominator

    for gid, es in entries_by_game.items():
        winner = winner_by_game.get(gid)
        b_avg = compute_table_bracket_avg(es)
        b_w = compute_winner_bracket(es, winner)

        # pairing participations
        for e in es:
            key = (e.player, e.commander)
            pair_games.setdefault(key, set()).add(gid)
            pair_weighted_games[key] = pair_weighted_games.get(key, 0.0) + 1.0
            weighted_games_by_player[e.player] = weighted_games_by_player.get(e.player, 0.0) + 1.0

        # win weight (only if computable)
        w = None
        if b_avg is not None and b_w is not None:
            w = win_weight_from_delta(float(b_w) - float(b_avg), alpha=alpha)

        if winner:
            # If w isn't computable, treat as neutral win (w = 1.0)
            w_eff = float(w) if w is not None else 1.0
            weighted_wins_by_player[winner] = weighted_wins_by_player.get(winner, 0.0) + w_eff
            # Win-weighted denominator: a win with weight w also makes that game count as w
            weighted_games_by_player[winner] = weighted_games_by_player.get(winner, 0.0) + (w_eff - 1.0)
            # pairing winner increment (for the specific winner's commander in that game)
            for e in es:
                if e.player == winner:
                    key = (e.player, e.commander)
                    pair_weighted_wins[key] = pair_weighted_wins.get(key, 0.0) + w_eff
                    pair_weighted_games[key] = pair_weighted_games.get(key, 0.0) + (w_eff - 1.0)
                    break

        # meta impact per player (player bracket - table avg), only if computable
        if b_avg is not None:
            for e in es:
                if e.bracket is None:
                    continue
                bracket_games_by_player[e.player] = bracket_games_by_player.get(e.player, 0) + 1
                meta_delta_sum_by_player[e.player] = meta_delta_sum_by_player.get(e.player, 0.0) + (float(e.bracket) - float(b_avg))

    # -----------------------------------------------------------------
    # A) Player table (Weighted WR + Meta impact)
    # -----------------------------------------------------------------
    player_rows = []
    bubble_rows = []
    for p, games_n in games_count_by_player.items():
        if games_n < min_pg:
            continue
        ww = weighted_wins_by_player.get(p, 0.0)
        wg = weighted_games_by_player.get(p, float(games_n))
        wr_w = (ww / wg) * 100.0 if wg else 0.0

        mg = bracket_games_by_player.get(p, 0)
        mi = (meta_delta_sum_by_player.get(p, 0.0) / mg) if mg else None

        r = 4 + min(14, int((games_n ** 0.5) * 3))
        bubble_rows.append(
            {"player": p, "games": games_n, "weighted_winrate": round(wr_w, 1), "r": r}
        )
        player_rows.append((p, games_n, wr_w, mi))

    # sort by weighted WR, tie-break games
    player_rows.sort(key=lambda x: (-x[2], -x[1], x[0].lower()))
    player_top = player_rows[:top_players]

    # -----------------------------------------------------------------
    # B) Pairing table (Weighted WR)
    # -----------------------------------------------------------------
    pairing_rows = []
    pairing_bubble_rows = []
    for (p, c), gids in pair_games.items():
        games_n = len(gids)
        if games_n < min_pair:
            continue
        ww = pair_weighted_wins.get((p, c), 0.0)
        wg = pair_weighted_games.get((p, c), float(games_n))
        wr_w = (ww / wg) * 100.0 if wg else 0.0

        r = 4 + min(14, int((games_n ** 0.5) * 3))
        pairing_bubble_rows.append(
            {"player": p, "commander": c, "games": games_n, "weighted_winrate": round(wr_w, 1), "r": r}
        )
        pairing_rows.append((p, c, games_n, wr_w))

    pairing_rows.sort(key=lambda x: (-x[3], -x[2], x[0].lower(), x[1].lower()))
    pairing_top = pairing_rows[:top_pairs]

    payload = {
        "params": {
            "min_pg": min_pg,
            "min_pair": min_pair,
            "top_players": top_players,
            "top_pairs": top_pairs,
            "alpha": alpha,
        },
        "playerWinrate": {
            "labels": [p for (p, _, _, _) in player_top],
            "values": [round(wr_w, 1) for (_, _, wr_w, _) in player_top],
            "rows": [
                {
                    "player": p,
                    "games": g,
                    "weighted_winrate": round(wr_w, 1),
                    "meta_impact": (round(mi, 2) if mi is not None else None),
                }
                for (p, g, wr_w, mi) in player_top
            ],
        },
        "playerBubble": {"minGames": min_pg, "rows": bubble_rows},
        "pairingWinrate": {
            "labels": [f"{p} — {c}" for (p, c, _, _) in pairing_top],
            "values": [round(wr_w, 1) for (_, _, _, wr_w) in pairing_top],
            "rows": [
                {"player": p, "commander": c, "games": g, "weighted_winrate": round(wr_w, 1)}
                for (p, c, g, wr_w) in pairing_top
            ],
        },
        "pairingBubble": {"minGames": min_pair, "rows": pairing_bubble_rows},
    }

    resp = templates.TemplateResponse("dashboard_mini_bracket.html", {"request": request, "chart_data": payload})
    resp.headers["Cache-Control"] = "no-store"
    return resp

@app.get("/dashboard_mini.pdf")
def dashboard_mini_pdf(request: Request) -> StreamingResponse:
    qs = request.url.query
    url = "http://127.0.0.1:8000/dashboard_mini"
    if qs:
        url += f"?{qs}"

    with sync_playwright() as p:
        
        browser = p.chromium.launch()

        # viewport coerente con A4 landscape (~96dpi)
        page = browser.new_page(viewport={"width": 1684, "height": 1191})

        # usa media "screen" così la pagina rende come desktop
        page.emulate_media(media="screen")

        page.goto(url, wait_until="networkidle")

        # attesa rendering (più generosa)
        page.wait_for_timeout(1800)

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            page.pdf(
                path=tmp.name,
                format="A4",
                landscape=True,
                print_background=True,
                prefer_css_page_size=True,  # rispetta meglio eventuale CSS di stampa
                margin={
                    "top": "8mm",
                    "bottom": "8mm",
                    "left": "8mm",
                    "right": "8mm",
                },
            )
            pdf_path = tmp.name

        browser.close()

    return StreamingResponse(
        open(pdf_path, "rb"),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=commander_dashboard_mini.pdf"},
    )



@app.get("/dashboard_mini_bracket.pdf")
def dashboard_mini_bracket_pdf(request: Request) -> StreamingResponse:
    """
    Export PDF for /dashboard_mini_bracket using Playwright.
    It preserves query string parameters (min_pg, min_pair, top_players, top_pairs, ...).
    """
    qs = request.url.query
    url = "http://127.0.0.1:8000/dashboard_mini_bracket"
    if qs:
        url += f"?{qs}"

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # Viewport coerente con A4 landscape (~96dpi)
        page = browser.new_page(viewport={"width": 1684, "height": 1191})

        # Usa media "screen" così la pagina rende come desktop
        page.emulate_media(media="screen")

        page.goto(url, wait_until="networkidle")

        # Attesa rendering (più generosa)
        page.wait_for_timeout(1800)

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            page.pdf(
                path=tmp.name,
                format="A4",
                landscape=True,
                print_background=True,
                prefer_css_page_size=True,
                margin={
                    "top": "8mm",
                    "bottom": "8mm",
                    "left": "8mm",
                    "right": "8mm",
                },
            )
            pdf_path = tmp.name

        browser.close()

    return StreamingResponse(
        open(pdf_path, "rb"),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=commander_dashboard_mini_bracket.pdf"},
    )
@app.get("/dashboard_mini.html", response_class=HTMLResponse)
def dashboard_mini_html(
    request: Request,
    min_pg: int = 3,
    min_pair: int = 3,
    top_players: int = 10,
    top_pairs: int = 10,
) -> HTMLResponse:
    # riusa la logica della dashboard_mini (stesso payload)
    resp = dashboard_mini(
        request=request,
        min_pg=min_pg,
        min_pair=min_pair,
        top_players=top_players,
        top_pairs=top_pairs,
    )
    # forza download (facoltativo: puoi anche ometterlo)
    resp.headers["Content-Disposition"] = "attachment; filename=dashboard_mini.html"
    return resp

@app.get("/player_dashboard", response_class=HTMLResponse)
def player_dashboard(
    request: Request,
    player: str = "",
    min_pair: int = 1,
    top_cmd: int = 10,
    top_pairs: int = 30,
) -> HTMLResponse:
    min_pair = max(1, int(min_pair))
    top_cmd = max(1, min(50, int(top_cmd)))
    top_pairs = max(1, min(200, int(top_pairs)))

    with get_session() as session:
        games = session.exec(select(Game)).all()
        entries = session.exec(select(GameEntry)).all()

    # game_id -> entries
    entries_by_game: Dict[int, List[GameEntry]] = {}
    for e in entries:
        entries_by_game.setdefault(e.game_id, []).append(e)

    # winner + played_at
    winner_by_game: Dict[int, Optional[str]] = {g.id: g.winner_player for g in games if g.id is not None}
    time_by_game: Dict[int, datetime] = {g.id: g.played_at for g in games if g.id is not None}

    # players list
    games_by_player: Dict[str, set] = {}
    for e in entries:
        games_by_player.setdefault(e.player, set()).add(e.game_id)
    all_players = sorted(games_by_player.keys(), key=lambda s: s.lower())

    # normalize selected player
    player = (player or "").strip()
    if not player:
        player = all_players[0] if all_players else ""

    if player not in games_by_player:
        # fallback safe
        player = all_players[0] if all_players else ""

    # se DB vuoto
    if not player:
        payload = {
            "params": {"player": "", "min_pair": min_pair, "top_cmd": top_cmd, "top_pairs": top_pairs},
            "players": [],
            "trend": {"labels": [], "values": []},
            "podWinrate": {"labels": [], "values": [], "baseline": [], "denom": []},
            "topCommanders": {"labels": [], "values": [], "rows": []},
            "pairingBubble": {"minGames": min_pair, "rows": []},
        }
        resp = templates.TemplateResponse("player_dashboard.html", {"request": request, "chart_data": payload})
        resp.headers["Cache-Control"] = "no-store"
        return resp

    # ---------------------------------------------------------------------
    # Subset: game_id dove il player partecipa
    # ---------------------------------------------------------------------
    player_game_ids = sorted(
        list(games_by_player.get(player, set())),
        key=lambda gid: time_by_game.get(gid, datetime.min),
    )

    # ---------------------------------------------------------------------
    # 1) Trend winrate cumulativo
    # ---------------------------------------------------------------------
    trend_labels: List[str] = []
    trend_values: List[float] = []
    total = 0
    wins = 0
    for gid in player_game_ids:
        total += 1
        if winner_by_game.get(gid) == player:
            wins += 1
        wr = (wins / total) * 100.0 if total else 0.0
        dt = time_by_game.get(gid)
        trend_labels.append(dt.strftime("%Y-%m-%d") if dt else f"game {gid}")
        trend_values.append(round(wr, 1))

    # ---------------------------------------------------------------------
    # 2) Winrate per pod size (solo games del player)
    # ---------------------------------------------------------------------
    pod_games: Dict[int, int] = {}  # size -> games count (player partecipazioni)
    pod_wins: Dict[int, int] = {}   # size -> wins count (player wins)

    for gid in player_game_ids:
        es = entries_by_game.get(gid, [])
        n = len(es)
        if n <= 0:
            continue
        pod_games[n] = pod_games.get(n, 0) + 1
        if winner_by_game.get(gid) == player:
            pod_wins[n] = pod_wins.get(n, 0) + 1

    pod_sizes = sorted(pod_games.keys())
    pod_labels = [f"{n}p" for n in pod_sizes]
    pod_values = []
    pod_denoms = []
    pod_baseline = []
    for n in pod_sizes:
        denom = pod_games.get(n, 0)
        wins_n = pod_wins.get(n, 0)
        wr = (wins_n / denom) * 100.0 if denom else 0.0
        pod_values.append(round(wr, 1))
        pod_denoms.append(denom)
        pod_baseline.append(round((1.0 / n) * 100.0, 1))

    # ---------------------------------------------------------------------
    # 3) Top commander del player per winrate (min_pair)
    #    (qui per commander del player: games=set, wins=int)
    # ---------------------------------------------------------------------
    cmd_stats: Dict[str, Dict[str, object]] = {}
    for gid in player_game_ids:
        winner = winner_by_game.get(gid)
        for e in entries_by_game.get(gid, []):
            if e.player != player:
                continue
            c = e.commander
            cmd_stats.setdefault(c, {"games": set(), "wins": 0})
            cmd_stats[c]["games"].add(gid)
            if winner and winner == player:
                cmd_stats[c]["wins"] += 1

    cmd_rows = []
    for c, v in cmd_stats.items():
        games_n = len(v["games"])
        if games_n < min_pair:
            continue
        wins_n = int(v["wins"])
        wr = (wins_n / games_n) * 100.0 if games_n else 0.0
        cmd_rows.append((c, games_n, wins_n, wr))

    cmd_rows.sort(key=lambda x: (-x[3], -x[1], x[0].lower()))
    cmd_rows = cmd_rows[:top_cmd]

    # ---------------------------------------------------------------------
    # 4) Bubble WR% vs #Partite per player+commander (solo quel player)
    # ---------------------------------------------------------------------
    pair_stats: Dict[Tuple[str, str], Dict[str, object]] = {}
    for gid in player_game_ids:
        winner = winner_by_game.get(gid)
        for e in entries_by_game.get(gid, []):
            if e.player != player:
                continue
            key = (e.player, e.commander)  # player è sempre lo stesso
            pair_stats.setdefault(key, {"games": set(), "wins": 0})
            pair_stats[key]["games"].add(gid)
            if winner and winner == player:
                pair_stats[key]["wins"] += 1

    bubble_rows = []
    for (p, c), v in pair_stats.items():
        games_n = len(v["games"])
        if games_n < min_pair:
            continue
        wins_n = int(v["wins"])
        wr = (wins_n / games_n) * 100.0 if games_n else 0.0

        # r cresce con sample size
        r = 4 + min(16, int((games_n ** 0.5) * 3))
        bubble_rows.append(
            {"player": p, "commander": c, "games": games_n, "wins": wins_n, "winrate": round(wr, 1), "r": r}
        )

    # puoi limitare quanti punti bubble vuoi visualizzare
    bubble_rows.sort(key=lambda x: (-x["games"], -x["winrate"], x["commander"].lower()))
    bubble_rows = bubble_rows[:top_pairs]

    payload = {
        "params": {"player": player, "min_pair": min_pair, "top_cmd": top_cmd, "top_pairs": top_pairs},
        "players": all_players,
        "trend": {"labels": trend_labels, "values": trend_values},
        "podWinrate": {"labels": pod_labels, "values": pod_values, "baseline": pod_baseline, "denom": pod_denoms},
        "topCommanders": {
            "labels": [c for (c, _, _, _) in cmd_rows],
            "values": [round(wr, 1) for (_, _, _, wr) in cmd_rows],
            "rows": [{"commander": c, "games": g, "wins": w, "winrate": round(wr, 1)} for (c, g, w, wr) in cmd_rows],
        },
        "pairingBubble": {"minGames": min_pair, "rows": bubble_rows},
    }

    resp = templates.TemplateResponse("player_dashboard.html", {"request": request, "chart_data": payload})
    resp.headers["Cache-Control"] = "no-store"
    return resp

from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse
import tempfile
from playwright.sync_api import sync_playwright

def build_player_dashboard_payload(
    player: str,
    min_pair: int,
    top_cmd: int,
    top_pairs: int,
) -> dict:
    min_pair = max(1, int(min_pair))
    top_cmd = max(1, min(50, int(top_cmd)))
    top_pairs = max(1, min(200, int(top_pairs)))

    with get_session() as session:
        games = session.exec(select(Game)).all()
        entries = session.exec(select(GameEntry)).all()

    entries_by_game: Dict[int, List[GameEntry]] = {}
    for e in entries:
        entries_by_game.setdefault(e.game_id, []).append(e)

    winner_by_game: Dict[int, Optional[str]] = {g.id: g.winner_player for g in games if g.id is not None}

    # lista players per tendina
    players_set = sorted({e.player.strip() for e in entries if e.player and e.player.strip()}, key=str.lower)

    if not player or player not in players_set:
        player = players_set[0] if players_set else ""

    # --- stats del player selezionato ---
    played_gids = [gid for gid, es in entries_by_game.items() if any(x.player == player for x in es)]
    total_games = len(played_gids)
    total_wins = sum(1 for gid in played_gids if winner_by_game.get(gid) == player)
    total_wr = round((total_wins / total_games) * 100.0, 1) if total_games else 0.0

    # commander usage + winrate (per quel player)
    cmd_games: Dict[str, set] = {}
    cmd_wins: Dict[str, int] = {}
    for gid in played_gids:
        winner = winner_by_game.get(gid)
        for e in entries_by_game.get(gid, []):
            if e.player != player:
                continue
            c = e.commander
            cmd_games.setdefault(c, set()).add(gid)
            if winner == player:
                cmd_wins[c] = cmd_wins.get(c, 0) + 1

    cmd_rows = []
    for c, gset in cmd_games.items():
        g = len(gset)
        w = cmd_wins.get(c, 0)
        wr = (w / g) * 100.0 if g else 0.0
        cmd_rows.append((c, g, w, wr))
    cmd_rows.sort(key=lambda x: (-x[3], -x[1], x[0].lower()))
    cmd_rows = cmd_rows[:top_cmd]

    # pairing player+commander (per quel player) -> winrate, min games
    pair_games: Dict[Tuple[str, str], set] = {}
    pair_wins: Dict[Tuple[str, str], int] = {}

    for gid in played_gids:
        winner = winner_by_game.get(gid)
        for e in entries_by_game.get(gid, []):
            if e.player != player:
                continue
            key = (e.player, e.commander)
            pair_games.setdefault(key, set()).add(gid)
            if winner == player:
                pair_wins[key] = pair_wins.get(key, 0) + 1

    pair_rows = []
    for (p, c), gset in pair_games.items():
        g = len(gset)
        if g < min_pair:
            continue
        w = pair_wins.get((p, c), 0)
        wr = (w / g) * 100.0 if g else 0.0
        pair_rows.append((p, c, g, w, wr))
    pair_rows.sort(key=lambda x: (-x[4], -x[2], x[1].lower()))
    pair_rows = pair_rows[:top_pairs]

    payload = {
        "params": {"player": player, "min_pair": min_pair, "top_cmd": top_cmd, "top_pairs": top_pairs},
        "players": players_set,
        "summary": {"games": total_games, "wins": total_wins, "winrate": total_wr},
        "commanderWinrate": {
            "labels": [c for (c, _, _, _) in cmd_rows],
            "values": [round(wr, 1) for (_, _, _, wr) in cmd_rows],
            "rows": [{"commander": c, "games": g, "wins": w, "winrate": round(wr, 1)} for (c, g, w, wr) in cmd_rows],
        },
        "pairingWinrate": {
            "labels": [f"{p} — {c}" for (p, c, _, _, _) in pair_rows],
            "values": [round(wr, 1) for (_, _, _, _, wr) in pair_rows],
            "rows": [{"player": p, "commander": c, "games": g, "wins": w, "winrate": round(wr, 1)} for (p, c, g, w, wr) in pair_rows],
        },
    }
    return payload

@app.get("/player_dashboard", response_class=HTMLResponse)
def player_dashboard(
    request: Request,
    player: str = "",
    min_pair: int = 1,
    top_cmd: int = 10,
    top_pairs: int = 30,
) -> HTMLResponse:
    payload = build_player_dashboard_payload(player, min_pair, top_cmd, top_pairs)
    resp = templates.TemplateResponse("player_dashboard.html", {"request": request, "chart_data": payload})
    resp.headers["Cache-Control"] = "no-store"
    return resp
@app.get("/player_dashboard.pdf")
def player_dashboard_pdf(
    request: Request,
    player: str = "",
    min_pair: int = 1,
    top_cmd: int = 10,
    top_pairs: int = 30,
) -> StreamingResponse:
    # Usa la stessa query string della pagina corrente
    qs = request.url.query
    url = "http://127.0.0.1:8000/player_dashboard"
    if qs:
        url += f"?{qs}"

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # viewport coerente con A4 landscape (~96dpi)
        page = browser.new_page(viewport={"width": 1684, "height": 1191})

        # usa media "screen" così la pagina rende come desktop
        page.emulate_media(media="screen")

        page.goto(url, wait_until="networkidle")

        # attesa rendering (più generosa)
        page.wait_for_timeout(1800)

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            page.pdf(
                path=tmp.name,
                format="A4",
                landscape=True,
                print_background=True,
                prefer_css_page_size=True,  # rispetta meglio eventuale CSS di stampa
                margin={
                    "top": "8mm",
                    "bottom": "8mm",
                    "left": "8mm",
                    "right": "8mm",
                },
            )
            pdf_path = tmp.name

        browser.close()

    return StreamingResponse(
        open(pdf_path, "rb"),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=commander_player_dashboard.pdf"},
    )

@app.get("/player_dashboard.html")
def player_dashboard_export_html(
    request: Request,
    player: str = "",
    min_pair: int = 1,
    top_cmd: int = 10,
    top_pairs: int = 30,
) -> Response:
    payload = build_player_dashboard_payload(player, min_pair, top_cmd, top_pairs)
    rendered = templates.get_template("player_dashboard.html").render({"request": request, "chart_data": payload})

    return Response(
        content=rendered,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="commander_player_dashboard.html"'},
    )

# =============================================================================
# BRACKET-WISE PLAYER DASHBOARD (separate endpoint + template)
# =============================================================================

def build_player_dashboard_payload_bracket(
    player: str,
    min_pair: int,
    top_cmd: int,
    top_pairs: int,
) -> dict:
    min_pair = max(1, int(min_pair))
    top_cmd = max(1, min(50, int(top_cmd)))
    top_pairs = max(1, min(200, int(top_pairs)))

    with get_session() as session:
        games = session.exec(select(Game)).all()
        entries = session.exec(select(GameEntry)).all()

    entries_by_game: Dict[int, List[GameEntry]] = {}
    for e in entries:
        entries_by_game.setdefault(e.game_id, []).append(e)

    winner_by_game: Dict[int, Optional[str]] = {g.id: g.winner_player for g in games if g.id is not None}
    time_by_game: Dict[int, datetime] = {g.id: g.played_at for g in games if g.id is not None}

    # player list for dropdown
    players_set = sorted({e.player.strip() for e in entries if e.player and e.player.strip()}, key=str.lower)
    player = (player or "").strip()
    if not player or player not in players_set:
        player = players_set[0] if players_set else ""

    if not player:
        return {
            "params": {"player": "", "min_pair": min_pair, "top_cmd": top_cmd, "top_pairs": top_pairs},
            "players": [],
            "trend": {"labels": [], "values": []},
            "podWinrate": {"labels": [], "values": [], "baseline": [], "denom": []},
            "topCommanders": {"labels": [], "values": [], "rows": []},
            "pairingBubble": {"minGames": min_pair, "rows": []},
        }

    # games where player participated
    player_game_ids = sorted(
        [gid for gid, es in entries_by_game.items() if any(x.player == player for x in es)],
        key=lambda gid: time_by_game.get(gid, datetime.min),
    )

    # Trend: skill-adjusted (cumulative weighted wr).
    # Denominator is win-weighted so that WR remains bounded in [0,100]
    # even when underdog wins get rewarded (w > 1).
    trend_labels: List[str] = []
    trend_values: List[float] = []
    total = 0
    total_w = 0.0
    weighted_wins = 0.0
    for gid in player_game_ids:
        total += 1
        total_w += 1.0
        winner = winner_by_game.get(gid)
        es = entries_by_game.get(gid, [])
        b_avg = compute_table_bracket_avg(es)
        b_w = compute_winner_bracket(es, winner)
        w = None
        if b_avg is not None and b_w is not None:
            w = win_weight_from_delta(float(b_w) - float(b_avg))
        if winner == player:
            w_eff = float(w) if w is not None else 1.0
            weighted_wins += w_eff
            total_w += (w_eff - 1.0)
        wr = (weighted_wins / total_w) * 100.0 if total_w else 0.0
        dt = time_by_game.get(gid)
        trend_labels.append(dt.strftime("%Y-%m-%d") if dt else f"game {gid}")
        trend_values.append(round(wr, 1))

    # Pod winrate: keep classic baseline, but value = bracket-adjusted WR within that pod size
    pod_games: Dict[int, int] = {}
    pod_weighted_wins: Dict[int, float] = {}
    pod_weighted_games: Dict[int, float] = {}
    for gid in player_game_ids:
        es = entries_by_game.get(gid, [])
        n = len(es)
        if n <= 0:
            continue
        pod_games[n] = pod_games.get(n, 0) + 1
        pod_weighted_games[n] = pod_weighted_games.get(n, 0.0) + 1.0

        winner = winner_by_game.get(gid)
        b_avg = compute_table_bracket_avg(es)
        b_w = compute_winner_bracket(es, winner)
        w = None
        if b_avg is not None and b_w is not None:
            w = win_weight_from_delta(float(b_w) - float(b_avg))
        if winner == player:
            w_eff = float(w) if w is not None else 1.0
            pod_weighted_wins[n] = pod_weighted_wins.get(n, 0.0) + w_eff
            pod_weighted_games[n] = pod_weighted_games.get(n, 0.0) + (w_eff - 1.0)

    pod_sizes = sorted(pod_games.keys())
    pod_labels = [f"{n}p" for n in pod_sizes]
    pod_values = []
    pod_denoms = []
    pod_baseline = []
    for n in pod_sizes:
        denom = pod_weighted_games.get(n, float(pod_games.get(n, 0)))
        ww = pod_weighted_wins.get(n, 0.0)
        wr = (ww / denom) * 100.0 if denom else 0.0
        pod_values.append(round(wr, 1))
        pod_denoms.append(pod_games.get(n, 0))
        pod_baseline.append(round((1.0 / n) * 100.0, 1))

    # Commander stats for the selected player:
    # - Weighted WR% (sum weights of wins / games played with that commander)
    # - BPI: mean deltaB in wins (only when computable), label qualitative
    cmd_games: Dict[str, set] = {}
    cmd_weighted_wins: Dict[str, float] = {}
    cmd_weighted_games: Dict[str, float] = {}
    cmd_delta_sum_in_wins: Dict[str, float] = {}
    cmd_delta_n_in_wins: Dict[str, int] = {}

    for gid in player_game_ids:
        es = entries_by_game.get(gid, [])
        winner = winner_by_game.get(gid)
        b_avg = compute_table_bracket_avg(es)
        b_w = compute_winner_bracket(es, winner)
        w = None
        delta = None
        if b_avg is not None and b_w is not None:
            delta = float(b_w) - float(b_avg)
            w = win_weight_from_delta(delta)

        # find player's commander in this game
        p_cmd = None
        for e in es:
            if e.player == player:
                p_cmd = e.commander
                break
        if not p_cmd:
            continue

        cmd_games.setdefault(p_cmd, set()).add(gid)
        cmd_weighted_games[p_cmd] = cmd_weighted_games.get(p_cmd, 0.0) + 1.0

        if winner == player:
            w_eff = float(w) if w is not None else 1.0
            cmd_weighted_wins[p_cmd] = cmd_weighted_wins.get(p_cmd, 0.0) + w_eff
            cmd_weighted_games[p_cmd] = cmd_weighted_games.get(p_cmd, 0.0) + (w_eff - 1.0)
            if delta is not None:
                cmd_delta_sum_in_wins[p_cmd] = cmd_delta_sum_in_wins.get(p_cmd, 0.0) + delta
                cmd_delta_n_in_wins[p_cmd] = cmd_delta_n_in_wins.get(p_cmd, 0) + 1

    cmd_rows = []
    for c, gids in cmd_games.items():
        games_n = len(gids)
        if games_n < min_pair:
            continue
        ww = cmd_weighted_wins.get(c, 0.0)
        wg = cmd_weighted_games.get(c, float(games_n))
        wr_w = (ww / wg) * 100.0 if wg else 0.0

        nwin = cmd_delta_n_in_wins.get(c, 0)
        bpi = (cmd_delta_sum_in_wins.get(c, 0.0) / nwin) if nwin else None
        cmd_rows.append((c, games_n, wr_w, bpi))

    cmd_rows.sort(key=lambda x: (-x[2], -x[1], x[0].lower()))
    cmd_rows = cmd_rows[:top_cmd]

    # Bubble: keep like original but y = weighted wr
    pair_stats: Dict[Tuple[str, str], Dict[str, object]] = {}
    for gid in player_game_ids:
        es = entries_by_game.get(gid, [])
        winner = winner_by_game.get(gid)
        b_avg = compute_table_bracket_avg(es)
        b_w = compute_winner_bracket(es, winner)
        w = None
        if b_avg is not None and b_w is not None:
            w = win_weight_from_delta(float(b_w) - float(b_avg))

        for e in es:
            if e.player != player:
                continue
            key = (e.player, e.commander)
            pair_stats.setdefault(key, {"games": set(), "weighted_wins": 0.0, "weighted_games": 0.0})
            pair_stats[key]["games"].add(gid)
            pair_stats[key]["weighted_games"] += 1.0
            if winner == player:
                w_eff = float(w) if w is not None else 1.0
                pair_stats[key]["weighted_wins"] += w_eff
                pair_stats[key]["weighted_games"] += (w_eff - 1.0)

    bubble_rows = []
    for (p, c), v in pair_stats.items():
        games_n = len(v["games"])
        if games_n < min_pair:
            continue
        ww = float(v["weighted_wins"])
        wg = float(v.get("weighted_games") or games_n)
        wr_w = (ww / wg) * 100.0 if wg else 0.0
        r = 4 + min(16, int((games_n ** 0.5) * 3))
        bubble_rows.append(
            {"player": p, "commander": c, "games": games_n, "weighted_winrate": round(wr_w, 1), "r": r}
        )

    bubble_rows.sort(key=lambda x: (-x["games"], -x["weighted_winrate"], x["commander"].lower()))
    bubble_rows = bubble_rows[:top_pairs]

    payload = {
        "params": {"player": player, "min_pair": min_pair, "top_cmd": top_cmd, "top_pairs": top_pairs},
        "players": players_set,
        "trend": {"labels": trend_labels, "values": trend_values},
        "podWinrate": {"labels": pod_labels, "values": pod_values, "baseline": pod_baseline, "denom": pod_denoms},
        "topCommanders": {
            "labels": [c for (c, _, _, _) in cmd_rows],
            "values": [round(wr_w, 1) for (_, _, wr_w, _) in cmd_rows],
            "rows": [
                {
                    "commander": c,
                    "games": g,
                    "weighted_winrate": round(wr_w, 1),
                    "bpi": (round(bpi, 2) if bpi is not None else None),
                    "bpi_label": bpi_label(bpi),
                }
                for (c, g, wr_w, bpi) in cmd_rows
            ],
        },
        "pairingBubble": {"minGames": min_pair, "rows": bubble_rows},
    }
    return payload


@app.get("/player_dashboard_bracket", response_class=HTMLResponse)
def player_dashboard_bracket(
    request: Request,
    player: str = "",
    min_pair: int = 1,
    top_cmd: int = 10,
    top_pairs: int = 30,
) -> HTMLResponse:
    payload = build_player_dashboard_payload_bracket(player, min_pair, top_cmd, top_pairs)
    resp = templates.TemplateResponse("player_dashboard_bracket.html", {"request": request, "chart_data": payload})
    resp.headers["Cache-Control"] = "no-store"
    return resp


# =============================================================================
# COMMANDER BRACKET MANAGEMENT
# =============================================================================

def commander_bracket_summary() -> List[Dict]:
    """Return per-commander bracket stats from GameEntry.

    - current_bracket: the modal (most common) non-null bracket, if any
    - counts: dict {1..5: count, "n/a": count}
    """
    with get_session() as session:
        rows = session.exec(select(GameEntry.commander, GameEntry.bracket)).all()

    agg: Dict[str, Dict] = {}
    for commander, bracket in rows:
        if not commander or not commander.strip():
            continue
        key = commander.strip()
        rec = agg.setdefault(key, {"commander": key, "total": 0, "counts": {1:0,2:0,3:0,4:0,5:0,"n/a":0}})
        rec["total"] += 1
        if bracket is None:
            rec["counts"]["n/a"] += 1
        else:
            try:
                b = int(bracket)
            except Exception:
                rec["counts"]["n/a"] += 1
            else:
                if 1 <= b <= 5:
                    rec["counts"][b] += 1
                else:
                    rec["counts"]["n/a"] += 1

    out: List[Dict] = []
    for rec in agg.values():
        # mode among 1..5
        mode_b = None
        best = 0
        for b in (1,2,3,4,5):
            c = rec["counts"][b]
            if c > best:
                best = c
                mode_b = b
        rec["current_bracket"] = mode_b  # None if no non-null brackets
        out.append(rec)

    out.sort(key=lambda r: r["commander"].lower())
    return out


@app.get("/commander_brackets", response_class=HTMLResponse)
def commander_brackets(request: Request) -> HTMLResponse:
    summary = commander_bracket_summary()
    return templates.TemplateResponse(
        "commander_brackets.html",
        {"request": request, "summary": summary, "error": None, "ok": request.query_params.get("ok")},
    )


@app.post("/commander_brackets/set")
def commander_brackets_set(
    commander: str = Form(...),
    bracket_value: str = Form(""),
) -> RedirectResponse:
    cmd = (commander or "").strip()
    if not cmd:
        return RedirectResponse(url="/commander_brackets?ok=0", status_code=303)

    token = (bracket_value or "").strip().lower()
    if token in {"", "n/a", "na", "none", "null"}:
        new_b: Optional[int] = None
    else:
        try:
            new_b_int = int(token)
        except ValueError:
            raise HTTPException(status_code=400, detail="Bracket non valido (usa 1-5 o n/a).")
        if new_b_int < 1 or new_b_int > 5:
            raise HTTPException(status_code=400, detail="Bracket fuori range (1-5).")
        new_b = new_b_int

    # Apply to ALL instances of that commander (case-insensitive match)
    with get_session() as session:
        entries = session.exec(
            select(GameEntry).where(func.lower(GameEntry.commander) == cmd.lower())
        ).all()
        for e in entries:
            e.bracket = new_b
            session.add(e)
        session.commit()

    return RedirectResponse(url="/commander_brackets?ok=1", status_code=303)
