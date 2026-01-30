from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy import Index
from sqlmodel import Field, Session, SQLModel, create_engine


class Game(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    played_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    notes: Optional[str] = None
    winner_player: Optional[str] = Field(default=None, index=True)  # opzionale


class GameEntry(SQLModel, table=True):
    __table_args__ = (
        Index('ix_gameentry_player_commander', 'player', 'commander'),
        Index('ix_gameentry_player_game', 'player', 'game_id'),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id", index=True)
    player: str = Field(index=True)
    commander: str = Field(index=True)
    bracket: Optional[int] = Field(default=None, index=True)

# =============================================================================
# Engine / session
# =============================================================================

def make_engine(db_path: str | Path):
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")
    return create_engine(f"sqlite:///{db_path}", echo=False)


def get_session(engine) -> Session:
    return Session(engine)


def migrate_schema(engine) -> None:
    """Apply small, safe migrations (adds 'bracket' column + indexes if missing)."""
    with engine.connect() as conn:
        res = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='gameentry';"
        ).fetchone()
        if not res:
            return

        cols = conn.exec_driver_sql("PRAGMA table_info('gameentry');").fetchall()
        col_names = {c[1] for c in cols}
        if "bracket" not in col_names:
            conn.exec_driver_sql("ALTER TABLE gameentry ADD COLUMN bracket INTEGER;")
            conn.commit()

        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_game_played_at ON game(played_at);")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_game_winner_player ON game(winner_player);")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_gameentry_game_id ON gameentry(game_id);")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_gameentry_player ON gameentry(player);")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_gameentry_commander ON gameentry(commander);")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_gameentry_bracket ON gameentry(bracket);")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_gameentry_player_commander ON gameentry(player, commander);")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_gameentry_player_game ON gameentry(player, game_id);")
        conn.commit()

def compute_table_bracket_avg(entries: List[GameEntry]) -> Optional[float]:
    """Average bracket at the table (ignoring n/a). Returns None if no brackets."""
    vals = [e.bracket for e in entries if e.bracket is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)

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

def build_entries_by_game(entries: List[GameEntry]) -> Dict[int, List[GameEntry]]:
    by_game: Dict[int, List[GameEntry]] = {}
    for e in entries:
        by_game.setdefault(e.game_id, []).append(e)
    return by_game

