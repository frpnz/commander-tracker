# README – Advanced Overview

Questo documento fornisce una descrizione **approfondita** dell’applicazione di tracking e analytics per partite di Commander e Draft (Magic), includendo architettura, flussi dati e funzionalità dettagliate.  
È pensato come complemento al README principale.

---

## Panoramica generale

L’applicazione è composta da tre parti principali:

1. **Database SQLite** separati per la persistenza dei dati (Commander + Draft)  
2. **Backend Python** per amministrazione locale e generazione statistiche  
3. **Frontend statico HTML/JS** per la visualizzazione (hosting statico, es. GitHub Pages)

Il flusso tipico è:

> Inserimento / modifica partite → DB SQLite → export JSON → sito statico con statistiche

---

## Struttura del progetto

```
.
├── data/
│   ├── commander_tracker.sqlite
│   └── draft_tracker.sqlite
├── backend/
│   ├── commander_stats/
│   │   ├── cli.py
│   │   ├── compute.py
│   │   ├── site.py
│   │   └── admin_stdlib.py
│   ├── draft_stats/
│   │   ├── cli.py
│   │   ├── compute.py
│   │   └── db.py
│   ├── admin_draft_stdlib.py
│   └── export_stats.py
├── frontend/
│   └── site/
│       ├── index.html
│       ├── archive.html
│       ├── stats.html
│       ├── meta-profile.html
│       ├── metrics.html
│       └── assets/
└── docs/
    └── (output generato)
```

---

## Database

### Tabelle

#### `game`
| Campo | Tipo | Descrizione |
|------|------|-------------|
| id | INTEGER (PK) | ID partita |
| played_at | TEXT | Data/ora |
| notes | TEXT | Note libere |
| winner_player | TEXT | Nome player vincitore |

#### `gameentry`
| Campo | Tipo | Descrizione |
|------|------|-------------|
| id | INTEGER (PK) | ID entry |
| game_id | INTEGER (FK) | Riferimento a `game` |
| player | TEXT | Nome player |
| commander | TEXT | Commander usato |
| bracket | INTEGER | Bracket/meta-level |

Ogni partita ha **N entries**, una per giocatore.

---

## Backend – Funzionalità

### 1. Admin UI locale (stdlib only)

Modulo: `admin_stdlib.py`

Server HTTP minimale (solo standard library) pensato per:
- utilizzo locale
- accesso via SSH tunnel se necessario
- **nessuna esposizione pubblica**

#### Funzioni disponibili
- CRUD completo partite
- CRUD entries (player / commander / bracket)
- Import massivo partite
- Gestione e correzione bracket
- Rinomina commander per player (migrazione dati)
- API JSON di supporto per suggerimenti bracket

Endpoint principali:
```
GET  /admin/games
GET  /admin/games/<id>
POST /admin/games/create
POST /admin/games/<id>/update
POST /admin/games/<id>/delete
POST /admin/games/<id>/entries/add
POST /admin/entries/<id>/update
POST /admin/entries/<id>/delete
GET  /admin/brackets
POST /admin/brackets/apply
POST /admin/brackets/rename_commander
GET  /admin/api/bracket_suggestions
```

### 1.b Admin Draft (stdlib + CLI)

Oltre all’admin UI Commander, esiste un layer admin separato per il dominio Draft:

- `backend/admin_draft_stdlib.py` (funzioni riutilizzabili)
- `backend/draft_stats/cli.py` (entrypoint CLI)

Esempio:

```bash
python -m backend.draft_stats --help
```


---

### 2. Generazione statistiche

Modulo: `compute.py`

Responsabilità:
- lettura DB
- normalizzazione dati
- aggregazioni
- calcolo metriche avanzate
- output JSON deterministico

#### Output
- `stats.v1.json` (Commander)
- `draft.v1.json` (Draft)
- `stats.v1.schema.json`

---

### 3. Export sito statico

Modulo: `cli.py` + `site.py`

Funzioni:
- copia del frontend statico
- generazione cartella `docs/`
- inserimento dati JSON
- pronto per GitHub Pages o hosting statico

Comando completo (Commander + Draft):

```bash
python backend/export_stats.py --db data/commander_tracker.sqlite --draft-db data/draft_tracker.sqlite --docs docs
```


---

## Statistiche calcolate

### Base
- Numero totale partite
- Numero entries
- Lista player
- Lista commander
- Lista bracket

### Winrate
- Per player
- Per (player, commander, bracket)

### Storico partite
- Elenco completo e denormalizzato
- Include entries, vincitore e note
- Usato dal frontend per archivio e “ultime partite”

---

## Meta Profile (metriche avanzate)

Metriche progettate per analisi “meta” del tavolo.

### MDI (Matchup Difficulty Index)
- Differenza tra:
  - bracket del player
  - media bracket degli altri giocatori al tavolo

Asse X del grafico.

### Expected Win Rate
- Calcolato con softmax sui bracket del tavolo

### OEWR
- Over Expected Win Rate
- Differenza tra win reale e win atteso

### OEWR_Z
- Normalizzazione tipo z-score
- Asse Y del grafico

Sono applicate soglie minime (es. numero minimo partite) per stabilità statistica.

---

## Frontend – Funzionalità

### Pagine
- Home
- Archivio
- Stats
- Meta Profile
- Metrics (documentazione interpretativa)

### Archivio
- Filtri combinabili:
  - player
  - commander
  - bracket
- Tabella risultati
- Sezione “ultime N partite”

### Grafici (Chart.js)
- Winrate per player (bar)
- Winrate vs numero partite (bubble)
- Meta Profile (scatter + vettori)

---

## Filosofia del progetto

- **DB semplice e portabile**
- **Backend solo per build-time**
- **Nessun backend in produzione**
- **Hosting statico**
- **JSON versionato come API pubblica**
- **Riproducibilità dei risultati**

---

## Estensioni possibili

- Nuove metriche in `compute.py`
- Filtri avanzati lato frontend
- Esportazione CSV
- Supporto a formati torneo diversi
- Autenticazione admin (se necessario)

---

Fine documento.
