# Commander Tracker (bracket 1–5)

## Avvio
```bash
uvicorn app:app --host 0.0.0.0 --port 8000
# oppure (sviluppo)
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

## Novità
- Campo `bracket` (1–5) su Game (retrocompatibile: può essere vuoto).
- Add/Edit partita: select bracket.
- Filtri per bracket su:
  - /dashboard_mini
  - /player_dashboard
  - /stats
- Grafici aggiuntivi in dashboard e player_dashboard.
- Import CSV supporta la colonna `bracket` (se manca, resta vuoto).
