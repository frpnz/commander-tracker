from __future__ import annotations

import os
import sqlite3

REPO_DEFAULT_DB = os.path.join(os.path.dirname(__file__), "..", "..", "data", "draft_tracker.sqlite")


def connect(db_path: str | None = None) -> sqlite3.Connection:
    path = os.path.abspath(db_path or os.environ.get("DRAFT_DB", REPO_DEFAULT_DB))
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;

        CREATE TABLE IF NOT EXISTS tournament (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            played_at TEXT NOT NULL,
            name TEXT NOT NULL,
            format TEXT NOT NULL DEFAULT 'Draft',
            rounds INTEGER,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS standing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER NOT NULL,
            player TEXT NOT NULL,
            wins INTEGER NOT NULL,
            losses INTEGER NOT NULL,
            draws INTEGER NOT NULL,
            via_pct REAL,
            FOREIGN KEY (tournament_id) REFERENCES tournament(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_standing_tournament_id ON standing(tournament_id);
        CREATE INDEX IF NOT EXISTS idx_standing_player ON standing(player);

        -- Optional playoffs bracket (SF/F for now).
        CREATE TABLE IF NOT EXISTS playoff_match (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER NOT NULL,
            stage TEXT NOT NULL,
            player_a TEXT NOT NULL,
            player_b TEXT NOT NULL,
            winner TEXT NOT NULL,
            FOREIGN KEY (tournament_id) REFERENCES tournament(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_playoff_tournament_id ON playoff_match(tournament_id);
        CREATE INDEX IF NOT EXISTS idx_playoff_stage ON playoff_match(stage);
        """
    )
    conn.commit()
