# OPERATIONS - Setup & Runtime Guide

Operational guide for Commander Dashboard:
environment setup, startup, background execution,
monitoring and shutdown.

---

## Requirements
- Python >= 3.10
- pip
- Linux / macOS
  (Windows supported via WSL)

---

## Virtual environment setup

From project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Upgrade base tools:

```bash
pip install --upgrade pip wheel setuptools
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Install Chromium (required for PDF export):

```bash
playwright install chromium
```

---

## Start application (foreground)

Development / debug mode:

```bash
uvicorn app.app:app --host 127.0.0.1 --port 8000 --reload
```

Open in browser:

```
http://127.0.0.1:8000
```

---

## Start via helper script

If present:

```bash
./setup_and_run.sh
```

The script:
- creates the venv if missing
- installs dependencies
- installs Chromium
- starts the app

---

## Run in background (persistent)

Recommended method: nohup

```bash
nohup uvicorn app.app:app \
  --host 0.0.0.0 \
  --port 8000 \
  > app.log 2>&1 &
```

---

## Application status

Check running process:

```bash
ps aux | grep uvicorn
```

Check listening port:

```bash
lsof -i :8000
```

Or:

```bash
ss -tulnp | grep 8000
```

---

## Logs

Follow application logs:

```bash
tail -f app.log
```

---

## Stop application

Standard method:
1. Get PID:
```bash
ps aux | grep uvicorn
```

2. Stop process:
```bash
kill <PID>
```

Forced (only if needed):
```bash
kill -9 <PID>
```

---

## Restart (background)

```bash
pkill -f uvicorn
nohup uvicorn app.app:app \
  --host 0.0.0.0 \
  --port 8000 \
  > app.log 2>&1 &
```

---

## Operational notes
- PDF export uses Playwright + Chromium
- Chromium is used on-demand
- For real production, consider:
  - gunicorn + uvicorn workers
  - or a systemd service

---

## Suggested extensions
- systemd service
- Nginx reverse proxy
- Docker / docker-compose
- Monitoring
