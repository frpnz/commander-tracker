#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Local-only admin UI (no external dependencies).

This server is meant to be run on the Ubuntu machine hosting the DB.
It binds to 127.0.0.1 by default so it's not exposed publicly.

Access it via SSH tunnel (example from phone/PC):
  ssh -L 8080:127.0.0.1:8000 user@SERVER
  open http://127.0.0.1:8080/admin/games

Environment variables:
  COMMANDER_DB   Path to commander_tracker.sqlite (default: ./data/commander_tracker.sqlite)
  ADMIN_HOST     Bind host (default: 127.0.0.1)
  ADMIN_PORT     Bind port (default: 8000)

DB compatibility:
  Uses existing tables:
    - game(id, played_at, notes, winner_player)
    - gameentry(id, game_id, player, commander, bracket)
"""

from __future__ import annotations

import os
import sqlite3
import html
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer


REPO_DEFAULT_DB = os.path.join(os.path.dirname(__file__), "..", "data", "commander_tracker.sqlite")
DB_PATH = os.environ.get("COMMANDER_DB", os.path.abspath(REPO_DEFAULT_DB))

HOST = os.environ.get("ADMIN_HOST", "127.0.0.1")
PORT = int(os.environ.get("ADMIN_PORT", "8000"))


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def esc(s: str | None) -> str:
    return html.escape(s or "", quote=True)


def select_options(values: list[str], selected: str | None = None) -> str:
    """Render <option> tags for a <select>, marking `selected` when it matches.

    Values are escaped. The returned string does not include a leading empty option.
    """
    sel = (selected or "").strip()
    out: list[str] = []
    for v in values:
        sv = (v or "").strip()
        if not sv:
            continue
        if sv == sel:
            out.append(f'<option value="{esc(sv)}" selected>{esc(sv)}</option>')
        else:
            out.append(f'<option value="{esc(sv)}">{esc(sv)}</option>')
    return "\n".join(out)


def parse_form(body: bytes) -> dict[str, str]:
    data = urllib.parse.parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return {k: (v[0] if v else "") for k, v in data.items()}



def pick_select_or_new(form: dict[str, str], sel_key: str, new_key: str) -> str:
    sel = (form.get(sel_key, "") or "").strip()
    new = (form.get(new_key, "") or "").strip()
    if new:
        return new
    if sel and sel != "__NEW__":
        return sel
    return ""

def iso_to_dtlocal(iso_str: str | None) -> str:
    """Convert DB timestamp to <input type=datetime-local> value."""
    if not iso_str:
        return ""
    s = str(iso_str).strip().replace("T", " ")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        try:
            dt = datetime.fromisoformat(s[:16])
        except Exception:
            return ""
    return dt.strftime("%Y-%m-%dT%H:%M")


def dtlocal_to_iso(dtlocal: str) -> str:
    dt = datetime.fromisoformat(dtlocal)
    return dt.isoformat(sep=" ")


def now_iso() -> str:
    """Return a system timestamp string compatible with existing DB values."""
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{esc(title)}</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 16px; }}
    .nav {{ display:flex; gap:12px; align-items:center; margin-bottom: 14px; flex-wrap:wrap; }}
    .nav a {{ text-decoration:none; padding: 8px 10px; border-radius: 10px; border:1px solid #ddd; color:#111; }}
    .row {{ display:flex; gap:16px; flex-wrap:wrap; }}
    .card {{ border:1px solid #ddd; border-radius:12px; padding:14px; background:#fff; }}
    .muted {{ color:#666; font-size: 0.9rem; }}
    input, select, textarea {{ padding:10px; border-radius:10px; border:1px solid #ccc; width: 100%; box-sizing: border-box; }}
    label {{ display:block; font-size: 0.9rem; margin: 10px 0 6px; color:#333; }}
    button {{ padding:10px 14px; border-radius:10px; border:1px solid #bbb; background:#f6f6f6; cursor:pointer; }}
    button.primary {{ background:#111; color:#fff; border-color:#111; }}
    .table-wrap {{ width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; }}
    table {{ border-collapse: collapse; width: 100%; min-width: 560px; }}
    th, td {{ border-bottom: 1px solid #eee; padding: 10px; text-align:left; vertical-align: top; }}
    details summary {{ cursor:pointer; }}
    code {{ background:#f2f2f2; padding:2px 6px; border-radius:6px; }}

    /* Mobile */
    @media (max-width: 640px) {{
      body {{ margin: 12px; }}
      .row {{ flex-direction: column; gap: 12px; }}
      .card {{ padding: 12px; }}
      button {{ width: 100%; }}
      table {{ min-width: 520px; }}
      th, td {{ padding: 8px; }}
    }}
  </style>
</head>
<body>
  <div class="nav">
    <a href="/admin/games">Partite</a>
    <a href="/admin/brackets">Tool Bracket</a>
    <span class="muted">DB: <code>{esc(DB_PATH)}</code></span>
  </div>
  {body}
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def _send_html(self, html_text: str, status: int = 200) -> None:
        data = html_text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def do_GET(self):
        path, _, qs = self.path.partition("?")
        query = urllib.parse.parse_qs(qs)

        if path in ("/", ""):
            return self._redirect("/admin/games")

        if path == "/admin/games":
            return self._get_games()

        if path.startswith("/admin/games/"):
            parts = path.strip("/").split("/")
            if len(parts) == 3:
                try:
                    game_id = int(parts[2])
                except ValueError:
                    return self._send_html(page("Errore", "<h1>ID non valido</h1>"), 400)
                return self._get_game_detail(game_id)

        if path == "/admin/brackets":
            updated = query.get("updated", [""])[0]
            msg = query.get("msg", [""])[0]
            return self._get_brackets(updated, msg)

        return self._send_html(page("404", "<h1>Not found</h1>"), 404)

    def do_POST(self):
        path = self.path
        length = int(self.headers.get("Content-Length", "0") or "0")
        form = parse_form(self.rfile.read(length))

        if path == "/admin/games/create":
            return self._post_game_create(form)

        if path.startswith("/admin/games/") and path.endswith("/update"):
            parts = path.strip("/").split("/")
            if len(parts) == 4:
                return self._post_game_update(int(parts[2]), form)

        if path.startswith("/admin/games/") and path.endswith("/delete"):
            parts = path.strip("/").split("/")
            if len(parts) == 4:
                return self._post_game_delete(int(parts[2]))

        if path.startswith("/admin/games/") and path.endswith("/entries/add"):
            parts = path.strip("/").split("/")
            if len(parts) == 5:
                return self._post_entry_add(int(parts[2]), form)

        if path.startswith("/admin/entries/") and path.endswith("/update"):
            parts = path.strip("/").split("/")
            if len(parts) == 4:
                return self._post_entry_update(int(parts[2]), form)

        if path.startswith("/admin/entries/") and path.endswith("/delete"):
            parts = path.strip("/").split("/")
            if len(parts) == 4:
                return self._post_entry_delete(int(parts[2]))

        if path == "/admin/brackets/apply":
            return self._post_brackets_apply(form)

        return self._send_html(page("404", "<h1>Not found</h1>"), 404)

    # ---------------------------
    # Pages
    # ---------------------------
    def _get_games(self):
        with db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT g.*,
                       (SELECT COUNT(*) FROM gameentry ge WHERE ge.game_id=g.id) AS entries_count
                FROM game g
                ORDER BY datetime(g.played_at) DESC, g.id DESC
                """
            )
            games = cur.fetchall()

            cur.execute(
                """
                SELECT player, COUNT(*) AS n
                FROM gameentry
                GROUP BY player
                ORDER BY n DESC, player ASC
                LIMIT 100
                """
            )
            players = [r["player"] for r in cur.fetchall()]

        # Valori esistenti dal DB per i menu (mobile-friendly)
        players_list = "\n".join(f'<option value="{esc(p)}"></option>' for p in players)
        players_select = select_options(players)

        rows = []
        for g in games:
            rows.append(
                f"""
                <tr>
                  <td>{g['id']}</td>
                  <td>{esc(str(g['played_at'] or ''))}</td>
                  <td>{esc(str(g['winner_player'] or '—'))}</td>
                  <td>{g['entries_count']}</td>
                  <td><a href="/admin/games/{g['id']}">Apri</a></td>
                </tr>
                """
            )
        table = "\n".join(rows) if rows else "<tr><td colspan=5 class='muted'>Nessuna partita</td></tr>"

        body = f"""
        <h1>Partite</h1>
        <p class="muted">La data/ora della nuova partita viene presa automaticamente dall'orologio di sistema.</p>
        <div class="row">
          <div class="card" style="flex:1; min-width: 320px;">
            <h3>Nuova partita</h3>
            <form method="post" action="/admin/games/create">
              <label>Winner (player)</label>
              <select name="winner_sel">
                <option value="" selected>— nessuno —</option>
                {players_select}
                <option value="__NEW__">+ Nuovo…</option>
              </select>
              <label class="muted">Se “Nuovo…”, scrivi qui:</label>
              <input name="winner_new" placeholder="Winner nuovo (opzionale)">

              <label>Note</label>
              <textarea name="notes" rows="3" placeholder="opzionale"></textarea>

              <div style="margin-top:12px;">
                <button class="primary" type="submit">Crea</button>
              </div>
            </form>
          </div>

          <div class="card" style="flex:2; min-width: 420px;">
            <h3>Elenco</h3>
            <div class="table-wrap">
              <table>
                <thead><tr><th>ID</th><th>Quando</th><th>Winner</th><th>Entries</th><th></th></tr></thead>
                <tbody>{table}</tbody>
              </table>
            </div>
          </div>
        </div>
        """
        return self._send_html(page("Partite", body))

    def _get_game_detail(self, game_id: int):
        with db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM game WHERE id=?", (game_id,))
            game = cur.fetchone()
            if not game:
                return self._send_html(page("404", "<h1>Partita non trovata</h1>"), 404)

            cur.execute("SELECT * FROM gameentry WHERE game_id=? ORDER BY id ASC", (game_id,))
            entries = cur.fetchall()

            cur.execute(
                "SELECT player, COUNT(*) AS n FROM gameentry GROUP BY player ORDER BY n DESC, player ASC LIMIT 200"
            )
            players = [r["player"] for r in cur.fetchall()]

            cur.execute(
                "SELECT commander, COUNT(*) AS n FROM gameentry GROUP BY commander ORDER BY n DESC, commander ASC LIMIT 400"
            )
            commanders = [r["commander"] for r in cur.fetchall()]

            cur.execute(
                "SELECT DISTINCT bracket FROM gameentry WHERE bracket IS NOT NULL ORDER BY bracket ASC LIMIT 200"
            )
            brackets = [str(r["bracket"]) for r in cur.fetchall()]

        players_list = "\n".join(f'<option value="{esc(p)}"></option>' for p in players)
        commanders_list = "\n".join(f'<option value="{esc(c)}"></option>' for c in commanders)
        brackets_list = "\n".join(f'<option value="{esc(b)}"></option>' for b in brackets)

        # <select> options (affidabile su mobile)
        winner_select = select_options(players, (game["winner_player"] or ""))
        players_select = select_options(players)
        commanders_select = select_options(commanders)
        brackets_select = "\n".join(
            f'<option value="{esc(b)}">{esc(b)}</option>' for b in brackets if b.strip()
        )

        entry_rows = []
        for e in entries:
            bracket_val = "" if e["bracket"] is None else str(e["bracket"])
            bracket_show = "—" if e["bracket"] is None else esc(str(e["bracket"]))

            # options per riga (con selezione attuale)
            player_select_row = select_options(players, e["player"])
            commander_select_row = select_options(commanders, e["commander"])
            br_sel = bracket_val
            bracket_select_row = "\n".join(
                f'<option value="{esc(b)}" {"selected" if b == br_sel else ""}>{esc(b)}</option>'
                for b in brackets
                if b.strip()
            )
            bracket_none_selected = "selected" if br_sel == "" else ""

            entry_rows.append(
                f"""
                <tr>
                  <td>{e['id']}</td>
                  <td>{esc(e['player'])}</td>
                  <td>{esc(e['commander'])}</td>
                  <td>{bracket_show}</td>
                  <td>
                    <details>
                      <summary>Modifica</summary>
                      <form method="post" action="/admin/entries/{e['id']}/update" style="margin-top:10px;">
                        <label>Player</label>
                        <select name="player_sel" required>
                          <option value="" disabled>Seleziona…</option>
                          {player_select_row}
                          <option value="__NEW__">+ Nuovo…</option>
                        </select>
                        <label class="muted">Se “Nuovo…”, scrivi qui:</label>
                        <input name="player_new" placeholder="Player nuovo">

                        <label>Commander</label>
                        <select name="commander_sel" required>
                          <option value="" disabled>Seleziona…</option>
                          {commander_select_row}
                          <option value="__NEW__">+ Nuovo…</option>
                        </select>
                        <label class="muted">Se “Nuovo…”, scrivi qui:</label>
                        <input name="commander_new" placeholder="Commander nuovo">

                        <label>Bracket</label>
                        <select name="bracket_sel">
                          <option value="" {bracket_none_selected}>— nessuno —</option>
                          {bracket_select_row}
                          <option value="__NEW__">+ Nuovo…</option>
                        </select>
                        <label class="muted">Se “Nuovo…”, scrivi qui:</label>
                        <input name="bracket_new" value="{esc(bracket_val)}" inputmode="numeric" placeholder="Bracket (int)">

                        <div style="margin-top:10px; display:flex; gap:10px;">
                          <button class="primary" type="submit">Salva</button>
                        </div>
                      </form>

                      <form method="post" action="/admin/entries/{e['id']}/delete" onsubmit="return confirm('Eliminare entry?')">
                        <button type="submit" style="margin-top:8px;">Elimina</button>
                      </form>
                    </details>
                  </td>
                </tr>
                """
            )
        entries_table = "\n".join(entry_rows) if entry_rows else "<tr><td colspan=5 class='muted'>Nessuna entry</td></tr>"

        body = f"""
        <h1>Partita #{game['id']}</h1>
        <div class="row">
          <div class="card" style="flex:1; min-width: 320px;">
            <h3>Modifica partita</h3>
            <form method="post" action="/admin/games/{game_id}/update">
              <label>Data/Ora</label>
              <div class="muted" style="margin-top:4px;">{esc(str(game['played_at'] or ''))}</div>

              <label>Winner (player)</label>
              <select name="winner_sel">
                <option value="" selected>— nessuno —</option>
                {winner_select}
                <option value="__NEW__">+ Nuovo…</option>
              </select>
              <label class="muted">Se “Nuovo…”, scrivi qui:</label>
              <input name="winner_new" placeholder="Winner nuovo (opzionale)" value="">

              <label>Note</label>
              <textarea name="notes" rows="3">{esc(game['notes'] or '')}</textarea>

              <div style="margin-top:12px; display:flex; gap:10px; flex-wrap:wrap;">
                <button class="primary" type="submit">Salva</button>
                <button type="submit" name="set_now" value="1">Imposta a ora</button>
              </div>
            </form>

            <form method="post" action="/admin/games/{game_id}/delete" onsubmit="return confirm('Eliminare partita e entries?')">
              <div style="margin-top:12px;">
                <button type="submit">Elimina</button>
              </div>
            </form>
          </div>

          <div class="card" style="flex:2; min-width: 520px;">
            <h3>Entries</h3>


            <div class="card" style="margin-bottom:14px;">
              <h4>Aggiungi entry</h4>
              <form method="post" action="/admin/games/{game_id}/entries/add">
                <div class="row">
                  <div style="flex:1; min-width:180px;">
                    <label>Player</label>
                    <select name="player_sel" required>
                      <option value="" disabled selected>Seleziona…</option>
                      {players_select}
                      <option value="__NEW__">+ Nuovo…</option>
                    </select>
                    <label class="muted">Se “Nuovo…”, scrivi qui:</label>
                    <input name="player_new" placeholder="Player nuovo">
                  </div>

                  <div style="flex:1; min-width:220px;">
                    <label>Commander</label>
                    <select name="commander_sel" required>
                      <option value="" disabled selected>Seleziona…</option>
                      {commanders_select}
                      <option value="__NEW__">+ Nuovo…</option>
                    </select>
                    <label class="muted">Se “Nuovo…”, scrivi qui:</label>
                    <input name="commander_new" placeholder="Commander nuovo">
                  </div>

                  <div style="width:160px;">
                    <label>Bracket</label>
                    <select name="bracket_sel">
                      <option value="" selected>— nessuno —</option>
                      {brackets_select}
                      <option value="__NEW__">+ Nuovo…</option>
                    </select>
                    <label class="muted">Se “Nuovo…”, scrivi qui:</label>
                    <input name="bracket_new" inputmode="numeric" placeholder="Bracket (int)">
                  </div>
                </div>

                <div style="margin-top:12px;">
                  <button class="primary" type="submit">Aggiungi</button>
                </div>
              </form>
            </div>

            <div class="table-wrap">
            <table>
              <thead><tr><th>ID</th><th>Player</th><th>Commander</th><th>Bracket</th><th>Azioni</th></tr></thead>
              <tbody>{entries_table}</tbody>
            </table>
            </div>
          </div>
        </div>
        """
        return self._send_html(page(f"Partita {game_id}", body))

    def _get_brackets(self, updated: str, msg: str = ""):
        with db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT commander, COUNT(*) AS n FROM gameentry GROUP BY commander ORDER BY n DESC, commander ASC"
            )
            commanders = cur.fetchall()
            cur.execute("SELECT player, COUNT(*) AS n FROM gameentry GROUP BY player ORDER BY n DESC, player ASC")
            players = cur.fetchall()
            cur.execute("SELECT DISTINCT bracket FROM gameentry WHERE bracket IS NOT NULL ORDER BY bracket ASC LIMIT 200")
            brackets = [str(r["bracket"]) for r in cur.fetchall()]

        cmd_opts = "\n".join(
            f'<option value="{esc(r["commander"])}">{esc(r["commander"])} ({r["n"]})</option>'
            for r in commanders
        )
        # player opzionale, sempre a tendina classica
        player_opts = "\n".join(
            f'<option value="{esc(r["player"])}">{esc(r["player"])} ({r["n"]})</option>' for r in players
        )

        brackets_list = "\n".join(f'<option value="{esc(b)}"></option>' for b in brackets)

        info_bits: list[str] = []
        if updated != "":
            info_bits.append(f"<p class='muted'>Aggiornate {esc(updated)} righe.</p>")
        if msg:
            info_bits.append(f"<p class='muted'>{esc(msg)}</p>")
        info = "\n".join(info_bits)

        table_rows = (
            "\n".join(f"<tr><td>{esc(r['commander'])}</td><td>{r['n']}</td></tr>" for r in commanders)
            if commanders
            else "<tr><td colspan=2 class='muted'>Nessun commander</td></tr>"
        )

        body = f"""
        <h1>Tool Bracket</h1>
        <p class="muted">Aggiorna <code>gameentry.bracket</code> per tutte le entries del <b>player associato</b> al commander scelto (opzionale: forza il player). Utile per correggere anche eventuali varianti/typo del nome commander salvate nel DB.</p>
        {info}
        <div class="row">
          <div class="card" style="flex:1; min-width: 360px;">
            <h3>Bulk update</h3>
            <form method="post" action="/admin/brackets/apply" onsubmit="return confirm('Confermi update massivo?')">
              <label>Commander</label>
              <select name="commander" required>{cmd_opts}</select>

              <label>Nuovo bracket (int)</label>
              <input list="brackets" name="new_bracket" required inputmode="numeric" placeholder="seleziona o scrivi...">

              <label>Player (opzionale)</label>
              <select name="player">
                <option value="">— tutti —</option>
                {player_opts}
              </select>

              <div style="margin-top:12px;">
                <button class="primary" type="submit">Applica</button>
              </div>
            </form>
          </div>

          <datalist id="brackets">{brackets_list}</datalist>

          <div class="card" style="flex:2; min-width: 420px;">
            <h3>Commander presenti</h3>
            <div class="table-wrap">
            <table>
              <thead><tr><th>Commander</th><th># entries</th></tr></thead>
              <tbody>{table_rows}</tbody>
            </table>
            </div>
          </div>
        </div>
        """
        return self._send_html(page("Tool Bracket", body))

    # ---------------------------
    # POST handlers
    # ---------------------------
    def _post_game_create(self, form: dict[str, str]):
        notes = form.get("notes", "").strip() or None
        winner = pick_select_or_new(form, "winner_sel", "winner_new") or None

        played_iso = now_iso()

        with db() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO game (played_at, notes, winner_player) VALUES (?, ?, ?)",
                (played_iso, notes, winner),
            )
            game_id = cur.lastrowid
            conn.commit()

        return self._redirect(f"/admin/games/{game_id}")

    def _post_game_update(self, game_id: int, form: dict[str, str]):
        notes = form.get("notes", "").strip() or None
        winner = pick_select_or_new(form, "winner_sel", "winner_new") or None

        set_now = form.get("set_now", "").strip() == "1"

        with db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT played_at FROM game WHERE id=?", (game_id,))
            row = cur.fetchone()
            if not row:
                return self._send_html(page("404", "<h1>Partita non trovata</h1>"), 404)

            played_iso = now_iso() if set_now else str(row["played_at"])
            cur.execute(
                "UPDATE game SET played_at=?, notes=?, winner_player=? WHERE id=?",
                (played_iso, notes, winner, game_id),
            )
            conn.commit()

        return self._redirect(f"/admin/games/{game_id}")

    def _post_game_delete(self, game_id: int):
        with db() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM gameentry WHERE game_id=?", (game_id,))
            cur.execute("DELETE FROM game WHERE id=?", (game_id,))
            conn.commit()
        return self._redirect("/admin/games")

    def _post_entry_add(self, game_id: int, form: dict[str, str]):
        player = pick_select_or_new(form, "player_sel", "player_new")
        commander = pick_select_or_new(form, "commander_sel", "commander_new")
        bracket_s = (form.get("bracket_new", "") or "").strip() if (form.get("bracket_sel", "").strip() == "__NEW__") else (form.get("bracket_sel", "") or "").strip()

        if not player or not commander:
            return self._send_html(page("Errore", "<h1>player e commander sono obbligatori</h1>"), 400)

        bracket = None
        if bracket_s != "":
            try:
                bracket = int(bracket_s)
            except ValueError:
                return self._send_html(page("Errore", "<h1>bracket deve essere un intero</h1>"), 400)

        with db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM game WHERE id=?", (game_id,))
            if not cur.fetchone():
                return self._send_html(page("404", "<h1>Partita non trovata</h1>"), 404)
            cur.execute(
                "INSERT INTO gameentry (game_id, player, commander, bracket) VALUES (?, ?, ?, ?)",
                (game_id, player, commander, bracket),
            )
            conn.commit()

        return self._redirect(f"/admin/games/{game_id}")

    def _post_entry_update(self, entry_id: int, form: dict[str, str]):
        player = pick_select_or_new(form, "player_sel", "player_new")
        commander = pick_select_or_new(form, "commander_sel", "commander_new")
        bracket_s = (form.get("bracket_new", "") or "").strip() if (form.get("bracket_sel", "").strip() == "__NEW__") else (form.get("bracket_sel", "") or "").strip()

        if not player or not commander:
            return self._send_html(page("Errore", "<h1>player e commander sono obbligatori</h1>"), 400)

        bracket = None
        if bracket_s != "":
            try:
                bracket = int(bracket_s)
            except ValueError:
                return self._send_html(page("Errore", "<h1>bracket deve essere un intero</h1>"), 400)

        with db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT game_id FROM gameentry WHERE id=?", (entry_id,))
            row = cur.fetchone()
            if not row:
                return self._send_html(page("404", "<h1>Entry non trovata</h1>"), 404)
            game_id = int(row["game_id"])
            cur.execute(
                "UPDATE gameentry SET player=?, commander=?, bracket=? WHERE id=?",
                (player, commander, bracket, entry_id),
            )
            conn.commit()

        return self._redirect(f"/admin/games/{game_id}")

    def _post_entry_delete(self, entry_id: int):
        with db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT game_id FROM gameentry WHERE id=?", (entry_id,))
            row = cur.fetchone()
            if not row:
                return self._send_html(page("404", "<h1>Entry non trovata</h1>"), 404)
            game_id = int(row["game_id"])
            cur.execute("DELETE FROM gameentry WHERE id=?", (entry_id,))
            conn.commit()

        return self._redirect(f"/admin/games/{game_id}")

    def _post_brackets_apply(self, form: dict[str, str]):
        commander = form.get("commander", "").strip()
        player = form.get("player", "").strip()
        new_bracket_s = form.get("new_bracket", "").strip()

        if not commander:
            return self._send_html(page("Errore", "<h1>Commander obbligatorio</h1>"), 400)

        try:
            new_bracket = int(new_bracket_s)
        except ValueError:
            return self._send_html(page("Errore", "<h1>new_bracket deve essere un intero</h1>"), 400)

        with db() as conn:
            cur = conn.cursor()

            # Commander e player sono legati 1:1 (assunzione del progetto).
            # Per correggere anche varianti/typo del nome commander nel DB,
            # facciamo l'update per PLAYER (non per commander) dopo averlo risolto.

            resolved_player = player
            msg = ""

            if not resolved_player:
                cur.execute(
                    "SELECT DISTINCT player FROM gameentry WHERE commander=?",
                    (commander,),
                )
                players = [str(r["player"]) for r in cur.fetchall() if (r["player"] or "").strip()]
                if not players:
                    changed = 0
                    msg = f"Nessuna entry trovata per commander: {commander}"  # safe: escaped on render
                    conn.commit()
                    return self._redirect(
                        f"/admin/brackets?updated={changed}&msg={urllib.parse.quote(msg)}"
                    )
                if len(players) > 1:
                    changed = 0
                    msg = (
                        f"Ambiguo: il commander '{commander}' risulta associato a più player ({', '.join(players)}). "
                        "Seleziona il player esplicitamente e riprova."
                    )
                    conn.commit()
                    return self._redirect(
                        f"/admin/brackets?updated={changed}&msg={urllib.parse.quote(msg)}"
                    )
                resolved_player = players[0]
                msg = f"Autodetect: '{commander}' → player '{resolved_player}'."

            else:
                # Check di coerenza: la coppia (commander, player) deve esistere almeno una volta.
                cur.execute(
                    "SELECT 1 FROM gameentry WHERE commander=? AND player=? LIMIT 1",
                    (commander, resolved_player),
                )
                if not cur.fetchone():
                    changed = 0
                    msg = (
                        f"Check fallito: nessuna entry trovata con commander '{commander}' e player '{resolved_player}'. "
                        "Nessuna modifica applicata."
                    )
                    conn.commit()
                    return self._redirect(
                        f"/admin/brackets?updated={changed}&msg={urllib.parse.quote(msg)}"
                    )

            cur.execute(
                "UPDATE gameentry SET bracket=? WHERE player=?",
                (new_bracket, resolved_player),
            )
            changed = cur.rowcount
            conn.commit()

        return self._redirect(
            f"/admin/brackets?updated={changed}&msg={urllib.parse.quote(msg)}"
        )


def main() -> None:
    print(f"[admin] DB={DB_PATH}")
    print(f"[admin] http://{HOST}:{PORT} (bind local only)")
    HTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
