# Commander Tracker

Small FastAPI + SQLModel (SQLite) web app to track Commander games (players, commanders, optional bracket).

## Requirements

- **Python >= 3.10**
- pip
- Virtualenv strongly recommended

## Run (dev)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Open: http://127.0.0.1:8000/

## Data storage

SQLite file is created under `./data/commander_tracker.sqlite` (relative to `app.py`).

## PDF export (Playwright)

PDF endpoints render the corresponding HTML page via headless Chromium.

By default, the server will use `request.base_url` to build the URL that Chromium opens.
If your deployment requires a different internal URL (container, reverse proxy, etc.), set:

```bash
export RENDER_BASE_URL="http://127.0.0.1:8000"
```
