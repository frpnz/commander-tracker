from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import Any, Iterable


class PayloadValidationError(ValueError):
    """Raised when a game.v1 payload is not semantically valid."""


class DatabaseValidationError(RuntimeError):
    """Raised when blocking database integrity issues are found before export."""

    def __init__(self, issues: list["ValidationIssue"]):
        self.issues = issues
        super().__init__("; ".join(issue.message for issue in issues))


@dataclass(frozen=True)
class ValidationIssue:
    severity: str  # "error" or "warning"
    code: str
    message: str
    game_id: int | None = None


def normalize_bracket(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise PayloadValidationError("bracket deve essere un intero tra 1 e 5")
    try:
        bracket = int(value)
    except (TypeError, ValueError) as exc:
        raise PayloadValidationError("bracket deve essere un intero tra 1 e 5") from exc
    if bracket < 1 or bracket > 5:
        raise PayloadValidationError("bracket deve essere compreso tra 1 e 5")
    return bracket


def normalize_game_payload(item: Any, *, label: str = "Payload") -> dict[str, Any]:
    """Normalize and validate one public game.v1 payload without touching the DB."""
    if not isinstance(item, dict):
        raise PayloadValidationError(f"{label}: non è un oggetto JSON valido")
    if item.get("version") != "game.v1":
        raise PayloadValidationError(f"{label}: versione payload non supportata")

    played_at_raw = item.get("played_at")
    played_at = played_at_raw.strip() if isinstance(played_at_raw, str) else ""
    if not played_at:
        raise PayloadValidationError(f"{label}: played_at è obbligatorio")

    notes = item.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise PayloadValidationError(f"{label}: notes deve essere una stringa o null")

    winner_raw = item.get("winner_player")
    if winner_raw is None:
        winner = None
    elif isinstance(winner_raw, str):
        winner = winner_raw.strip() or None
    else:
        raise PayloadValidationError(f"{label}: winner_player deve essere una stringa o null")

    entries = item.get("entries")
    if not isinstance(entries, list) or len(entries) < 2:
        raise PayloadValidationError(f"{label}: entries deve essere una lista con almeno 2 elementi")

    normalized_entries: list[dict[str, Any]] = []
    player_keys: set[str] = set()
    players_exact: set[str] = set()

    for entry_idx, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise PayloadValidationError(f"{label}: entry #{entry_idx} non valida")
        player_raw = entry.get("player")
        commander_raw = entry.get("commander")
        player = player_raw.strip() if isinstance(player_raw, str) else ""
        commander = commander_raw.strip() if isinstance(commander_raw, str) else ""
        if not player or not commander:
            raise PayloadValidationError(f"{label}: ogni entry richiede player e commander")

        player_key = player.casefold()
        if player_key in player_keys:
            raise PayloadValidationError(f"{label}: player duplicato nella stessa partita: {player}")
        player_keys.add(player_key)
        players_exact.add(player)

        try:
            bracket = normalize_bracket(entry.get("bracket"))
        except PayloadValidationError as exc:
            raise PayloadValidationError(f"{label}: bracket non valido per {player}: {exc}") from exc

        normalized_entries.append({"player": player, "commander": commander, "bracket": bracket})

    if winner is not None and winner not in players_exact:
        raise PayloadValidationError(f"{label}: winner_player deve essere uno dei player nelle entries")

    return {
        "played_at": played_at,
        "notes": notes,
        "winner_player": winner,
        "entries": normalized_entries,
    }


def _fetchall(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    return list(conn.execute(sql, tuple(params)).fetchall())


def validate_database(
    conn: sqlite3.Connection,
    *,
    duplicate_players_are_errors: bool = False,
    allowed_duplicate_game_ids: set[int] | frozenset[int] | None = None,
) -> list[ValidationIssue]:
    """Validate invariants relied on by the statistics exporter.

    Duplicate players are errors unless their game id is explicitly listed as
    a legacy exception. New duplicates are therefore blocked even when the current
    historical DB still contains a small set of known ambiguous records.
    """
    issues: list[ValidationIssue] = []

    for row in conn.execute("PRAGMA foreign_key_check").fetchall():
        issues.append(
            ValidationIssue(
                "error",
                "foreign_key",
                f"Foreign-key violation: table={row[0]} rowid={row[1]} parent={row[2]}",
            )
        )

    for row in _fetchall(
        conn,
        """
        SELECT id, game_id, player, commander, bracket
        FROM gameentry
        WHERE TRIM(COALESCE(player, '')) = ''
           OR TRIM(COALESCE(commander, '')) = ''
           OR (bracket IS NOT NULL AND (bracket < 1 OR bracket > 5))
        ORDER BY game_id, id
        """,
    ):
        game_id = int(row["game_id"])
        if not str(row["player"] or "").strip():
            issues.append(ValidationIssue("error", "empty_player", f"Game {game_id}: entry {row['id']} ha player vuoto", game_id))
        if not str(row["commander"] or "").strip():
            issues.append(ValidationIssue("error", "empty_commander", f"Game {game_id}: entry {row['id']} ha commander vuoto", game_id))
        if row["bracket"] is not None and not 1 <= int(row["bracket"]) <= 5:
            issues.append(ValidationIssue("error", "invalid_bracket", f"Game {game_id}: entry {row['id']} ha bracket fuori range: {row['bracket']}", game_id))

    for row in _fetchall(
        conn,
        """
        SELECT g.id, COUNT(ge.id) AS n
        FROM game g
        LEFT JOIN gameentry ge ON ge.game_id = g.id
        GROUP BY g.id
        HAVING COUNT(ge.id) < 2
        ORDER BY g.id
        """,
    ):
        gid = int(row["id"])
        issues.append(ValidationIssue("error", "too_few_entries", f"Game {gid}: solo {row['n']} entry; ne servono almeno 2 per l'export", gid))

    for row in _fetchall(
        conn,
        """
        SELECT g.id, g.winner_player
        FROM game g
        WHERE g.winner_player IS NOT NULL
          AND TRIM(g.winner_player) <> ''
          AND NOT EXISTS (
              SELECT 1 FROM gameentry ge
              WHERE ge.game_id = g.id AND ge.player = g.winner_player
          )
        ORDER BY g.id
        """,
    ):
        gid = int(row["id"])
        issues.append(ValidationIssue("error", "orphan_winner", f"Game {gid}: winner '{row['winner_player']}' non presente tra le entries", gid))

    # Detect duplicates case-insensitively in Python, so the rule matches the UI
    # even for names containing non-ASCII characters.
    rows = _fetchall(conn, "SELECT id, game_id, player FROM gameentry ORDER BY game_id, id")
    seen_by_game: dict[int, dict[str, str]] = {}
    duplicate_reported: set[tuple[int, str]] = set()
    allowed_duplicates = set(allowed_duplicate_game_ids or ())
    for row in rows:
        gid = int(row["game_id"])
        player = str(row["player"] or "").strip()
        key = player.casefold()
        if not key:
            continue
        seen = seen_by_game.setdefault(gid, {})
        if key in seen:
            marker = (gid, key)
            if marker not in duplicate_reported:
                severity = "error" if duplicate_players_are_errors or gid not in allowed_duplicates else "warning"
                issues.append(
                    ValidationIssue(
                        severity,
                        "duplicate_player",
                        f"Game {gid}: player duplicato '{seen[key]}'",
                        gid,
                    )
                )
                duplicate_reported.add(marker)
        else:
            seen[key] = player

    return issues


def assert_exportable(
    conn: sqlite3.Connection,
    *,
    duplicate_players_are_errors: bool = False,
    allowed_duplicate_game_ids: set[int] | frozenset[int] | None = None,
) -> list[ValidationIssue]:
    issues = validate_database(
        conn,
        duplicate_players_are_errors=duplicate_players_are_errors,
        allowed_duplicate_game_ids=allowed_duplicate_game_ids,
    )
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        raise DatabaseValidationError(errors)
    return issues
