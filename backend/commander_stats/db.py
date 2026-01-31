from __future__ import annotations
import sqlite3

def connect(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection with Row factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn
