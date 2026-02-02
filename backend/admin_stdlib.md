# Admin UI locale (senza dipendenze)

Questa cartella aggiunge un piccolo server HTTP per **inserire/modificare partite** e **correggere il bracket** nel DB esistente, **usando solo la standard library** di Python.

## Requisiti
- Python 3 (nessun `pip install`)

## Avvio (locale sulla macchina Ubuntu)

Da root del repo:

```bash
export COMMANDER_DB=./data/commander_tracker.sqlite
python3 backend/admin_stdlib.py
```

Di default ascolta su `127.0.0.1:8000`.

## Accesso da remoto con SSH tunnel (es. telefono)

```bash
ssh -L 8080:127.0.0.1:8000 user@SERVER
```

Poi apri nel browser:

`http://127.0.0.1:8080/admin/games`

## UI: selezione player/commander già presenti

Nei form vengono usati campi `input` con `datalist`: mostrano un menù a tendina con i valori già presenti nel DB, **ma consentono comunque di digitare e salvare nuovi valori**.

## Compatibilità DB

La UI è compatibile con lo schema esistente:

- `game(id, played_at, notes, winner_player)`
- `gameentry(id, game_id, player, commander, bracket)`

Non vengono aggiunte tabelle o colonne.
