# Commander Tracker – Stats (GitHub Pages)

Questo progetto genera una pagina `docs/stats/` con statistiche **win rate (vittorie / partite)** aggregabili e filtrabili per:
- Player
- Player + Commander
- Bracket

## Requisiti
- Python 3.10+ (nessuna dipendenza esterna)

## Generazione sito
```bash
python export_stats.py --db data/commander_tracker.sqlite --docs docs
python -m http.server -d docs 8000
# poi apri http://localhost:8000/stats/
```

## Output
- `docs/data/stats.v1.json`
- `docs/stats/index.html` + assets
