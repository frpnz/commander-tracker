# Stats-only static export

Genera la pagina **Stats** per GitHub Pages:
- `docs/data/stats.v1.json`
- `docs/stats/index.html`

## Install

```bash
pip install -r requirements.txt
```

## Export

```bash
python export_stats_light.py --db /path/to/commander_tracker.sqlite
```

## Preview locale

```bash
python -m http.server -d docs 8000
```
Apri: http://localhost:8000/stats/
