from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy import Index
from sqlmodel import Field, Session, SQLModel, create_engine


# =============================================================================
# DB MODELS (compatible with commander_tracker.sqlite)
# =============================================================================


class Game(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    played_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    notes: Optional[str] = None
    winner_player: Optional[str] = Field(default=None, index=True)


class GameEntry(SQLModel, table=True):
    __table_args__ = (
        Index("ix_gameentry_player_commander", "player", "commander"),
        Index("ix_gameentry_player_game", "player", "game_id"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id", index=True)
    player: str = Field(index=True)
    commander: str = Field(index=True)
    bracket: Optional[int] = Field(default=None, index=True)


# =============================================================================
# DB helpers
# =============================================================================


def make_engine(db_path: str | Path):
    db_path = Path(db_path)
    return create_engine(f"sqlite:///{db_path}", echo=False)


def session_from(db_path: str | Path) -> Session:
    """Open a SQLModel session against the given sqlite db file."""
    return Session(make_engine(db_path))


# =============================================================================
# Domain helpers used by Stats
# =============================================================================


def build_entries_by_game(entries: List[GameEntry]) -> Dict[int, List[GameEntry]]:
    by_game: Dict[int, List[GameEntry]] = {}
    for e in entries:
        by_game.setdefault(e.game_id, []).append(e)
    return by_game


def compute_table_bracket_avg(entries: List[GameEntry]) -> Optional[float]:
    """Average bracket at the table (ignoring n/a). Returns None if no brackets."""
    vals = [e.bracket for e in entries if e.bracket is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def win_weight_from_delta(delta_b: float, alpha: float = 0.5) -> float:
    """Weight applied to a win based on bracket mismatch.

    delta_b = B_winner - B_avg (winner bracket minus table average)

    - delta_b > 0: penalize win
    - delta_b == 0: neutral
    - delta_b < 0: reward win

    The weighted winrate remains bounded in [0, 100] if you also weight the denominator.
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






