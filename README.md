# Commander Tracker (FastAPI)

App web per registrare partite multiplayer (stile Commander/EDH) e ottenere statistiche su **player**, **commander** e (opzionalmente) **bracket di potenza**.

**Stack**
- Backend: FastAPI
- UI: Jinja2 (server-side rendering)
- DB: SQLite tramite SQLModel
- Export: Playwright (render HTML → PDF)

---

## 1) Concetti e dati

### Game
Una partita (pod) con:
- **winner_player**: nome del player vincitore (stringa che deve combaciare con `GameEntry.player` per attribuire correttamente la win)
- metadati (id, timestamp, ecc. a seconda del modello)

### GameEntry
Una riga per ogni partecipante in una partita:
- **player**: nome player
- **commander**: nome commander/mazzo
- **bracket**: livello di potenza (intero) o `n/a`/None

### Pod size
Numero di partecipanti in una partita. Usato per segmentare alcune statistiche (es. WR per pod size).

---

## 2) Pagine principali

### `/`
Home / elenco partite + azioni principali.

### `/add_game`, `/edit_game`
Creazione/modifica partite e relative entries.

### `/dashboard`
Dashboard “classica” (non bracket-aware): trend e classifiche per player/commander.

### `/dashboard_mini`
Dashboard compatta.

### `/dashboard_mini_bracket`
Dashboard compatta **bracket-aware**:
- penalizza le win ottenute con bracket sopra la media del pod
- **premia** le win ottenute con bracket sotto la media del pod
- parametro **alpha** configurabile da interfaccia

### `/player_dashboard` e `/player_dashboard_bracket`
Dashboard per singolo player (versione standard e bracket-aware).

### `/stats`
Pagina “tabellare” di statistiche:
- tabelle per player e per player+commander
- distribuzioni bracket (entries e winner)
- winrate per bracket
- elenco **triplette univoche** `Commander – Player – Bracket`
- tabella **triplette** `Player – Commander – Bracket` con WR, Weighted WR e BPI

---

## 3) Export PDF

Sono disponibili export PDF (Playwright) per alcune dashboard. L’export:
- usa formato **A4 landscape**
- include background (`print_background=True`)
- **mantiene i query params** della pagina (filtri, top N, alpha, ecc.)

Endpoint rilevanti (a seconda della build):
- `/dashboard_mini.pdf`
- `/dashboard_mini_bracket.pdf`

---

## 4) Bracket weighting (penalità + premio)

### Definizioni
Per ogni partita con bracket compilati (ignorando `n/a`) si calcola:

- **B_avg**: bracket medio del pod
- **B_w**: bracket del winner
- **ΔB = B_w − B_avg**

Interpretazione:
- **ΔB > 0**: il winner ha bracket *più alto* della media del pod (win “facilitata”)
- **ΔB < 0**: il winner ha bracket *più basso* della media del pod (win “più difficile”)

### Peso della win
Usiamo un parametro **alpha (α)** che controlla quanto “aggressiva” è la correzione.

Peso applicato alle **sole vittorie**:

- se **ΔB > 0** (winner sopra pod):  
  **w = 1 / (1 + α · ΔB)**  → penalizza

- se **ΔB = 0**:  
  **w = 1** → neutro

- se **ΔB < 0** (winner sotto pod):  
  **w = 1 + α · (−ΔB)** → premia

Note:
- α ≥ 0 (valori negativi vengono trattati come 0)
- se ΔB non è calcolabile (bracket mancanti): la win è trattata come **neutra** (w = 1)

### Perché serve un denominatore pesato
Se introduci un premio (w > 1), un “winrate pesato” calcolato come `weighted_wins / games` potrebbe superare il 100%.

Per mantenere il risultato sempre in **[0, 100]**, le metriche **Weighted WR** usano un **denominatore win-pesato**:

- ogni partecipazione parte con `weighted_games += 1`
- se vinci con peso `w`, allora:
  - `weighted_wins += w`
  - `weighted_games += (w − 1)`  
  (quindi quella partita “pesa” w sia al numeratore che al denominatore)

---

## 5) Parametro `alpha` (α)

### Dove si imposta
Nella dashboard bracket-aware (es. `/dashboard_mini_bracket`) è presente un input UI per **alpha**.

### Range e comportamento
- **α = 0** → disabilita la correzione (tutte le win hanno w = 1)
- α più grande → premio/penalità più forti

Suggerimento pratico:
- 0.2–0.8: correzione “leggera”
- 1.0–2.0: correzione “decisa” (attenzione alle classifiche con pochi campioni)

---

## 6) BPI (Bracket Pressure Index)

Il **BPI** è la media di ΔB sulle vittorie:

- BPI ≈ 0 → il player/commander vince in linea col meta del pod
- BPI > 0 → tende a vincere con bracket sopra la media (pressione “verso l’alto”)
- BPI < 0 → tende a vincere con bracket sotto la media (vittorie “in salita”)

Il BPI viene mostrato solo se ci sono almeno **2 vittorie** con ΔB calcolabile (copertura minima).

---

## 7) Note importanti (data hygiene)

- L’attribuzione delle vittorie dipende da una match esatta tra:
  - `Game.winner_player`
  - `GameEntry.player`
- Bracket mancanti (`n/a`) riducono la copertura delle metriche basate su ΔB.
- Con campioni piccoli, qualsiasi indice (WR, Weighted WR, BPI) può essere instabile: usare `min_games`/filtri quando disponibili.

---

