# Stats-only static exporter (pulito)

Questo pacchetto contiene **solo** i file necessari (DB escluso) per generare la pagina **Stats** su GitHub Pages usando JSON.

## Uso rapido

```bash
pip install -r requirements.txt
python export_stats_light.py --db /percorso/commander_tracker.sqlite
```

Output:
- `docs/data/stats.v1.json`
- `docs/stats/index.html`
- `docs/assets/stats.js`

## GitHub Pages
Configura Pages per pubblicare la cartella `docs/`.

Nota: lo script **non** include il DB. Devi passare il path con `--db`.
