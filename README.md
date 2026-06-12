# Commander Tracker

Commander Tracker e una web app static-first per tracciare partite Commander e tornei Draft di Magic: The Gathering, calcolare statistiche, pubblicare dashboard statiche e gestire i dati tramite strumenti admin locali.

Il progetto usa:

- Python standard library per admin locale, calcolo metriche ed export
- SQLite per la persistenza dati
- frontend statico HTML/CSS/JavaScript
- Chart.js via CDN per i grafici
- output statico in `docs/`, adatto a GitHub Pages o a qualsiasi hosting statico

Non serve un backend pubblico in produzione: il sito legge file JSON generati a partire dai database SQLite.

---

## Indice

1. Struttura del progetto
2. Flusso generale
3. Setup e requisiti
4. Run locale per test
5. Flusso utente
6. Flusso admin Commander
7. Flusso admin Draft
8. Export e pubblicazione statica
9. Funzionalita frontend
10. Funzionalita Commander analytics
11. Funzionalita Draft analytics
12. Database e backup
13. Comandi utili
14. Troubleshooting

---

## 1. Struttura del progetto

```text
backend/
  export_stats.py              # Export completo sito statico: Commander + Draft
  export_draft.py              # Export standalone dati Draft
  admin_stdlib.py              # Admin locale Commander, solo standard library
  admin_draft_stdlib.py        # Admin locale Draft, solo standard library
  stats.v1.schema.json         # Schema JSON dati Commander

  commander_stats/
    cli.py                     # CLI Commander/export sito
    compute.py                 # Calcolo statistiche Commander
    db.py                      # Accesso SQLite Commander
    site.py                    # Copia frontend + scrittura JSON/schema

  draft_stats/
    cli.py                     # CLI export Draft JSON
    compute.py                 # Calcolo statistiche Draft
    db.py                      # Accesso SQLite Draft

data/
  commander_tracker.sqlite     # Database Commander
  draft_tracker.sqlite         # Database Draft

frontend/site/
  index.html                   # Home
  archive/                     # Archivio partite Commander
  stats/                       # Dashboard statistiche Commander
  meta-profile/                # Analisi meta/profile
  bracket-calibration/         # Calibrazione bracket commander
  draft/                       # Dashboard Draft
  new-game/                    # Generatore JSON nuova partita Commander
  metrics/                     # Guida metriche
  assets/                      # JS, CSS, immagini, colori player

docs/                          # Output generato dall'export, pubblicabile
  data/
    stats.v1.json              # Dati Commander esportati
    draft.v1.json              # Dati Draft esportati
    stats.v1.schema.json       # Schema dati Commander
```

Nota: `docs/` puo non esistere dopo clone/unzip. Viene generata con l'export.

---

## 2. Flusso generale

Il flusso dati e questo:

```text
Admin locale / import JSON
        ->
SQLite Commander e/o Draft
        ->
Python export
        ->
docs/data/*.json + frontend statico
        ->
Sito statico consultabile dagli utenti
```

In pratica:

1. L'admin inserisce o importa partite/tornei nei database SQLite.
2. L'admin lancia l'export.
3. L'export rigenera `docs/` con frontend e JSON aggiornati.
4. Gli utenti consultano il sito statico.
5. La pagina `Nuova partita` puo generare un file JSON da inviare/importare nell'admin.

---

## 3. Setup e requisiti

Requisiti minimi:

- Python 3.10+ consigliato
- browser moderno
- nessuna dipendenza Python esterna obbligatoria

Verifica Python:

```bash
python3 --version
```

Da root repo, verifica che i file principali siano presenti:

```bash
ls backend data frontend
ls data/commander_tracker.sqlite data/draft_tracker.sqlite
```

---

## 4. Run locale per test

### 4.1 Generare il sito statico

Da root repo:

```bash
python3 backend/export_stats.py \
  --db data/commander_tracker.sqlite \
  --draft-db data/draft_tracker.sqlite \
  --docs docs
```

Questo comando:

- copia `frontend/site/` dentro `docs/`
- genera `docs/data/stats.v1.json`
- genera `docs/data/draft.v1.json`
- copia `docs/data/stats.v1.schema.json`

### 4.2 Servire il sito in locale

```bash
python3 -m http.server -d docs 8081
```

Apri:

```text
http://127.0.0.1:8081/
```

Pagine utili:

```text
http://127.0.0.1:8081/archive/
http://127.0.0.1:8081/stats/
http://127.0.0.1:8081/meta-profile/
http://127.0.0.1:8081/bracket-calibration/
http://127.0.0.1:8081/draft/
http://127.0.0.1:8081/new-game/
http://127.0.0.1:8081/metrics/
```

### 4.3 Avviare admin Commander locale

```bash
export COMMANDER_DB=./data/commander_tracker.sqlite
export ADMIN_HOST=127.0.0.1
export ADMIN_PORT=8000
python3 backend/admin_stdlib.py
```

Apri:

```text
http://127.0.0.1:8000/admin/games
```

### 4.4 Avviare admin Draft locale

In un altro terminale:

```bash
export DRAFT_DB=./data/draft_tracker.sqlite
export ADMIN_HOST=127.0.0.1
export ADMIN_PORT=8010
python3 backend/admin_draft_stdlib.py
```

Apri:

```text
http://127.0.0.1:8010/draft/tournaments
```

---

## 5. Flusso utente

Il sito pubblico/statico e pensato per consultazione e preparazione dati.

### 5.1 Consultare statistiche

L'utente apre il sito generato in `docs/` e naviga tra:

- Home
- Archivio
- Stats
- Meta Profile
- Calibrazione
- Draft
- Nuova partita
- Guida metriche

Esempio locale:

```text
http://127.0.0.1:8081/stats/
```

### 5.2 Preparare una nuova partita Commander

Pagina:

```text
/new-game/
```

Flusso:

1. L'utente compila data/ora.
2. Aggiunge player, commander e bracket.
3. Seleziona il vincitore, se gia noto.
4. Scarica un file JSON `game_YYYYMMDD_HHMM.json`.
5. Invia il file all'admin o lo importa direttamente se ha accesso all'admin locale.

Il payload generato ha forma simile a:

```json
{
  "version": "game.v1",
  "played_at": "2026-06-12 21:00",
  "winner_player": "Marco",
  "notes": "Partita del venerdi",
  "entries": [
    { "player": "Marco", "commander": "Atraxa", "bracket": 4 },
    { "player": "Luca", "commander": "Muldrotha", "bracket": 3 },
    { "player": "Giulia", "commander": "Yuriko", "bracket": 4 },
    { "player": "Francesco", "commander": "Miirym", "bracket": 4 }
  ]
}
```

### 5.3 Importare il JSON nell'admin Commander

Con admin Commander avviato:

```text
http://127.0.0.1:8000/admin/games/import_json
```

Flusso:

1. Carica uno o piu file `.json`, oppure incolla il JSON.
2. Premi `Importa`.
3. Controlla la partita importata.
4. Rigenera il sito con l'export.

---

## 6. Flusso admin Commander

L'admin Commander e un server locale, non pensato per esposizione pubblica.

### 6.1 Avvio

```bash
export COMMANDER_DB=./data/commander_tracker.sqlite
python3 backend/admin_stdlib.py
```

Host/porta custom:

```bash
COMMANDER_DB=./data/commander_tracker.sqlite ADMIN_HOST=127.0.0.1 ADMIN_PORT=8005 python3 backend/admin_stdlib.py
```

Apri:

```text
http://127.0.0.1:8000/admin/games
```

### 6.2 Funzionalita admin Commander

L'admin consente di:

- vedere l'elenco partite
- aprire il dettaglio di una partita
- creare una nuova partita
- modificare data, note e vincitore
- cancellare una partita
- aggiungere entry giocatore/commander/bracket
- modificare entry esistenti
- cancellare entry
- importare partite da JSON
- duplicare/importare da partite esistenti
- vedere la lista player
- rinominare player
- gestire bracket
- applicare correzioni bracket
- rinominare commander per uno specifico player
- usare suggerimenti bracket basati sui dati esistenti

### 6.3 URL principali Commander

```text
/admin/games
/admin/games/import_json
/admin/players
/admin/brackets
/admin/api/bracket_suggestions
```

Esempi locali:

```text
http://127.0.0.1:8000/admin/games
http://127.0.0.1:8000/admin/games/import_json
http://127.0.0.1:8000/admin/players
http://127.0.0.1:8000/admin/brackets
```

### 6.4 Accesso da telefono via SSH tunnel

Se l'admin gira su un server remoto:

```bash
ssh -L 8080:127.0.0.1:8000 user@SERVER
```

Poi dal dispositivo locale apri:

```text
http://127.0.0.1:8080/admin/games
```

### 6.5 Dopo modifiche admin

Dopo aver inserito o modificato dati:

```bash
python3 backend/export_stats.py \
  --db data/commander_tracker.sqlite \
  --draft-db data/draft_tracker.sqlite \
  --docs docs
```

Poi testa:

```bash
python3 -m http.server -d docs 8081
```

---

## 7. Flusso admin Draft

L'admin Draft usa un database separato:

```text
data/draft_tracker.sqlite
```

### 7.1 Avvio admin Draft

```bash
export DRAFT_DB=./data/draft_tracker.sqlite
python3 backend/admin_draft_stdlib.py
```

Apri:

```text
http://127.0.0.1:8010/draft/tournaments
```

Host/porta custom:

```bash
DRAFT_DB=./data/draft_tracker.sqlite ADMIN_HOST=127.0.0.1 ADMIN_PORT=8015 python3 backend/admin_draft_stdlib.py
```

### 7.2 Funzionalita admin Draft

L'admin Draft consente di:

- vedere l'elenco tornei
- creare un torneo
- modificare torneo, formato, round e note
- sostituire standings
- sostituire playoff
- cancellare tornei
- importare standings testuali
- rinominare player

### 7.3 Import standings Draft

La pagina import accetta standings in stile:

```text
Nome Player  W-L-D  VIA%
```

Esempio:

```text
Marco Rossi  3-0-0  67.89
Giulia       2-1-0  55.50%
Ale          1-2-0  44.12
```

### 7.4 Export solo Draft

Opzione A, tramite wrapper:

```bash
python3 backend/export_draft.py --db data/draft_tracker.sqlite --docs docs
```

Opzione B, tramite modulo:

```bash
python3 -m backend.draft_stats \
  --db data/draft_tracker.sqlite \
  --out docs/data/draft.v1.json
```

In genere, per aggiornare tutto conviene usare l'export completo:

```bash
python3 backend/export_stats.py \
  --db data/commander_tracker.sqlite \
  --draft-db data/draft_tracker.sqlite \
  --docs docs
```

---

## 8. Export e pubblicazione statica

### 8.1 Export completo

```bash
python3 backend/export_stats.py \
  --db data/commander_tracker.sqlite \
  --draft-db data/draft_tracker.sqlite \
  --docs docs
```

### 8.2 Export Commander senza Draft

```bash
python3 backend/export_stats.py \
  --db data/commander_tracker.sqlite \
  --docs docs
```

### 8.3 Specificare una sorgente frontend diversa

```bash
python3 backend/export_stats.py \
  --db data/commander_tracker.sqlite \
  --draft-db data/draft_tracker.sqlite \
  --site frontend/site \
  --docs docs
```

### 8.4 Test post-export

```bash
python3 -m http.server -d docs 8081
```

Apri:

```text
http://127.0.0.1:8081/
```

### 8.5 Pubblicazione GitHub Pages

Il repo e compatibile con un setup GitHub Pages che pubblica la cartella `docs/`.

Flusso manuale tipico:

```bash
git status
python3 backend/export_stats.py --db data/commander_tracker.sqlite --draft-db data/draft_tracker.sqlite --docs docs
git add data/commander_tracker.sqlite data/draft_tracker.sqlite docs
git commit -m "Update tracker data and static export"
git push
```

Se vuoi committare solo i dati generati:

```bash
git add docs/data data/commander_tracker.sqlite data/draft_tracker.sqlite
git commit -m "Update tracker data"
git push
```

---

## 9. Funzionalita frontend

### 9.1 Home

Pagina:

```text
/
```

Mostra landing page, navigazione e accesso alle sezioni principali.

### 9.2 Archivio

Pagina:

```text
/archive/
```

Funzionalita:

- elenco partite Commander
- filtri per player
- filtri per commander
- filtri per bracket
- reset filtri
- ultime partite
- dettaglio entry per partita

### 9.3 Stats

Pagina:

```text
/stats/
```

Schede interne:

- `Overview`
- `Player detail`
- `Commander by Pod`
- `Cumulative trend`

Funzionalita:

- filtro player
- filtro minimo partite
- winrate player
- bubble plot winrate vs volume
- winrate per commander del player selezionato
- analisi commander per pod size
- cumulata wins above expected

### 9.4 Meta Profile

Pagina:

```text
/meta-profile/
```

Serve a leggere il profilo meta di player e commander usando metriche avanzate come MDI, MPI, OEWR e OEWR_Z.

### 9.5 Bracket Calibration

Pagina:

```text
/bracket-calibration/
```

Serve a stimare se un commander sembra performare sopra o sotto il bracket dichiarato.

### 9.6 Draft

Pagina:

```text
/draft/
```

Mostra statistiche aggregate dei tornei Draft.

### 9.7 Nuova partita

Pagina:

```text
/new-game/
```

Genera un file JSON `game.v1` importabile nell'admin Commander.

### 9.8 Guida metriche

Pagina:

```text
/metrics/
```

Documenta come leggere le metriche e le sezioni del sito.

---

## 10. Funzionalita Commander analytics

I dati Commander vengono calcolati a partire da:

```text
game
  id
  played_at
  notes
  winner_player

gameentry
  id
  game_id
  player
  commander
  bracket
```

Ogni partita ha N entry, una per ogni player seduto al tavolo.

### 10.1 Metriche base

- numero partite
- numero entry
- elenco player
- elenco commander
- elenco bracket
- partite per player
- vittorie per player
- winrate per player
- partite per commander
- vittorie per commander
- winrate per player/commander/bracket

### 10.2 Overview Stats

La scheda `Overview` mostra:

- ranking winrate per player
- volume partite
- bubble plot efficacia vs volume

Interpretazione:

- winrate alto con poche partite = segnale rumoroso
- winrate alto con molte partite = segnale piu affidabile
- bubble piu a destra = piu partite

### 10.3 Player detail

La scheda `Player detail` mostra i commander di un player selezionato.

Metriche:

- games
- wins
- raw winrate
- intervallo di confidenza 95% sul winrate

Uso:

1. Seleziona un player.
2. Imposta `Min partite`.
3. Confronta i commander del player.

### 10.4 Commander by Pod

La scheda `Commander by Pod` analizza i commander del player selezionato in funzione del numero di player al tavolo.

Obiettivo: non confrontare in modo ingenuo un winrate ottenuto in pod da 3, 4 o 5 player, perche la probabilita neutra cambia.

Winrate atteso neutro:

```text
3 player -> 1/3 = 33.3%
4 player -> 1/4 = 25.0%
5 player -> 1/5 = 20.0%
```

Metrica principale:

```text
WAE = wins - expected_wins
expected_wins = somma(1 / pod_size) sulle partite considerate
```

Esempio:

```text
Commander X, 4 partite tutte a 4 player
expected_wins = 4 * 0.25 = 1.00
wins = 2
WAE = 2 - 1.00 = +1.00
```

Visualizzazioni:

- matrice commander x pod size
- cella con WAE
- dettaglio wins/games, raw WR ed expected WR
- grafico barre per top commander
- colori barre fissi per pod size, non per player

### 10.5 Cumulative trend

La scheda `Cumulative trend` sostituisce il rolling winrate.

Il rolling classico puo essere rumoroso. La cumulata usa invece la performance progressiva rispetto all'atteso neutro del pod size.

Per ogni partita del player o del commander selezionato:

```text
actual = 1 se vince, altrimenti 0
expected = 1 / pod_size
delta = actual - expected
cumulative_delta += delta
```

Il grafico mostra:

```text
cumulative wins above expected
```

Interpretazione:

- linea sopra 0 = sopra atteso
- linea sotto 0 = sotto atteso
- linea crescente = periodo positivo
- linea decrescente = periodo sotto atteso

La summary card mostra:

- games
- wins
- expected wins
- wins above expected
- raw WR
- expected WR

### 10.6 Meta Profile

Metriche principali:

- `MDI`: Matchup Difficulty Index, differenza tra bracket del player e media bracket degli altri player al tavolo
- `MPI`: intensita media dello scostamento rispetto al tavolo
- `OEWR`: Over Expected Win Rate, differenza tra win reale e win atteso
- `OEWR_Z`: normalizzazione del segnale OEWR

Uso tipico:

- capire chi performa meglio rispetto al tavolo
- individuare player spesso favoriti o sfavoriti
- leggere performance non spiegate solo dal winrate grezzo

### 10.7 Bracket Calibration

La pagina calibrazione aiuta a valutare se un commander sembra dichiarato troppo basso o troppo alto rispetto alla performance osservata.

Metriche principali:

- `CPR-Z`: indicatore normalizzato di performance/calibrazione
- `B_post`: bracket posteriore stimato
- giochi minimi per ridurre rumore statistico

---

## 11. Funzionalita Draft analytics

Il dominio Draft usa:

```text
tournament
  id
  played_at
  name
  format
  rounds
  notes

standing
  tournament_id
  player
  wins
  losses
  draws
  via_pct

playoff_match
  tournament_id
  stage
  player_a
  player_b
  winner
```

Statistiche calcolate:

- numero tornei
- standings per torneo
- wins/losses/draws
- match win percentage
- VIA percentage media
- ranking medio
- miglior ranking
- podi oro/argento/bronzo
- playoff opzionali
- campione playoff, se presente

Pagina frontend:

```text
/draft/
```

Funzionalita:

- filtro torneo
- filtro minimo match
- ranking player Draft
- grafico Match Win %
- dettaglio tornei
- podi
- playoff, se presenti

---

## 12. Database e backup

### 12.1 Database versionabili

I database principali sono:

```text
data/commander_tracker.sqlite
data/draft_tracker.sqlite
```

Sono piccoli e possono essere versionati in Git.

### 12.2 File SQLite da non versionare

Non versionare file temporanei SQLite:

```gitignore
*.sqlite-wal
*.sqlite-shm
```

### 12.3 Backup manuale veloce

```bash
cp data/commander_tracker.sqlite data/commander_tracker.backup.sqlite
cp data/draft_tracker.sqlite data/draft_tracker.backup.sqlite
```

### 12.4 Backup consistente con SQLite

```bash
sqlite3 data/commander_tracker.sqlite ".backup data/commander_tracker.backup.sqlite"
sqlite3 data/draft_tracker.sqlite ".backup data/draft_tracker.backup.sqlite"
```

### 12.5 Rollback da Git

Vedere storico:

```bash
git log --oneline -- data/commander_tracker.sqlite
git log --oneline -- data/draft_tracker.sqlite
```

Ripristinare una versione:

```bash
git checkout COMMIT_SHA -- data/commander_tracker.sqlite
git checkout COMMIT_SHA -- data/draft_tracker.sqlite
```

Committare il rollback:

```bash
git add data/commander_tracker.sqlite data/draft_tracker.sqlite
git commit -m "Rollback tracker database"
git push
```

---

## 13. Comandi utili

### Help exporter completo

```bash
python3 backend/export_stats.py --help
```

### Help modulo Commander

```bash
python3 -m backend.commander_stats --help
```

### Help modulo Draft

```bash
python3 -m backend.draft_stats --help
```

### Export completo

```bash
python3 backend/export_stats.py --db data/commander_tracker.sqlite --draft-db data/draft_tracker.sqlite --docs docs
```

### Export solo Draft

```bash
python3 backend/export_draft.py --db data/draft_tracker.sqlite --docs docs
```

### Server statico locale

```bash
python3 -m http.server -d docs 8081
```

### Admin Commander

```bash
COMMANDER_DB=./data/commander_tracker.sqlite python3 backend/admin_stdlib.py
```

### Admin Draft

```bash
DRAFT_DB=./data/draft_tracker.sqlite python3 backend/admin_draft_stdlib.py
```

### Controllo sintassi Python

```bash
python3 -m py_compile backend/*.py backend/commander_stats/*.py backend/draft_stats/*.py
```

### Ispezione rapida tabelle SQLite

```bash
sqlite3 data/commander_tracker.sqlite ".tables"
sqlite3 data/draft_tracker.sqlite ".tables"
```

### Conteggio partite Commander

```bash
sqlite3 data/commander_tracker.sqlite "select count(*) from game;"
```

### Conteggio tornei Draft

```bash
sqlite3 data/draft_tracker.sqlite "select count(*) from tournament;"
```

---

## 14. Troubleshooting

### Il sito mostra dati vecchi

Rigenera `docs/`:

```bash
python3 backend/export_stats.py --db data/commander_tracker.sqlite --draft-db data/draft_tracker.sqlite --docs docs
```

Poi ricarica il browser senza cache.

### Il sito non carica i JSON

Servi il sito via HTTP, non aprire direttamente `index.html` da file system:

```bash
python3 -m http.server -d docs 8081
```

Poi apri:

```text
http://127.0.0.1:8081/
```

### L'admin non parte per porta occupata

Usa un'altra porta:

```bash
ADMIN_PORT=8005 COMMANDER_DB=./data/commander_tracker.sqlite python3 backend/admin_stdlib.py
```

Oppure per Draft:

```bash
ADMIN_PORT=8015 DRAFT_DB=./data/draft_tracker.sqlite python3 backend/admin_draft_stdlib.py
```

### Import JSON fallisce

Controlla che il payload abbia:

- `version: "game.v1"`
- `played_at` valorizzato
- almeno 2 entries
- player non duplicati nella stessa partita
- `winner_player`, se presente, uguale a uno dei player nelle entries

### Chart.js non carica

Il frontend usa Chart.js da CDN. In locale serve connessione internet per visualizzare i grafici se il browser non ha gia la libreria in cache.

### Admin esposto pubblicamente

Non esporre direttamente `admin_stdlib.py` o `admin_draft_stdlib.py` su internet. Usali in locale o via SSH tunnel.

---

## Workflow operativo consigliato

Dopo una serata Commander:

```bash
COMMANDER_DB=./data/commander_tracker.sqlite python3 backend/admin_stdlib.py
```

1. Apri `/admin/games`.
2. Importa i JSON da `/admin/games/import_json` o crea/modifica manualmente le partite.
3. Ferma o lascia attivo l'admin locale.
4. Rigenera il sito:

```bash
python3 backend/export_stats.py --db data/commander_tracker.sqlite --draft-db data/draft_tracker.sqlite --docs docs
```

5. Testa in locale:

```bash
python3 -m http.server -d docs 8081
```

6. Pubblica o committa:

```bash
git add data/commander_tracker.sqlite data/draft_tracker.sqlite docs
git commit -m "Update Commander tracker"
git push
```
