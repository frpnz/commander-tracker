# Commander Tracker — Hardening Audit

Date: 2026-09-18

## Scope

Conservative pre-extension hardening. No historical game or draft data were rewritten.

## Implemented

- Centralized `game.v1` validation for player/commander presence, bracket `1..5`, winner membership, and duplicate-player rejection.
- JSON batch import is now all-or-nothing: validation happens before writes and insertion uses an explicit rollback-safe transaction.
- Commander admin prevents new duplicate players, invalid bracket values, and winners outside the game entries.
- Renaming/deleting a winning entry keeps `winner_player` coherent; global player rename is blocked if it would merge two identities in one game.
- New games start as drafts with `winner_player = NULL`; export blocks games with fewer than two entries.
- Pre-export database validator checks foreign keys, empty identities, bracket range, orphan winners, minimum pod size, and duplicate players.
- Known ambiguous historical duplicate-player games are explicit exceptions in `data/validation_exceptions.json`: `45`, `47`, `55`. They remain warnings in normal export and errors under `--strict-duplicates`.
- `stats.v1.schema.json` is aligned with the real payload, including integer brackets, `pod_size`, `pod_sizes`, `games`, and `by_player_count` nested payloads.
- Exported float values are canonicalized to 14 significant digits to remove platform-level last-bit noise while preserving metric values far beyond UI precision.
- Removed unused weighted/WBD/meta-wins computations from `compute.py`. Raw `compute_stats()` output was verified byte-identical to the original baseline after this cleanup.
- `publish.sh` now falls back to system `python3`, checkpoints both SQLite DBs without requiring the sqlite3 CLI, runs tests and validation before export, rebuilds all of `docs/`, and stages both frontend source and generated static content.
- Commander and Draft admin/database paths now close SQLite connections reliably; Draft export also closes its connection on success or failure.
- Fixed an accidental duplicated SQL literal in the Commander game-detail query.
- Added a standard-library regression suite in `tests/test_hardening.py`.

## Historical data deliberately not changed

The following games contain an ambiguous duplicated player identity and cannot be corrected safely without external information:

- Game 45 — `Matti`
- Game 47 — `Matti`
- Game 55 — `Da`

The exporter allows only these configured legacy exceptions. Any new unconfigured duplicate is a blocking validation error.

## Final audit results

- Python syntax: PASS
- JavaScript syntax: PASS
- `scripts/publish.sh` shell syntax: PASS
- Automated tests: **17/17 PASS**
- Tests with `ResourceWarning` promoted to error: PASS
- Commander SQLite `integrity_check`: `ok`
- Commander foreign-key violations: `0`
- Draft SQLite `integrity_check`: `ok`
- Draft foreign-key violations: `0`
- Commander DB byte-identical to supplied original: YES
- Draft DB byte-identical to supplied original: YES
- `stats.v1.json` vs JSON Schema: **0 errors**
- Commander counts after hardening: **155 games / 534 entries**
- Baseline structural/non-float differences: **0**
- Float-only differences caused by canonicalization: max absolute delta **5.02e-14**
- Draft JSON byte-identical to baseline: YES
- Repeated full export byte-deterministic: PASS
- `frontend/site` vs generated `docs/` static assets: synchronized
- Strict duplicate validation: correctly fails on games `45`, `47`, `55`

## Commands

Validate Commander DB:

```bash
python3 backend/validate_db.py --db data/commander_tracker.sqlite
```

Strict legacy duplicate check:

```bash
python3 backend/validate_db.py --db data/commander_tracker.sqlite --strict-duplicates
```

Run tests:

```bash
python3 -m unittest discover -s tests -v
```

Export:

```bash
python3 backend/export_stats.py \
  --db data/commander_tracker.sqlite \
  --draft-db data/draft_tracker.sqlite \
  --docs docs
```

Publish:

```bash
bash scripts/publish.sh "Update Commander tracker"
```
