# Draft Admin (stdlib)

Questo server è **solo locale** e serve a gestire un DB separato per i tornei Draft.

## Avvio

```bash
# dalla root del repo
python backend/admin_draft_stdlib.py
```

Variabili ambiente:

- `DRAFT_DB` (default: `./data/draft_tracker.sqlite`)
- `ADMIN_HOST` (default: `127.0.0.1`)
- `ADMIN_PORT` (default: `8010`)

## Accesso via SSH tunnel

```bash
ssh -L 8081:127.0.0.1:8010 user@SERVER
open http://127.0.0.1:8081/draft/tournaments
```

## Import da MTG Companion

Incolla le standings nel formato:

- `Nome  W-L-D  VIA%`

Sono accettati spazi o tab.

Esempio:

```
Marco Rossi\t3-0-0\t67.89
Giulia\t2-1-0\t55.50%
Ale 1-2-0 44.12
```

## Export JSON per il sito statico

```bash
python backend/export_draft.py --db data/draft_tracker.sqlite --docs docs
```

Scrive `docs/data/draft.v1.json` (che la pagina `Draft` carica).
