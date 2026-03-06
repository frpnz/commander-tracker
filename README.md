# Commander Tracker

**Commander Tracker** è un progetto per tracciare partite di *Commander* in **database SQLite** (Commander + Draft), calcolare **statistiche** e pubblicare un **sito statico** (GitHub Pages–friendly).  
Include anche un **tool admin locale** (solo Python standard library) per inserire/modificare partite.

---

## Struttura del progetto

```text
backend/                       # Logica Python (export stats + admin)
  export_stats.py              # Wrapper CLI per l'export (Commander + Draft)
  export_draft.py              # Export Draft standalone (opzionale)
  admin_stdlib.py              # Admin UI locale (HTTP server)
  admin_draft_stdlib.py        # Funzioni admin dominio Draft
  admin_stdlib.md              # Doc dell'admin tool
  commander_stats/             # Moduli di calcolo + rendering output (Commander)
  draft_stats/                 # Moduli di calcolo + rendering output (Draft)
  stats.v1.schema.json         # JSON Schema (contratto dati)

frontend/
  site/                        # Frontend statico (HTML / CSS / JS)

data/
  commander_tracker.sqlite     # Database SQLite Commander (versionato nel repo)
  draft_tracker.sqlite         # Database SQLite Draft (versionato nel repo)

docs/                          # Output finale pubblicabile (generato dall'export)
  data/
    stats.v1.json              # Commander
    draft.v1.json              # Draft
    stats.v1.schema.json

scripts/
  publish.sh                   # Export + commit/push automatico (lato admin)
```

> Nota: la cartella `docs/` può non essere presente appena cloni il repo: viene **generata** da `backend/export_stats.py`.

---

## Database SQLite (tracking & backup)

I database sono:

```text
data/commander_tracker.sqlite  # Commander
data/draft_tracker.sqlite      # Draft
```

È **leggero** e viene **tracciato direttamente nel repository Git** per avere:

- backup automatico
- storico versionato
- possibilità di rollback

### File da ignorare (WAL/SHM)

Nel `.gitignore` **devono** essere ignorati i file temporanei di SQLite:

```gitignore
*.sqlite-wal
*.sqlite-shm
```

Questi file non vanno mai versionati.

### Rollback del database

Ripristino di una versione specifica del DB (consigliato):

```bash
git log --oneline -- data/commander_tracker.sqlite
git log --oneline -- data/draft_tracker.sqlite

git checkout <COMMIT_SHA> -- data/commander_tracker.sqlite
git checkout <COMMIT_SHA> -- data/draft_tracker.sqlite

git commit -m "Rollback DB to <COMMIT_SHA>"
git push
```

Rollback temporaneo (senza commit, solo per test):

```bash
git checkout <COMMIT_SHA> -- data/commander_tracker.sqlite
git checkout <COMMIT_SHA> -- data/draft_tracker.sqlite
# test / export / verifiche
git restore data/commander_tracker.sqlite
git restore data/draft_tracker.sqlite
```

---

## Flusso dati end-to-end

1. **Admin tool** inserisce / modifica partite nel DB SQLite
2. **Exporter**:
   - legge il DB Commander
   - legge il DB Draft
   - calcola aggregazioni e metriche
   - genera JSON deterministico
   - copia il sito statico in `docs/`
3. Il **frontend statico** carica:
   - `docs/data/stats.v1.json` (Commander)
   - `docs/data/draft.v1.json` (Draft)
   e renderizza filtri/grafici
4. **GitHub Pages** pubblica `docs/` (se configurato nel repo)

---

## Admin tool (UI locale)

Documentazione completa: `backend/admin_stdlib.md`.

### Avvio (locale)

Dalla root del repo:

```bash
export COMMANDER_DB=./data/commander_tracker.sqlite
python3 backend/admin_stdlib.py
```

Di default ascolta su `127.0.0.1:8000`.

### Accesso remoto via SSH tunnel (es. da telefono)

```bash
ssh -L 8080:127.0.0.1:8000 user@SERVER
```

Poi apri:

```text
http://127.0.0.1:8080/admin/games
```

---

## Admin Draft (CLI)

Il dominio Draft ha un layer admin/operativo separato (no UI web pubblica):

- funzioni riutilizzabili in `backend/admin_draft_stdlib.py`
- comandi CLI in `backend/draft_stats/`.

Per vedere i comandi disponibili:

```bash
python -m backend.draft_stats --help
```

---

## Generare / aggiornare il sito (manuale)

Dalla root del progetto:

```bash
python backend/export_stats.py --db data/commander_tracker.sqlite --draft-db data/draft_tracker.sqlite --docs docs
```

Cosa fa:

- rigenera completamente `docs/`
- scrive/aggiorna:
  - `docs/data/stats.v1.json` (Commander, deterministico a DB invariato)
  - `docs/data/draft.v1.json` (Draft, deterministico a DB invariato)
  - `docs/data/stats.v1.schema.json`

### Test del sito in locale

Dopo aver generato `docs/`:

```bash
python3 -m http.server -d docs 8081
```

Poi apri:

```text
http://127.0.0.1:8081
```

---

## Pubblicazione/backup automatica lato admin (`scripts/publish.sh`)

Lo script `scripts/publish.sh` serve per il **workflow operativo lato admin**:

- (opzionale) fa checkpoint del WAL per rendere il DB consistente
- esegue l’export delle statistiche in `docs/`
- fa stage **solo** di:
  - `docs/data/**` (per triggerare GitHub Pages)
  - `data/commander_tracker.sqlite` (backup versionato del DB Commander)
  - `data/draft_tracker.sqlite` (backup versionato del DB Draft)
- crea commit e fa push **solo se ci sono cambiamenti**

### Prerequisiti

1. Repo clonato sulla macchina “admin”
2. Virtualenv creato (per avere `python` “stabile” nello script)

Esempio:

```bash
python3 -m venv .venv
. .venv/bin/activate
# se hai dipendenze extra (qui in genere non servono), installale
```

> L’export usa `backend/commander_stats` (solo stdlib + codice repo). L’admin tool usa solo stdlib.

### Uso

Da root del repo (o da qualsiasi path, se imposti `REPO_DIR`):

```bash
bash scripts/publish.sh "aggiunte partite del 2026-02-03"
```

Se non passi un messaggio:

```bash
bash scripts/publish.sh
# commit message di default: "update data"
```

### Variabili d’ambiente supportate

Lo script usa queste variabili (tutte opzionali):

- `REPO_DIR` (default: `~/Projects/commander-tracker`)
- `DB_PATH` (default: `$REPO_DIR/data/commander_tracker.sqlite`, Commander)
- `DRAFT_DB_PATH` (se supportata dallo script; default atteso: `$REPO_DIR/data/draft_tracker.sqlite`, Draft)
- `DOCS_DIR` (default: `$REPO_DIR/docs`)
- `VENV_DIR` (default: `$REPO_DIR/.venv`)

Esempio (utile se il repo non è nella path di default):

```bash
export REPO_DIR="$HOME/commander-tracker"
export VENV_DIR="$REPO_DIR/.venv"
bash "$REPO_DIR/scripts/publish.sh" "sync"
```

### Workflow operativo consigliato (admin)

1. Avvia l’admin tool e inserisci/modifica partite
2. Chiudi (o lascia aperto) l’admin tool
3. Esegui:

```bash
bash scripts/publish.sh "update partite"
```

Risultato:

- il DB viene versionato (backup)
- le statistiche vengono rigenerate
- se `docs/data/**` cambia, GitHub Pages (se configurato) si aggiorna automaticamente

---
### Background su server Ubuntu (systemd)

1. Creare /etc/systemd/system/commander-admin.service
```bash
[Unit]
Description=Commander Tracker Admin (local only)
After=network.target

[Service]
Type=simple
WorkingDirectory=/path/al/repo
Environment=COMMANDER_DB=/path/al/repo/data/commander_tracker.sqlite
ExecStart=/path/al/venv/bin/uvicorn backend.admin_app.app:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
```
2. Poi
```bash
sudo systemctl daemon-reload #  Ricaricare i file di servizio (da eseguire sempre dopo aver modificato: /etc/systemd/system/commander-admin.service)
sudo systemctl enable --now commander-admin #  Fa partire automaticamente l’admin backend ad ogni boot
```
A questo punto il backend admin gira come servizio systemd con nome: commander-admin
3. Utils
```bash
sudo systemctl status commander-admin #  Stato del servizio
sudo systemctl restart commander-admin #  Riavvio del servizio
sudo systemctl stop commander-admin #  Arresto del servizio
sudo systemctl start commander-admin #  Avvio del servizio
sudo systemctl disable commander-admin #  Disabilitazione all’avvio automatico
sudo journalctl -u commander-admin #  Log completi del servizio
sudo journalctl -u commander-admin -f #  Log in tempo reale
sudo systemctl is-active commander-admin #  Verifica rapida se è attivo
sudo systemctl is-enabled commander-admin #  Verifica se è abilitato al boot
```
---

## Note su GitHub Pages (se presente nel repo)

Molte installazioni configurano Pages per deployare **solo quando cambia `docs/**`** (es. via GitHub Actions con `paths: docs/**`).  
Questo evita deploy inutili quando cambi solo backend o admin tool.

Se Pages sembra “bloccato”:

- controlla tab **Actions → Deploy Pages**
- assicurati che il commit contenga cambiamenti in `docs/` (tipicamente `docs/data/**`)
