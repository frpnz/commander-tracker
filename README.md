# Commander Tracker

Commander Tracker e un tracker **static-first** per partite Commander e tornei Draft di Magic: The Gathering.
I dati vivono in due database SQLite locali; gli admin servono solo per inserimento e manutenzione. L'export genera `docs/`, un sito statico pubblicabile su GitHub Pages senza backend pubblico.

## Uso rapido

Requisiti: Python 3.10+ e un browser moderno. Non ci sono dipendenze Python esterne obbligatorie.

### 1. Avviare l'admin Commander

Da root del repository:

```bash
export COMMANDER_DB=./data/commander_tracker.sqlite
export ADMIN_HOST=127.0.0.1
export ADMIN_PORT=8000
python3 backend/admin_stdlib.py
```

Apri `http://127.0.0.1:8000/admin/games`.

L'admin Commander permette di:

- creare una partita manualmente;
- duplicare una partita storica come base per una nuova;
- importare uno o piu file JSON generati dalla pagina **Nuova partita**;
- modificare data/ora, note e winner;
- aggiungere, modificare o eliminare entries;
- suggerire automaticamente il bracket gia usato per una coppia player/commander;
- rinominare globalmente un player;
- applicare correzioni massive ai bracket;
- rinominare un commander per uno specifico player.

> L'admin non ha autenticazione ed e progettato per essere **locale-only**. Non esporre `8000` su Internet.

### 2. Avviare l'admin Draft

In un altro terminale:

```bash
export DRAFT_DB=./data/draft_tracker.sqlite
export ADMIN_HOST=127.0.0.1
export ADMIN_PORT=8010
python3 backend/admin_draft_stdlib.py
```

Apri `http://127.0.0.1:8010/draft/tournaments`.

L'admin Draft permette di creare/modificare tornei, importare standings da MTG Companion, inserire playoff opzionali e rinominare player.

### 3. Validare ed esportare il sito

```bash
python3 backend/validate_db.py --db data/commander_tracker.sqlite

python3 backend/export_stats.py \
  --db data/commander_tracker.sqlite \
  --draft-db data/draft_tracker.sqlite \
  --docs docs
```

L'export valida **prima** i dati Commander e tocca `docs/` solo se la validazione e il calcolo terminano correttamente.

Per vedere il sito in locale:

```bash
python3 -m http.server -d docs 8081
```

Apri `http://127.0.0.1:8081/`.

---

## Workflow Commander consigliato

### A. Inserimento dal sito: Nuova partita -> JSON -> admin

La pagina pubblica `/new-game/` serve a preparare la partita senza accesso al database.

1. Apri `/new-game/`.
2. Inserisci almeno due entries con `player`, `commander` e `bracket`.
3. Seleziona il winner quando noto.
4. Scarica il file `game_YYYYMMDD_HHMM.json`.
5. Nell'admin apri `/admin/games/import_json`.
6. Seleziona **uno o piu** file `.json`, oppure incolla il payload.
7. Premi **Importa**.
8. Controlla la partita importata e completa eventuali informazioni mancanti.

Formato atteso:

```json
{
  "version": "game.v1",
  "played_at": "2026-09-26 21:15:00",
  "notes": "",
  "winner_player": "Alice",
  "entries": [
    {"player": "Alice", "commander": "Commander A", "bracket": 4},
    {"player": "Bob", "commander": "Commander B", "bracket": 3}
  ]
}
```

Regole principali dell'import:

- `played_at` deve essere una data/ora ISO valida;
- servono almeno 2 entries;
- player e commander non possono essere vuoti;
- lo stesso player non puo comparire due volte nella stessa partita;
- `bracket` puo essere `null` oppure un intero da 1 a 5;
- `winner_player`, se valorizzato, deve essere uno dei player della partita;
- un import multiplo e **atomico**: se un payload fallisce, non viene inserita nessuna delle partite del batch.

Il JSON puo essere importato con `winner_player: null` quando la partita non e ancora conclusa. Prima dell'export, pero, ogni partita deve avere un winner valido: la validazione blocca la pubblicazione finche non viene impostato.

#### Import JSON diretto da riga di comando

Non serve avviare l'admin HTTP. Da root del repository:

```bash
python3 backend/import_games.py \
  --db data/commander_tracker.sqlite \
  partite.json
```

Puoi passare piu file nello stesso comando; ogni file puo contenere una singola partita oppure un array JSON:

```bash
python3 backend/import_games.py \
  --db data/commander_tracker.sqlite \
  partita_1.json partita_2.json batch.json
```

Tutto il batch viene validato prima dell'inserimento e importato in **un'unica transazione**: se un payload non e valido, non viene inserita nessuna partita. Il comando rifiuta inoltre un path DB inesistente invece di creare accidentalmente un nuovo SQLite vuoto.

### B. Creazione manuale nell'admin

Da `/admin/games` usa **Nuova partita**. L'admin assegna data/ora corrente, crea il game e poi consente di aggiungere le entries. Il winner si seleziona solo dopo aver inserito i player, cosi non puo puntare a un'identita assente dalla partita.

### C. Riutilizzare un tavolo storico

Da `/admin/games`, **Importa da partita storica** duplica entries, winner e note di un game esistente in una nuova partita con data/ora corrente. E utile quando tavolo e commander cambiano poco: dopo la duplicazione apri il dettaglio e correggi cio che serve.

### D. Correggere una partita

Nel dettaglio `/admin/games/<id>` puoi:

- modificare data/ora, note e winner;
- modificare player, commander e bracket delle singole entries;
- aggiungere o eliminare entries;
- eliminare l'intera partita.

Le operazioni che romperebbero le invarianti vengono rifiutate. In particolare, non e consentito creare due entries dello stesso player nella stessa partita o impostare un winner non presente nelle entries.

### E. Manutenzione player e bracket

- `/admin/players`: rinomina globale di un player. L'operazione viene bloccata se fonderebbe due identita gia presenti nella stessa partita.
- `/admin/brackets`: aggiornamento massivo dei bracket per coppia player/commander e rinomina commander per uno specifico player.

Dopo modifiche importanti, esegui sempre validazione, test ed export.

---

## Workflow Draft

### 1. Crea il torneo

Apri `/draft/tournaments` e crea il torneo con data/ora, nome, formato, numero round opzionale e note.

### 2. Importa standings da MTG Companion

Apri `/draft/import`, seleziona il torneo e incolla una riga per player:

```text
Marco Rossi    3-0-0    67.89
Giulia         2-1-0    55.50%
Ale            1-2-0    44.12
```

Sono accettati spazi o tab. L'import richiede:

- record `W-L-D` valido;
- VIA numerica tra 0 e 100;
- un'unica riga per player nel torneo.

Un player duplicato non viene piu ignorato: l'import viene rifiutato, cosi un paste errato resta visibile.

#### Import Draft diretto da riga di comando

Il torneo deve essere gia stato creato nell'admin. Salva gli standings nello stesso formato Companion, per esempio in `standings.txt`, e opzionalmente i playoff in `playoffs.txt`, quindi:

```bash
python3 backend/import_draft.py \
  --db data/draft_tracker.sqlite \
  --tournament-id 10 \
  --standings standings.txt \
  --playoffs playoffs.txt
```

Senza playoff ometti semplicemente `--playoffs`. Il comando verifica che il torneo esista, applica gli stessi parser dell'admin e sostituisce standings e playoff del torneo in **un'unica transazione**. Un input non valido non modifica il torneo.

### 3. Playoff opzionali

Esempi accettati:

```text
SF: Fra > Teo
SF: Giamma vs Lori -> Giamma
F: Fra vs Giamma -> Fra
```

Il winner deve essere uno dei due partecipanti del match. Gli standings e i playoff possono anche essere sostituiti in seguito dalla pagina del torneo.

### 4. Rinomina player

`/draft/players` rinomina un player nel database Draft. La rinomina viene bloccata se produrrebbe due standings dello stesso player nello stesso torneo.

### Ordinamento e podio Draft

Gli standings esportati sono ordinati per:

1. `wins` decrescente;
2. `draws` decrescente;
3. `VIA%` decrescente;
4. nome player per stabilita.

Il `Match Win %` e:

```text
MWP = (wins + 0.5 * draws) / (wins + losses + draws)
```

Se e presente una finale, oro e argento derivano dalla finale; il bronzo e il semifinalista sconfitto meglio piazzato negli standings, oppure il primo player disponibile negli standings. Senza finale, il podio e la top 3 degli standings.

---

## Validazione, test ed export

### Validator Commander

```bash
python3 backend/validate_db.py --db data/commander_tracker.sqlite
```

Blocca, tra le altre cose:

- foreign key non valide;
- game con meno di 2 entries;
- winner mancante o non presente tra le entries;
- player/commander vuoti;
- bracket non interi o fuori 1..5;
- nuovi duplicati dello stesso player nella stessa partita.

Le partite legacy `#45`, `#47`, `#55` sono elencate in `data/validation_exceptions.json`: in modalita normale generano warning. Per trattarle come errori:

```bash
python3 backend/validate_db.py \
  --db data/commander_tracker.sqlite \
  --strict-duplicates
```

### Test automatici

```bash
python3 -m unittest discover -s tests -v
```

La suite copre invarianti admin, validazione payload/DB, import Draft, transazioni atomiche, contratto statistiche, schema ed export deterministico.

### Export completo

```bash
python3 backend/export_stats.py \
  --db data/commander_tracker.sqlite \
  --draft-db data/draft_tracker.sqlite \
  --docs docs
```

Genera:

```text
docs/data/stats.v1.json
docs/data/draft.v1.json
docs/data/stats.v1.schema.json
```

e copia il frontend da `frontend/site/` a `docs/`.

### Export solo Draft

```bash
python3 backend/export_draft.py \
  --db data/draft_tracker.sqlite \
  --docs docs
```

---

## Pubblicazione GitHub Pages

Lo script completo e:

```bash
./scripts/publish.sh "messaggio commit"
```

Lo script ora usa automaticamente come repository la directory che contiene `scripts/`; quindi puo essere eseguito da qualunque working directory. Opzionalmente puoi sovrascrivere `REPO_DIR`, `DB_PATH`, `DRAFT_DB_PATH`, `DOCS_DIR` o `PYTHON_BIN`.

Prima di modificare `docs/`, il publish:

1. forza il checkpoint WAL dei DB;
2. esegue la suite di test;
3. valida il DB Commander;
4. rigenera l'intero sito;
5. aggiunge a Git frontend, docs, eccezioni e DB in-repo;
6. esegue commit e push solo se esistono modifiche staged.

---

## Funzionalita del sito

| Pagina | Funzione |
|---|---|
| `/` | sintesi dataset e navigazione |
| `/archive/` | archivio partite Commander con filtri |
| `/stats/` | statistiche player/commander, pod size, trend e intervalli di confidenza |
| `/meta-profile/` | MDI, MPI e OEWR contestualizzati sui bracket del tavolo |
| `/bracket-calibration/` | confronto bracket assegnato vs bracket inferito dai risultati |
| `/draft/` | tornei, Match Win %, VIA e podi |
| `/new-game/` | creazione del JSON da importare nell'admin Commander |
| `/metrics/` | definizioni e formule delle metriche |

Il frontend e interamente statico e legge i JSON in `docs/data/`.

---

## Metriche Commander: lettura rapida

Le statistiche grezze (`games`, `wins`, `WR`) riflettono direttamente le righe memorizzate. I tre game legacy con identita duplicata restano quindi nell'archivio e nei conteggi grezzi, ma sono esclusi dalle metriche contestuali.

- **WR** = `wins / games`; nei grafici player+commander il 95% CI usa Wilson.
- **WAE** = `wins - somma(1/pod_size)`: normalizza solo per dimensione del pod.
- **MDI** = media di `bracket_player - media(bracket_altri)`; **MPI** = media del valore assoluto dello stesso scostamento.
- **OEWR** usa `p_i = softmax(0.80 * bracket_i)` e il residuo `actual_win_i - p_i`. `oewr_z` standardizza la somma dei residui con `sqrt(somma(p_i*(1-p_i)))`.
- **Bracket calibration** stima un posteriore su `1.00..5.00` a step `0.25`; il JSON espone media (`b_post`), deviazione standard (`b_post_sd`) e MAP (`b_post_map`). La UI mostra il MAP come “B posterior”.

MDI/MPI/OEWR/calibrazione ignorano i game con identita player duplicata. OEWR e calibrazione richiedono inoltre il vettore completo dei bracket. Per formule, criteri di inclusione e interpretazione usa `/metrics/`; per i risultati dell'audit vedi `AUDIT_REPORT.md`.

---

## Dati e struttura essenziale

```text
backend/
  admin_stdlib.py              admin Commander
  admin_draft_stdlib.py        admin Draft
  import_games.py              import Commander JSON da CLI
  import_draft.py              import Draft Companion da CLI
  validate_db.py               validazione Commander
  export_stats.py              export completo
  export_draft.py              export Draft
  commander_stats/             calcolo/validation/export Commander
  draft_stats/                 calcolo/export Draft

data/
  commander_tracker.sqlite
  draft_tracker.sqlite
  validation_exceptions.json
frontend/site/                 sorgente sito statico
docs/                          artifact statico generato
tests/test_hardening.py        regressioni e invarianti
scripts/publish.sh             validazione + export + git push
```

`docs/` e un artifact generato: le modifiche di frontend vanno fatte in `frontend/site/` e poi propagate con l'export.

Il campo `generated_utc` nei JSON e mantenuto per compatibilita ma oggi e un **watermark deterministico dei dati**: corrisponde al `played_at` piu recente del dataset, non all'istante reale in cui e stato eseguito l'export.

---

## Backup e accesso remoto

I due file SQLite in `data/` sono la sorgente dati. Prima di manutenzioni invasive e consigliabile conservarne una copia o usare Git come punto di rollback.

Per usare gli admin su una macchina remota, mantieni il bind su `127.0.0.1` e usa un tunnel SSH, per esempio:

```bash
ssh -L 8080:127.0.0.1:8000 user@SERVER
ssh -L 8081:127.0.0.1:8010 user@SERVER
```

Poi apri rispettivamente `http://127.0.0.1:8080/admin/games` e `http://127.0.0.1:8081/draft/tournaments`.

---

## Troubleshooting essenziale

**Il sito mostra dati vecchi**  
Riesegui l'export e servi/pubblica la nuova `docs/`.

**L'import JSON fallisce**  
Controlla `played_at`, almeno 2 entries, player unici, commander non vuoti, bracket interi 1..5/null e winner presente nelle entries.

**L'export fallisce per winner mancante**  
Apri la partita indicata dal validator e imposta il winner. E possibile importare una partita ancora aperta, ma non pubblicarla come dato completo.

**Il validator segnala duplicati nei game 45/47/55**  
Sono eccezioni legacy note. In modalita normale sono warning; le metriche contestuali li ignorano. Non aggiungere nuovi ID all'elenco delle eccezioni per aggirare errori correnti senza una verifica esplicita.

**Porta admin occupata**  
Scegli un'altra `ADMIN_PORT`.

**Il sito non carica i JSON aprendo direttamente `index.html`**  
Usa un web server locale (`python3 -m http.server -d docs 8081`) invece di `file://`.
