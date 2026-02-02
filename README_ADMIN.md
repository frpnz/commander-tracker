# Commander Tracker
## Admin Tool – Guida Rapida (Stampabile)

---

## Scopo
Strumento **admin locale** per gestire partite ed entries del Commander Tracker.

- gira **solo in locale**
- **non è esposto pubblicamente**
- accesso remoto **solo via SSH tunnel**

---

## Requisiti
- Ubuntu (o Linux equivalente)
- Python 3 (standard library)
- Database SQLite esistente:
  - `data/commander_tracker.sqlite`

---

## Avvio manuale

Dalla root del repository:

```bash
export COMMANDER_DB=./data/commander_tracker.sqlite
python3 backend/admin_stdlib.py
```

Server attivo su:
```
127.0.0.1:8000
```

---

## Accesso remoto (PC o telefono)

Apri tunnel SSH:

```bash
ssh -L 8080:127.0.0.1:8000 user@SERVER
```

Apri il browser su:

```
http://127.0.0.1:8080/admin/games
```

---

## Avvio automatico (systemd)

File:
```
/etc/systemd/system/commander-admin.service
```

```ini
[Unit]
Description=Commander Tracker Admin
After=network.target

[Service]
Type=simple
WorkingDirectory=/path/al/repo
Environment=COMMANDER_DB=/path/al/repo/data/commander_tracker.sqlite
ExecStart=/usr/bin/python3 /path/al/repo/backend/admin_stdlib.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Comandi:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now commander-admin
sudo systemctl status commander-admin
```

---

## Funzionalità

### Partite
- Creazione partita (data/ora automatiche)
- Modifica winner e note
- Eliminazione partita

### Entries
- Aggiunta entry (player, commander, bracket)
- Modifica entry
- Eliminazione entry

### Tool Bracket
- Modifica massiva del campo `bracket`
- Filtro opzionale per player

---

## UX / Mobile
- Layout verticale
- Bottoni grandi
- Tabelle scrollabili
- Menu a tendina assistiti (datalist)
- Inserimento manuale sempre consentito

---

## Sicurezza
- Bind solo su `127.0.0.1`
- Nessuna API pubblica
- Accesso solo via SSH tunnel
- Nessuna dipendenza esterna

---

## Note
- Nessuna modifica allo schema DB
- Tool pensato solo per uso admin
- Funzionalità utente (import JSON) rimandate
