# Tempio Tracker

Questo progetto genera un **sito statico** (compatibile con **GitHub Pages**) che mostra statistiche di **win rate (vittorie / partite)** a partire da un database SQLite.

Le statistiche sono filtrabili per:
- **Player**
- **Player + Commander**
- **Bracket**

---

## Panoramica

- **Backend (Python)**  
  Estrae i dati da SQLite, calcola le aggregazioni e genera un JSON versionato.
- **Frontend (HTML / CSS / JS)**  
  Carica il JSON e renderizza grafici e filtri lato client.
- **Output finale**  
  Una cartella `docs/` pronta per essere pubblicata come sito statico.

---

## Struttura del progetto

```
backend/                     # Logica di estrazione e aggregazione
  export_stats.py            # Entry point CLI
  commander_stats/           # Moduli Python
  stats.v1.schema.json       # JSON Schema del contratto dati

frontend/
  site/                      # Frontend statico (HTML / CSS / JS)

data/
  commander_tracker.sqlite   # Database SQLite (sorgente dati)

docs/                        # Output generato (GitHub Pages)
```

---

## Flusso end-to-end

1. **SQLite** (`data/commander_tracker.sqlite`) è la sorgente dati.
2. Lo script **Python exporter**:
   - legge il database
   - calcola le aggregazioni (win rate, conteggi, filtri)
3. L’exporter:
   - copia `frontend/site/` dentro `docs/`
   - genera `docs/data/stats.v1.json`
   - copia anche lo schema `stats.v1.schema.json`
4. Il frontend (`docs/stats/index.html`) carica il JSON via `fetch()` e rende:
   - grafici
   - filtri
   - tabelle riepilogative

---

## Requisiti

- **Python 3.10+**
- Nessuna dipendenza esterna (solo standard library)
- (Opzionale) un web server statico per test locale  
  es. `python -m http.server`

---

## Contratto dati (Python → JavaScript)

Il file generato:

```
docs/data/stats.v1.json
```

segue lo schema:

```
backend/stats.v1.schema.json
```
## Generare (o rigenerare) il sito

Dalla root del progetto:

```bash
python backend/export_stats.py   --db data/commander_tracker.sqlite   --docs docs
```

Questo comando:
- rigenera completamente `docs/`
- aggiorna dati + frontend statico

---

## Test in locale

Avvia un server statico dalla cartella `docs/`:

```bash
python -m http.server -d docs 8000
```

Apri poi:

```
http://localhost:8000/stats/
```

---

## Output finale

Dopo la generazione, `docs/` contiene:

- `docs/data/stats.v1.json`
- `docs/data/stats.v1.schema.json`
- `docs/stats/index.html` + asset statici

La cartella `docs/` può essere pubblicata direttamente su **GitHub Pages**.
