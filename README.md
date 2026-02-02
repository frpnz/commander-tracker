# Commander Tracker

Questo repository contiene **Commander Tracker**, un progetto che:

* traccia partite di Commander (Magic: The Gathering) in un **database SQLite**
* genera **statistiche deterministiche** (win rate, metriche, filtri)
* pubblica un **sito statico su GitHub Pages**
* include un **tool admin locale** per inserire e gestire le partite

Questo README è il **documento unico di riferimento** per sviluppo, deploy, dati e amministrazione.

---

## Struttura del progetto

```
backend/                     # Logica Python (export stats + admin)
  export_stats.py            # Generazione sito statico
  commander_stats/           # Moduli di calcolo
  admin_stdlib.py            # Tool admin locale
  stats.v1.schema.json       # JSON Schema (contratto dati)

frontend/
  site/                      # Frontend statico (HTML / CSS / JS)

data/
  commander_tracker.sqlite   # Database SQLite (VERSIONATO nel repo)

docs/                        # Output finale pubblicato su GitHub Pages

.github/workflows/
  pages.yml                  # Workflow GitHub Actions per Pages
```

---

## Database SQLite (tracking & backup)

Il database:

```
data/commander_tracker.sqlite
```

è **leggero** e viene **tracciato direttamente nel repository Git**.
Questo fornisce:

* backup automatico
* storico versionato
* possibilità di rollback

### File da ignorare

Nel `.gitignore` **devono** essere ignorati i file temporanei di SQLite:

```gitignore
*.sqlite-wal
*.sqlite-shm
```

Questi file non vanno mai versionati.

### Rollback del database

Essendo il DB versionato, è possibile ripristinare una versione precedente usando Git.

**Ripristino di una versione specifica del DB (consigliato):**

```bash
git log --oneline -- data/commander_tracker.sqlite
git checkout <COMMIT_SHA> -- data/commander_tracker.sqlite
git commit -m "Rollback DB to <COMMIT_SHA>"
git push
```

Questo ripristina **solo il DB**, senza toccare il resto del repository.

**Rollback temporaneo (senza commit, solo per test):**

```bash
git checkout <COMMIT_SHA> -- data/commander_tracker.sqlite
# test / export / verifiche
git restore data/commander_tracker.sqlite
```

--- Rollback del database

Essendo il DB versionato, è possibile ripristinare una versione precedente usando Git.

**Ripristino di una versione specifica del DB (consigliato):**

```bash
git log --oneline -- data/commander_tracker.sqlite
git checkout <COMMIT_SHA> -- data/commander_tracker.sqlite
git commit -m "Rollback DB to <COMMIT_SHA>"
git push
```

Questo ripristina **solo il DB**, senza toccare il resto del repository.

**Rollback temporaneo (senza commit, solo per test):

## Flusso dati end-to-end

1. **Admin tool** inserisce / modifica partite nel DB SQLite
2. Lo script Python di export:

   * legge il DB
   * calcola aggregazioni e metriche
   * genera JSON deterministico
3. Il frontend statico carica il JSON e renderizza grafici e filtri
4. GitHub Pages pubblica il contenuto di `docs/`

---

## Statistiche generate

Le statistiche includono:

* win rate (vittorie / partite)
* filtri per:

  * player
  * commander
  * bracket
* metriche aggregate

Il file principale generato è:

```
docs/data/stats.v1.json
```

che rispetta lo schema:

```
backend/stats.v1.schema.json
```

L’export è **deterministico**: a DB invariato, l’output non cambia (niente commit rumorosi).

---

## GitHub Pages (configurazione attuale)

### Metodo usato

* **Source:** GitHub Actions
* **Cartella pubblicata:** `docs/`
* **Workflow:** `.github/workflows/pages.yml`

Non viene usato il deploy automatico da branch (`Deploy from a branch`).

---

## Trigger del deploy

Il workflow Pages è configurato per deployare **solo quando cambia `docs/**`**:

```yaml
on:
  push:
    branches: ["main"]
    paths:
      - "docs/**"
  workflow_dispatch:
```

### Effetti pratici

| Cambiamento     | Commit | Deploy Pages |
| --------------- | ------ | ------------ |
| Solo DB         | ✅      | ❌            |
| Backend / admin | ✅      | ❌            |
| docs/data       | ✅      | ✅            |
| DB + docs       | ✅      | ✅            |

---

## Concurrency (anti-code GitHub Actions)

Nel workflow Pages:

```yaml
concurrency:
  group: pages-${{ github.ref }}
  cancel-in-progress: true
```

Questo garantisce che:

* se fai più push ravvicinati
* i deploy precedenti vengono cancellati
* resta **solo l’ultimo deploy valido**

Risolve problemi di:

* runner queued
* deploy cancellati per priorità

---

## Generare / aggiornare il sito (locale)

Dalla root del progetto:

```bash
python backend/export_stats.py \
  --db data/commander_tracker.sqlite \
  --docs docs
```

Questo comando:

* rigenera completamente `docs/`
* aggiorna JSON + frontend statico

---

## Test del sito in locale

````bash
python -m http.server -d ## Workflow operativo consigliato

1. Avvia il tool admin locale e inserisci/modifica partite
2. Esegui lo script di aggiornamento (wrapper bash, es. `update_stats.sh`), che:
   - stabilizza il DB SQLite
   - esegue l’export delle statistiche
   - aggiorna `docs/data/ Accesso remoto

```bash
ssh -L 8080:127.0.0.1:8000 user@SERVER
````

Browser:

```
http://127.0.0.1:8080/admin/games
```

---

## Workflow operativo consigliato

1. Avvia admin tool
2. Inserisci / modifica partite
3. Lancia lo script di aggiornamento (wrapper bash) che:

   * ions

* [x] Concurrency attiva
* [x] Deploy solo su `docs/**`
* [x] Tool admin solo locale

---

**Nota finale**

Se GitHub Pages sembra bloccato:

* controllare **Actions → Deploy Pages**
* ignorare eventuali vecchie run dinamiche non cancellabili
* se il workflow `Deploy Pages` gira, il sito è sotto controllo
