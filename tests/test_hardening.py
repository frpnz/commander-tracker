from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from commander_stats.compute import compute_stats
from commander_stats.db import connect
from commander_stats.ingest import insert_games_atomic
from commander_stats.validation import (
    PayloadValidationError,
    normalize_game_payload,
    validate_database,
)
import admin_stdlib


SCHEMA_SQL = """
CREATE TABLE game (
    id INTEGER PRIMARY KEY,
    played_at DATETIME NOT NULL,
    notes VARCHAR,
    winner_player VARCHAR
);
CREATE TABLE gameentry (
    id INTEGER PRIMARY KEY,
    game_id INTEGER NOT NULL,
    player VARCHAR NOT NULL,
    commander VARCHAR NOT NULL,
    bracket INTEGER,
    FOREIGN KEY(game_id) REFERENCES game(id)
);
"""


def memory_db(extra_game_constraint: str = "") -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if extra_game_constraint:
        conn.executescript(
            SCHEMA_SQL.replace(
                "winner_player VARCHAR\n);",
                f"winner_player VARCHAR,\n    {extra_game_constraint}\n);",
            )
        )
    else:
        conn.executescript(SCHEMA_SQL)
    return conn


def game_payload(played_at: str = "2026-01-01 20:00:00") -> dict:
    return {
        "version": "game.v1",
        "played_at": played_at,
        "winner_player": "Alice",
        "notes": None,
        "entries": [
            {"player": "Alice", "commander": "A", "bracket": 3},
            {"player": "Bob", "commander": "B", "bracket": 4},
        ],
    }


class PayloadValidationTests(unittest.TestCase):
    def test_valid_payload_normalizes(self):
        out = normalize_game_payload(game_payload())
        self.assertEqual(out["winner_player"], "Alice")
        self.assertEqual(out["entries"][0]["bracket"], 3)

    def test_duplicate_player_is_rejected_case_insensitively(self):
        payload = game_payload()
        payload["entries"][1]["player"] = "alice"
        with self.assertRaises(PayloadValidationError):
            normalize_game_payload(payload)

    def test_winner_must_be_an_entry(self):
        payload = game_payload()
        payload["winner_player"] = "Carol"
        with self.assertRaises(PayloadValidationError):
            normalize_game_payload(payload)

    def test_bracket_must_be_1_to_5(self):
        payload = game_payload()
        payload["entries"][0]["bracket"] = 6
        with self.assertRaises(PayloadValidationError):
            normalize_game_payload(payload)


class TransactionTests(unittest.TestCase):
    def test_batch_insert_rolls_back_on_second_failure(self):
        conn = memory_db("UNIQUE(played_at)")
        try:
            games = [
                normalize_game_payload(game_payload("2026-01-01 20:00:00")),
                normalize_game_payload(game_payload("2026-01-01 20:00:00")),
            ]
            with self.assertRaises(sqlite3.IntegrityError):
                insert_games_atomic(conn, games)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM game").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM gameentry").fetchone()[0], 0)
        finally:
            conn.close()


class DatabaseInvariantTests(unittest.TestCase):
    def test_validator_flags_new_duplicate_but_allows_explicit_legacy_exception(self):
        conn = memory_db()
        try:
            conn.execute("INSERT INTO game(id, played_at, winner_player) VALUES (1, '2026-01-01 20:00:00', 'Alice')")
            conn.executemany(
                "INSERT INTO gameentry(game_id, player, commander, bracket) VALUES (1, ?, ?, ?)",
                [("Alice", "A", 3), ("alice", "B", 4)],
            )
            conn.commit()
            issues = validate_database(conn)
            self.assertTrue(any(i.code == "duplicate_player" and i.severity == "error" for i in issues))
            issues = validate_database(conn, allowed_duplicate_game_ids={1})
            self.assertFalse(any(i.severity == "error" for i in issues))
            self.assertTrue(any(i.code == "duplicate_player" and i.severity == "warning" for i in issues))
        finally:
            conn.close()

    def test_validator_flags_orphan_winner_and_bad_bracket(self):
        conn = memory_db()
        try:
            conn.execute("INSERT INTO game(id, played_at, winner_player) VALUES (1, '2026-01-01 20:00:00', 'Ghost')")
            conn.executemany(
                "INSERT INTO gameentry(game_id, player, commander, bracket) VALUES (1, ?, ?, ?)",
                [("Alice", "A", 6), ("Bob", "B", 4)],
            )
            conn.commit()
            codes = {i.code for i in validate_database(conn)}
            self.assertIn("orphan_winner", codes)
            self.assertIn("invalid_bracket", codes)
        finally:
            conn.close()

    def test_repository_db_has_only_configured_legacy_duplicate_warnings(self):
        exceptions = json.loads((REPO / "data" / "validation_exceptions.json").read_text())
        allowed = {int(v) for v in exceptions["duplicate_player_game_ids"]}
        conn = connect(str(REPO / "data" / "commander_tracker.sqlite"))
        try:
            issues = validate_database(conn, allowed_duplicate_game_ids=allowed)
        finally:
            conn.close()
        errors = [i for i in issues if i.severity == "error"]
        warnings = [i for i in issues if i.severity == "warning"]
        self.assertEqual(errors, [])
        self.assertEqual({i.game_id for i in warnings}, {45, 47, 55})


class AdminHandlerInvariantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "admin.sqlite"
        conn = sqlite3.connect(self.db_path)
        conn.executescript(SCHEMA_SQL)
        conn.execute("INSERT INTO game(id, played_at, winner_player) VALUES (1, '2026-01-01 20:00:00', 'Alice')")
        conn.executemany(
            "INSERT INTO gameentry(id, game_id, player, commander, bracket) VALUES (?, 1, ?, ?, ?)",
            [(1, "Alice", "A", 3), (2, "Bob", "B", 4)],
        )
        conn.commit()
        conn.close()
        self.old_db_path = admin_stdlib.DB_PATH
        admin_stdlib.DB_PATH = str(self.db_path)
        self.handler = admin_stdlib.Handler.__new__(admin_stdlib.Handler)
        self.handler._redirect = lambda url: ("redirect", url)
        self.handler._send_html = lambda body, status=200: ("html", status, body)

    def tearDown(self):
        admin_stdlib.DB_PATH = self.old_db_path
        self.tmp.cleanup()

    def read(self, sql, params=()):
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def test_admin_rejects_duplicate_player_add(self):
        result = self.handler._post_entry_add(1, {
            "player_sel": "__NEW__", "player_new": "alice",
            "commander_sel": "__NEW__", "commander_new": "C",
            "bracket_sel": "3", "bracket_new": "",
        })
        self.assertEqual(result[0], "redirect")
        self.assertIn("error=1", result[1])
        self.assertEqual(self.read("SELECT COUNT(*) FROM gameentry")[0][0], 2)

    def test_admin_rejects_out_of_range_bracket(self):
        result = self.handler._post_entry_add(1, {
            "player_sel": "__NEW__", "player_new": "Carol",
            "commander_sel": "__NEW__", "commander_new": "C",
            "bracket_sel": "__NEW__", "bracket_new": "6",
        })
        self.assertEqual(result[0:2], ("html", 400))
        self.assertEqual(self.read("SELECT COUNT(*) FROM gameentry")[0][0], 2)

    def test_admin_rejects_winner_not_in_game(self):
        result = self.handler._post_game_update(1, {"winner_sel": "Carol", "notes": ""})
        self.assertEqual(result[0], "redirect")
        self.assertIn("error=1", result[1])
        self.assertEqual(self.read("SELECT winner_player FROM game WHERE id=1")[0][0], "Alice")

    def test_renaming_winning_entry_updates_winner(self):
        result = self.handler._post_entry_update(1, {
            "player_sel": "__NEW__", "player_new": "Carol",
            "commander_sel": "A", "commander_new": "",
            "bracket_sel": "3", "bracket_new": "",
        })
        self.assertEqual(result[0], "redirect")
        self.assertEqual(self.read("SELECT winner_player FROM game WHERE id=1")[0][0], "Carol")
        self.assertEqual(self.read("SELECT player FROM gameentry WHERE id=1")[0][0], "Carol")

    def test_deleting_winning_entry_clears_winner(self):
        result = self.handler._post_entry_delete(1)
        self.assertEqual(result[0], "redirect")
        self.assertIsNone(self.read("SELECT winner_player FROM game WHERE id=1")[0][0])

    def test_global_rename_cannot_merge_players_in_same_game(self):
        result = self.handler._post_rename_player({"old_player": "Bob", "new_player": "Alice"})
        self.assertEqual(result[0], "redirect")
        self.assertIn("kind=err", result[1])
        players = [r[0] for r in self.read("SELECT player FROM gameentry ORDER BY id")]
        self.assertEqual(players, ["Alice", "Bob"])


class StatsContractTests(unittest.TestCase):
    def test_basic_stats_fixture(self):
        conn = memory_db()
        try:
            games = [
                normalize_game_payload(game_payload("2026-01-01 20:00:00")),
                normalize_game_payload({
                    **game_payload("2026-01-02 20:00:00"),
                    "winner_player": "Bob",
                }),
            ]
            insert_games_atomic(conn, games)
            stats = compute_stats(conn, generated_utc="2026-01-02T20:00:00Z", include_player_count_splits=False)
            by_player = {r["player"]: r for r in stats["by_player"]}
            self.assertEqual(stats["counts"], {"games": 2, "entries": 4})
            self.assertEqual(by_player["Alice"]["wins"], 1)
            self.assertEqual(by_player["Bob"]["wins"], 1)
        finally:
            conn.close()

    def test_schema_matches_current_computed_payload(self):
        try:
            from jsonschema import Draft202012Validator
        except Exception:
            self.skipTest("jsonschema non installato; dipendenza opzionale di test")

        schema = json.loads((BACKEND / "stats.v1.schema.json").read_text())
        conn = connect(str(REPO / "data" / "commander_tracker.sqlite"))
        try:
            payload = compute_stats(conn)
        finally:
            conn.close()
        errors = list(Draft202012Validator(schema).iter_errors(payload))
        self.assertEqual(errors, [], "\n".join(e.message for e in errors[:10]))

    def test_full_export_is_byte_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            out1 = Path(tmp) / "one"
            out2 = Path(tmp) / "two"
            cmd = [
                sys.executable,
                str(BACKEND / "export_stats.py"),
                "--db", str(REPO / "data" / "commander_tracker.sqlite"),
                "--draft-db", str(REPO / "data" / "draft_tracker.sqlite"),
            ]
            subprocess.run(cmd + ["--docs", str(out1)], cwd=REPO, check=True, capture_output=True, text=True)
            subprocess.run(cmd + ["--docs", str(out2)], cwd=REPO, check=True, capture_output=True, text=True)
            self.assertEqual((out1 / "data" / "stats.v1.json").read_bytes(), (out2 / "data" / "stats.v1.json").read_bytes())
            self.assertEqual((out1 / "data" / "draft.v1.json").read_bytes(), (out2 / "data" / "draft.v1.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
