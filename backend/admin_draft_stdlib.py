#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Local-only admin UI for Draft tournaments (no external dependencies).

This is intentionally separate from the Commander DB/admin for safety.

Environment variables:
  DRAFT_DB     Path to draft_tracker.sqlite (default: ./data/draft_tracker.sqlite)
  ADMIN_HOST   Bind host (default: 127.0.0.1)
  ADMIN_PORT   Bind port (default: 8010)

Access via SSH tunnel:
  ssh -L 8081:127.0.0.1:8010 user@SERVER
  open http://127.0.0.1:8081/draft/tournaments

DB schema (created if missing):
  tournament(id, played_at, name, format, rounds, notes)
  standing(id, tournament_id, player, wins, losses, draws, via_pct)
"""

from __future__ import annotations

import html
import json
import os
import re
import sqlite3
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

from draft_stats.db import connect, ensure_schema

REPO_DEFAULT_DB = os.path.join(os.path.dirname(__file__), "..", "data", "draft_tracker.sqlite")
DB_PATH = os.environ.get("DRAFT_DB", os.path.abspath(REPO_DEFAULT_DB))

HOST = os.environ.get("ADMIN_HOST", "127.0.0.1")
PORT = int(os.environ.get("ADMIN_PORT", "8010"))


def db() -> sqlite3.Connection:
    conn = connect(DB_PATH)
    ensure_schema(conn)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def esc(s: str | None) -> str:
    return html.escape(s or "", quote=True)


def parse_form(body: bytes) -> dict[str, str]:
    data = urllib.parse.parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return {k: (v[0] if v else "") for k, v in data.items()}


def parse_form_multi(body: bytes) -> dict[str, list[str]]:
    """Parse application/x-www-form-urlencoded keeping multiple values per key."""
    data = urllib.parse.parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return {k: [str(x) for x in (v or [])] for k, v in data.items()}


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def iso_to_dtlocal(iso_str: str | None) -> str:
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
    return dt.replace(microsecond=0).isoformat(sep=" ")


_RECORD_RE = re.compile(r"^(?P<w>\d+)\s*-\s*(?P<l>\d+)\s*-\s*(?P<d>\d+)$")


def parse_companion_text(text: str) -> list[dict[str, object]]:
    """Parse MTG Companion standings pasted text.

    Expected per line (flexible whitespace/tabs):
      <PLAYER NAME>  <W-L-D>  <VIA%>
    Example:
      Marco Rossi\t3-0-0\t67.89
      Ale 2-1-0 55.5%

    Returns list of dicts: {player, w, l, d, via_pct}
    """
    rows: list[dict[str, object]] = []

    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        # ignore obvious headers
        if line.lower().startswith(("name", "player", "giocatore")):
            continue

        parts = re.split(r"\s+", line)
        if len(parts) < 3:
            raise ValueError(f"Riga non valida (servono almeno 3 campi): {raw!r}")

        via_token = parts[-1].rstrip("%")
        rec_token = parts[-2]
        name_tokens = parts[:-2]

        m = _RECORD_RE.match(rec_token)
        if not m:
            # sometimes record is last and VIA is second last; try swapped
            m2 = _RECORD_RE.match(parts[-1])
            if m2:
                # swapped, expect VIA in parts[-2]
                via_token = parts[-2].rstrip("%")
                rec_token = parts[-1]
                name_tokens = parts[:-2]
                m = m2
            else:
                raise ValueError(f"Record non riconosciuto (usa W-L-D): {raw!r}")

        try:
            via = float(via_token)
        except ValueError:
            raise ValueError(f"VIA% non numerica: {raw!r}")

        player = " ".join(name_tokens).strip()
        if not player:
            raise ValueError(f"Nome player mancante: {raw!r}")

        w = int(m.group("w"))
        l = int(m.group("l"))
        d = int(m.group("d"))

        rows.append({"player": player, "w": w, "l": l, "d": d, "via_pct": via})

    if not rows:
        raise ValueError("Nessuna riga valida trovata.")

    # de-dup by player (keep first)
    seen = set()
    dedup: list[dict[str, object]] = []
    for r in rows:
        k = str(r["player"]).casefold()
        if k in seen:
            continue
        seen.add(k)
        dedup.append(r)

    return dedup


_STAGE_RE = re.compile(r"^(?P<stage>sf|semi|semifinale|semifinal|f|finale|final)\s*[:\-]?\s*(?P<rest>.*)$", re.IGNORECASE)


def _norm_stage(stage: str) -> str:
    s = (stage or "").strip().casefold()
    if s in ("sf", "semi", "semifinale", "semifinal"):
        return "SF"
    if s in ("f", "finale", "final"):
        return "F"
    return stage.strip().upper() or "M"


def parse_playoffs_text(text: str) -> list[dict[str, str]]:
    """Parse optional playoffs lines.

    Accepts 1-3 lines, examples:
      SF: Fra > Teo
      SF Fra vs Teo -> Fra
      Final: Fra def. Giamma
      F: Fra > Giamma

    Returns list of: {stage, player_a, player_b, winner}
    """
    out: list[dict[str, str]] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue

        stage = "M"
        rest = line
        m = _STAGE_RE.match(line)
        if m:
            stage = _norm_stage(m.group("stage"))
            rest = (m.group("rest") or "").strip()

        # Normalize common separators
        rest2 = rest.replace("→", "->").replace("⇒", "->")

        # Pattern 1: "A > B" means A wins.
        if ">" in rest2:
            left, right = rest2.split(">", 1)
            a = left.strip()
            b = right.strip()
            if not a or not b:
                raise ValueError(f"Riga playoff non valida: {raw!r}")
            out.append({"stage": stage, "player_a": a, "player_b": b, "winner": a})
            continue

        # Pattern 2: "A vs B -> A" (winner on the right)
        if "->" in rest2:
            pre, win = rest2.split("->", 1)
            winner = win.strip()
            pre = pre.strip()
            if not winner or not pre:
                raise ValueError(f"Riga playoff non valida: {raw!r}")
            # try split pre by vs / v / -
            pre = re.sub(r"\s+", " ", pre)
            mvs = re.split(r"\s+(?:vs\.?|v\.?|contro)\s+", pre, flags=re.IGNORECASE)
            if len(mvs) == 2:
                a, b = mvs[0].strip(), mvs[1].strip()
            elif "-" in pre:
                a, b = [x.strip() for x in pre.split("-", 1)]
            else:
                raise ValueError(f"Riga playoff non valida (manca 'vs'): {raw!r}")
            if not a or not b:
                raise ValueError(f"Riga playoff non valida: {raw!r}")
            out.append({"stage": stage, "player_a": a, "player_b": b, "winner": winner})
            continue

        # Pattern 3: "A def. B" or "A beat B" means A wins.
        mdef = re.split(r"\s+(?:def\.?|defeats|beat|beats)\s+", rest2, flags=re.IGNORECASE)
        if len(mdef) == 2:
            a, b = mdef[0].strip(), mdef[1].strip()
            if not a or not b:
                raise ValueError(f"Riga playoff non valida: {raw!r}")
            out.append({"stage": stage, "player_a": a, "player_b": b, "winner": a})
            continue

        raise ValueError(
            "Riga playoff non riconosciuta. Esempi: 'SF: Fra > Teo' oppure 'F: Fra vs Giamma -> Fra'."
        )

    return out


def page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang=\"it\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
  <title>{esc(title)}</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 16px; line-height: 1.35; }}
    .nav {{ display:flex; gap:12px; align-items:center; margin-bottom: 14px; flex-wrap:wrap; }}
    .nav a {{ text-decoration:none; padding: 8px 10px; border-radius: 10px; border:1px solid #ddd; color:#111; }}
    .card {{ border:1px solid #ddd; border-radius:12px; padding:14px; background:#fff; max-width: 980px; }}
    .muted {{ color:#666; font-size: 0.9rem; }}
    input, textarea {{ padding:10px; border-radius:10px; border:1px solid #ccc; width: 100%; box-sizing: border-box; font-size: 1rem; }}
    label {{ display:block; font-size: 0.9rem; margin: 10px 0 6px; color:#333; }}
    button {{ padding:8px 12px; border-radius:10px; border:1px solid #bbb; background:#f6f6f6; cursor:pointer; width:auto; font-size: 0.95rem; }}
    button.primary {{ background:#111; color:#fff; border-color:#111; }}
    .flash {{ border:1px solid #cfe3ff; background:#eef6ff; padding:10px 12px; border-radius:12px; margin: 0 0 12px; }}
    .flash.ok {{ border-color:#cfead5; background:#eefaf1; }}
    .flash.err {{ border-color:#ffd2d2; background:#fff0f0; }}
    .btn-row {{ display:flex; gap:10px; flex-wrap:wrap; align-items:center; }}
    .table-wrap {{ width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #eee; padding: 10px; text-align:left; vertical-align: top; }}
    code {{ background:#f2f2f2; padding:2px 6px; border-radius:6px; }}
  </style>
</head>
<body>
{body}
</body>
</html>"""


def nav() -> str:
    return (
        '<div class="nav">'
        '<a href="/draft/tournaments">Draft tornei</a>'
        '<a href="/draft/import">Import Companion</a>'
        '<a href="/draft/players">Player</a>'
        "</div>"
    )


def render_flash(qs: dict[str, str]) -> str:
    msg = (qs.get("msg") or "").strip()
    kind = (qs.get("kind") or "").strip()
    if not msg:
        return ""
    cls = "flash " + ("ok" if kind == "ok" else "err" if kind == "err" else "")
    return f'<div class="{cls}">{esc(msg)}</div>'


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, content_type: str, body: str) -> None:
        b = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _redirect(self, url: str) -> None:
        self.send_response(303)
        self.send_header("Location", url)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}

        if path in ("/", "/draft", "/draft/"):
            return self._redirect("/draft/tournaments")

        if path == "/draft/tournaments":
            return self._get_tournaments(qs)

        if path == "/draft/tournament":
            return self._get_tournament(qs)

        if path == "/draft/import":
            return self._get_import(qs)

        if path == "/draft/players":
            return self._get_players(qs)

        self._send(404, "text/html", page("404", nav() + "<p>Not found.</p>"))

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else b""
        form = parse_form(body)

        if path == "/draft/tournaments/create":
            return self._post_create_tournament(form)

        if path == "/draft/tournament/update":
            return self._post_update_tournament(form)

        if path == "/draft/standing/replace":
            return self._post_replace_standings(form)

        if path == "/draft/playoffs/replace":
            return self._post_replace_playoffs(form)

        if path == "/draft/tournament/delete":
            return self._post_delete_tournament(form)

        if path == "/draft/import":
            return self._post_import(form)

        if path == "/draft/player/rename":
            return self._post_rename_player(form)

        self._send(404, "text/html", page("404", nav() + "<p>Not found.</p>"))

    def _get_players(self, qs: dict[str, str]) -> None:
        with db() as conn:
            players = [
                r["player"]
                for r in conn.execute(
                    """
                    SELECT player FROM (
                      SELECT player AS player FROM standing
                      UNION
                      SELECT player_a AS player FROM playoff_match
                      UNION
                      SELECT player_b AS player FROM playoff_match
                      UNION
                      SELECT winner AS player FROM playoff_match
                    )
                    WHERE player IS NOT NULL AND TRIM(player) <> ''
                    GROUP BY LOWER(player)
                    ORDER BY LOWER(player)
                    """
                ).fetchall()
            ]

        body = nav() + render_flash(qs) + (
            '<div class="card">'
            '<h2 style="margin:0 0 8px">Rinomina player (globale)</h2>'
            '<div class="muted">Aggiorna il nome del player in <code>standing</code> e nei <code>playoff_match</code> (player_a / player_b / winner).</div>'
            '<form method="POST" action="/draft/player/rename" style="margin-top:12px">'
            '<label>Player attuale</label>'
            '<input name="old_player" list="players" placeholder="Seleziona o scrivi..." required />'
            '<datalist id="players">'
            + "".join([f'<option value="{esc(p)}"></option>' for p in players])
            + '</datalist>'
            '<label>Nuovo nome</label>'
            '<input name="new_player" placeholder="Nuovo nome player" required />'
            '<div class="btn-row" style="margin-top:12px">'
            '<button class="primary" type="submit" onclick="return confirm(\'Applicare la rinomina su tutto il DB draft?\')">Rinomina</button>'
            '</div>'
            '</form>'
            '</div>'
        )

        self._send(200, "text/html", page("Player", body))

    def _post_rename_player(self, form: dict[str, str]) -> None:
        oldp = (form.get("old_player") or "").strip()
        newp = (form.get("new_player") or "").strip()

        if not oldp or not newp:
            return self._redirect(
                "/draft/players?kind=err&msg="
                + urllib.parse.quote("Inserisci sia il player attuale sia il nuovo nome")
            )

        if oldp.casefold() == newp.casefold():
            return self._redirect(
                "/draft/players?kind=err&msg="
                + urllib.parse.quote("Il nuovo nome è uguale al vecchio (ignorando maiuscole/minuscole)")
            )

        with db() as conn:
            conn.execute("BEGIN")
            cur = conn.cursor()
            # Standings
            cur.execute(
                "UPDATE standing SET player = ? WHERE player = ? COLLATE NOCASE",
                (newp, oldp),
            )
            n_standing = cur.rowcount

            # Playoffs
            cur.execute(
                "UPDATE playoff_match SET player_a = ? WHERE player_a = ? COLLATE NOCASE",
                (newp, oldp),
            )
            n_a = cur.rowcount
            cur.execute(
                "UPDATE playoff_match SET player_b = ? WHERE player_b = ? COLLATE NOCASE",
                (newp, oldp),
            )
            n_b = cur.rowcount
            cur.execute(
                "UPDATE playoff_match SET winner = ? WHERE winner = ? COLLATE NOCASE",
                (newp, oldp),
            )
            n_w = cur.rowcount

            conn.commit()

        msg = f"Rinominato '{oldp}' → '{newp}'. standing: {n_standing}, playoff a/b/w: {n_a}/{n_b}/{n_w}"
        self._redirect("/draft/players?kind=ok&msg=" + urllib.parse.quote(msg))

    def _get_tournaments(self, qs: dict[str, str]) -> None:
        conn = db()
        rows = conn.execute(
            "SELECT id, played_at, name, format, rounds FROM tournament ORDER BY played_at DESC, id DESC"
        ).fetchall()

        flash = render_flash(qs)
        items = []
        for r in rows:
            items.append(
                f"<tr>"
                f"<td><a href=\"/draft/tournament?id={int(r['id'])}\">{esc(r['name'])}</a></td>"
                f"<td>{esc(r['played_at'])}</td>"
                f"<td>{esc(r['format'])}</td>"
                f"<td>{esc(str(r['rounds'] or ''))}</td>"
                f"</tr>"
            )

        body = (
            nav()
            + flash
            + "<div class='card'>"
            + "<h2>Draft tornei</h2>"
            + "<p class='muted'>Crea un torneo oppure importa l'output di MTG Companion.</p>"
            + "<h3>Nuovo torneo</h3>"
            + "<form method='POST' action='/draft/tournaments/create'>"
            + "<label>Nome torneo</label><input name='name' placeholder='Friday Draft (MKC)'>"
            + "<label>Data / ora</label><input type='datetime-local' name='played_at' value='{}'>".format(
                esc(iso_to_dtlocal(now_iso()))
            )
            + "<label>Formato</label><input name='format' value='Draft'>"
            + "<label>Rounds (opzionale)</label><input name='rounds' placeholder='3'>"
            + "<label>Note (opzionale)</label><input name='notes' placeholder='...'>"
            + "<div class='btn-row' style='margin-top:12px'><button class='primary' type='submit'>Crea</button></div>"
            + "</form>"
            + "<h3 style='margin-top:18px'>Elenco</h3>"
            + "<div class='table-wrap'><table>"
            + "<thead><tr><th>Torneo</th><th>Played at</th><th>Format</th><th>Rounds</th></tr></thead>"
            + "<tbody>"
            + ("".join(items) if items else "<tr><td colspan='4' class='muted'>Nessun torneo.</td></tr>")
            + "</tbody></table></div>"
            + "</div>"
        )

        self._send(200, "text/html", page("Draft tornei", body))

    def _get_tournament(self, qs: dict[str, str]) -> None:
        tid = int(qs.get("id") or "0")
        conn = db()
        t = conn.execute(
            "SELECT id, played_at, name, format, rounds, notes FROM tournament WHERE id = ?",
            (tid,),
        ).fetchone()
        if not t:
            return self._redirect("/draft/tournaments?kind=err&msg=" + urllib.parse.quote("Torneo non trovato"))

        rows = conn.execute(
            """
            SELECT player, wins, losses, draws, via_pct
            FROM standing
            WHERE tournament_id = ?
            ORDER BY wins DESC, draws DESC, via_pct DESC, player ASC
            """,
            (tid,),
        ).fetchall()

        items = []
        for i, r in enumerate(rows, start=1):
            rec = f"{int(r['wins'])}-{int(r['losses'])}-{int(r['draws'])}"
            via = "" if r["via_pct"] is None else f"{float(r['via_pct']):.2f}%"
            items.append(
                f"<tr><td>{i}</td><td>{esc(r['player'])}</td><td><code>{esc(rec)}</code></td><td>{esc(via)}</td></tr>"
            )

        standings_text = "\n".join(
            [
                f"{r['player']}\t{int(r['wins'])}-{int(r['losses'])}-{int(r['draws'])}\t{(float(r['via_pct']) if r['via_pct'] is not None else 0):.2f}%"
                for r in rows
            ]
        )

        po_rows = conn.execute(
            """
            SELECT stage, player_a, player_b, winner
            FROM playoff_match
            WHERE tournament_id = ?
            ORDER BY CASE stage WHEN 'SF' THEN 1 WHEN 'F' THEN 2 ELSE 9 END, id ASC
            """,
            (tid,),
        ).fetchall()

        po_lines: list[str] = []
        po_edit_lines: list[str] = []
        for r in po_rows:
            stage = str(r["stage"]).strip().upper()
            a = esc(str(r["player_a"]))
            b = esc(str(r["player_b"]))
            w = esc(str(r["winner"]))
            label = "SF" if stage == "SF" else "F" if stage == "F" else stage
            po_lines.append(f"<li><code>{label}</code> {a} vs {b} → <strong>{w}</strong></li>")
            po_edit_lines.append(f"{label}: {str(r['player_a'])} vs {str(r['player_b'])} -> {str(r['winner'])}")
        po_html = ""
        if po_lines:
            po_html = (
                "<h3>Playoff</h3>"
                "<ul style='margin: 8px 0 0 18px'>" + "".join(po_lines) + "</ul>"
            )

        po_edit_text = "\n".join(po_edit_lines)

        edit_html = (
            "<div class='card' style='margin-top:14px'>"
            "<h3 style='margin:0 0 10px'>Modifica torneo</h3>"
            "<form method='POST' action='/draft/tournament/update'>"
            f"<input type='hidden' name='id' value='{tid}'>"
            "<label>Data / ora</label>"
            f"<input type='datetime-local' name='played_at' value='{esc(iso_to_dtlocal(t['played_at']))}'>"
            "<label>Nome</label>"
            f"<input name='name' value='{esc(t['name'])}'>"
            "<label>Formato</label>"
            f"<input name='format' value='{esc(t['format'])}'>"
            "<label>Rounds (opzionale)</label>"
            f"<input name='rounds' value='{esc(str(t['rounds'] or ''))}'>"
            "<label>Note (opzionale)</label>"
            f"<textarea name='notes' rows='3'>{esc(t['notes'] or '')}</textarea>"
            "<div class='btn-row' style='margin-top:12px'>"
            "<button class='primary' type='submit'>Salva torneo</button>"
            "</div>"
            "</form>"
            "</div>"

            "<div class='card' style='margin-top:14px'>"
            "<h3 style='margin:0 0 10px'>Modifica standings (sovrascrive)</h3>"
            "<p class='muted'>Formato atteso: <code>Nome</code> <code>W-L-D</code> <code>VIA%</code> (spazi o tab). Ogni salvataggio sostituisce tutte le righe.</p>"
            "<form method='POST' action='/draft/standing/replace'>"
            f"<input type='hidden' name='tournament_id' value='{tid}'>"
            "<label>Standings</label>"
            f"<textarea name='standings_text' rows='10' style='font-family: ui-monospace, SFMono-Regular, Menlo, monospace'>{esc(standings_text)}</textarea>"
            "<div class='btn-row' style='margin-top:12px'>"
            "<button class='primary' type='submit'>Salva standings</button>"
            "</div>"
            "</form>"
            "</div>"

            "<div class='card' style='margin-top:14px'>"
            "<h3 style='margin:0 0 10px'>Modifica playoff (sovrascrive)</h3>"
            "<p class='muted'>Esempi: <code>SF: Fra &gt; Teo</code> oppure <code>F: Fra vs Giamma -&gt; Fra</code>. Ogni salvataggio sostituisce tutti i match.</p>"
            "<form method='POST' action='/draft/playoffs/replace'>"
            f"<input type='hidden' name='tournament_id' value='{tid}'>"
            "<label>Playoff</label>"
            f"<textarea name='playoffs_text' rows='5' style='font-family: ui-monospace, SFMono-Regular, Menlo, monospace'>{esc(po_edit_text)}</textarea>"
            "<div class='btn-row' style='margin-top:12px'>"
            "<button class='primary' type='submit'>Salva playoff</button>"
            "</div>"
            "</form>"
            "</div>"
        )

        body = (
            nav()
            + "<div class='card'>"
            + f"<h2>{esc(t['name'])}</h2>"
            + f"<p class='muted'>{esc(t['played_at'])} · {esc(t['format'])} · rounds: {esc(str(t['rounds'] or ''))}</p>"
            + (f"<p>{esc(t['notes'] or '')}</p>" if (t["notes"] or "").strip() else "")
            + "<h3>Standings</h3>"
            + "<div class='table-wrap'><table>"
            + "<thead><tr><th>#</th><th>Player</th><th>Record</th><th>VIA%</th></tr></thead>"
            + "<tbody>"
            + ("".join(items) if items else "<tr><td colspan='4' class='muted'>Nessun risultato ancora. Usa Import.</td></tr>")
            + "</tbody></table></div>"
            + po_html
            + "<form method='POST' action='/draft/tournament/delete' onsubmit=\"return confirm('Eliminare questo torneo?')\" style='margin-top:16px'>"
            + f"<input type='hidden' name='id' value='{tid}'>"
            + "<button type='submit'>Elimina torneo</button>"
            + "</form>"
            + "</div>"
            + edit_html
        )
        self._send(200, "text/html", page("Torneo", body))

    def _post_update_tournament(self, form: dict[str, str]) -> None:
        tid = int((form.get("id") or "0").strip() or 0)
        if not tid:
            return self._redirect("/draft/tournaments?kind=err&msg=" + urllib.parse.quote("ID torneo mancante"))

        name = (form.get("name") or "").strip()
        played_at = (form.get("played_at") or "").strip()
        fmt = (form.get("format") or "Draft").strip() or "Draft"
        rounds_s = (form.get("rounds") or "").strip()
        notes = (form.get("notes") or "").strip()

        if not name:
            return self._redirect(f"/draft/tournament?id={tid}&kind=err&msg=" + urllib.parse.quote("Nome mancante"))

        try:
            played_at_iso = dtlocal_to_iso(played_at) if played_at else now_iso()
        except Exception:
            return self._redirect(f"/draft/tournament?id={tid}&kind=err&msg=" + urllib.parse.quote("Data/ora non valida"))

        rounds = None
        if rounds_s:
            try:
                rounds = int(rounds_s)
            except ValueError:
                return self._redirect(f"/draft/tournament?id={tid}&kind=err&msg=" + urllib.parse.quote("Rounds deve essere un intero"))

        conn = db()
        conn.execute(
            "UPDATE tournament SET played_at=?, name=?, format=?, rounds=?, notes=? WHERE id=?",
            (played_at_iso, name, fmt, rounds, notes, tid),
        )
        conn.commit()
        self._redirect(f"/draft/tournament?id={tid}&kind=ok&msg=" + urllib.parse.quote("Torneo aggiornato"))

    def _post_replace_standings(self, form: dict[str, str]) -> None:
        tid_s = (form.get("tournament_id") or "").strip()
        text = (form.get("standings_text") or "").strip()
        if not tid_s:
            return self._redirect("/draft/tournaments?kind=err&msg=" + urllib.parse.quote("Seleziona un torneo"))
        tid = int(tid_s)
        if not text:
            return self._redirect(f"/draft/tournament?id={tid}&kind=err&msg=" + urllib.parse.quote("Standings vuoti"))

        try:
            rows = parse_companion_text(text)
        except Exception as e:
            return self._redirect(f"/draft/tournament?id={tid}&kind=err&msg=" + urllib.parse.quote(str(e)))

        conn = db()
        conn.execute("DELETE FROM standing WHERE tournament_id = ?", (tid,))
        for r in rows:
            conn.execute(
                "INSERT INTO standing(tournament_id, player, wins, losses, draws, via_pct) VALUES(?,?,?,?,?,?)",
                (tid, r["player"], r["w"], r["l"], r["d"], r["via_pct"]),
            )
        conn.commit()
        self._redirect(f"/draft/tournament?id={tid}&kind=ok&msg=" + urllib.parse.quote("Standings aggiornati"))

    def _post_replace_playoffs(self, form: dict[str, str]) -> None:
        tid_s = (form.get("tournament_id") or "").strip()
        text = (form.get("playoffs_text") or "").strip()
        if not tid_s:
            return self._redirect("/draft/tournaments?kind=err&msg=" + urllib.parse.quote("Seleziona un torneo"))
        tid = int(tid_s)

        matches = []
        if text:
            try:
                matches = parse_playoffs_text(text)
            except Exception as e:
                return self._redirect(f"/draft/tournament?id={tid}&kind=err&msg=" + urllib.parse.quote(str(e)))

        conn = db()
        conn.execute("DELETE FROM playoff_match WHERE tournament_id = ?", (tid,))
        for m in matches:
            conn.execute(
                "INSERT INTO playoff_match(tournament_id, stage, player_a, player_b, winner) VALUES(?,?,?,?,?)",
                (tid, m["stage"], m["player_a"], m["player_b"], m["winner"]),
            )
        conn.commit()
        self._redirect(f"/draft/tournament?id={tid}&kind=ok&msg=" + urllib.parse.quote("Playoff aggiornati"))

    def _get_import(self, qs: dict[str, str]) -> None:
        conn = db()
        tournaments = conn.execute(
            "SELECT id, name, played_at FROM tournament ORDER BY played_at DESC, id DESC LIMIT 50"
        ).fetchall()

        options = [f"<option value='{int(t['id'])}'>{esc(t['played_at'])} — {esc(t['name'])}</option>" for t in tournaments]

        flash = render_flash(qs)
        example = """Marco Rossi\t3-0-0\t67.89\nGiulia\t2-1-0\t55.50%\nAle 1-2-0 44.12"""
        example_po = """SF: Fra > Teo\nSF: Giamma > Lori\nF: Fra > Giamma"""

        body = (
            nav()
            + flash
            + "<div class='card'>"
            + "<h2>Import da MTG Companion</h2>"
            + "<p class='muted'>Incolla le standings. Formato atteso: <code>Nome</code> <code>W-L-D</code> <code>VIA%</code> (spazi o tab).</p>"
            + "<form method='POST' action='/draft/import'>"
            + "<label>Torneo</label>"
            + "<select name='tournament_id' style='padding:10px;border-radius:10px;border:1px solid #ccc;width:100%;font-size:1rem'>"
            + ("".join(options) if options else "<option value=''>Nessun torneo (creane uno prima)</option>")
            + "</select>"
            + "<label>Standings (paste)</label>"
            + f"<textarea name='standings' rows='10' placeholder='{esc(example)}'></textarea>"
            + "<label>Playoff (opzionale)</label>"
            + "<p class='muted'>Incolla 1-3 righe (SF/F). Esempi: <code>SF: Fra &gt; Teo</code> oppure <code>F: Fra vs Giamma -&gt; Fra</code>.</p>"
            + f"<textarea name='playoffs' rows='4' placeholder='{esc(example_po)}'></textarea>"
            + "<div class='btn-row' style='margin-top:12px'>"
            + "<button class='primary' type='submit'>Importa</button>"
            + "</div>"
            + "</form>"
            + "</div>"
        )

        self._send(200, "text/html", page("Import", body))

    def _post_create_tournament(self, form: dict[str, str]) -> None:
        name = (form.get("name") or "").strip() or "Draft"
        played_at = (form.get("played_at") or "").strip()
        fmt = (form.get("format") or "Draft").strip() or "Draft"
        rounds_s = (form.get("rounds") or "").strip()
        notes = (form.get("notes") or "").strip()

        if not played_at:
            played_at_iso = now_iso()
        else:
            played_at_iso = dtlocal_to_iso(played_at)

        rounds = None
        if rounds_s:
            try:
                rounds = int(rounds_s)
            except ValueError:
                return self._redirect("/draft/tournaments?kind=err&msg=" + urllib.parse.quote("Rounds deve essere un intero"))

        conn = db()
        cur = conn.execute(
            "INSERT INTO tournament(played_at, name, format, rounds, notes) VALUES(?,?,?,?,?)",
            (played_at_iso, name, fmt, rounds, notes),
        )
        conn.commit()
        tid = cur.lastrowid
        self._redirect(f"/draft/tournament?id={tid}")

    def _post_delete_tournament(self, form: dict[str, str]) -> None:
        tid = int((form.get("id") or "0") or "0")
        conn = db()
        conn.execute("DELETE FROM tournament WHERE id = ?", (tid,))
        conn.commit()
        self._redirect("/draft/tournaments?kind=ok&msg=" + urllib.parse.quote("Torneo eliminato"))

    def _post_import(self, form: dict[str, str]) -> None:
        tid_s = (form.get("tournament_id") or "").strip()
        if not tid_s:
            return self._redirect("/draft/import?kind=err&msg=" + urllib.parse.quote("Seleziona un torneo"))
        tid = int(tid_s)
        text = form.get("standings") or ""
        po_text = form.get("playoffs") or ""

        try:
            rows = parse_companion_text(text)
        except Exception as e:
            return self._redirect("/draft/import?kind=err&msg=" + urllib.parse.quote(str(e)))

        try:
            playoffs = parse_playoffs_text(po_text) if po_text.strip() else []
        except Exception as e:
            return self._redirect("/draft/import?kind=err&msg=" + urllib.parse.quote(str(e)))

        conn = db()
        # replace standings for tournament
        conn.execute("DELETE FROM standing WHERE tournament_id = ?", (tid,))
        conn.execute("DELETE FROM playoff_match WHERE tournament_id = ?", (tid,))
        for r in rows:
            conn.execute(
                "INSERT INTO standing(tournament_id, player, wins, losses, draws, via_pct) VALUES(?,?,?,?,?,?)",
                (tid, r["player"], int(r["w"]), int(r["l"]), int(r["d"]), float(r["via_pct"])),
            )

        for m in playoffs:
            conn.execute(
                "INSERT INTO playoff_match(tournament_id, stage, player_a, player_b, winner) VALUES(?,?,?,?,?)",
                (tid, m["stage"], m["player_a"], m["player_b"], m["winner"]),
            )
        conn.commit()

        self._redirect(
            "/draft/tournament?id="
            + str(tid)
            + "&kind=ok&msg="
            + urllib.parse.quote(
                f"Importati {len(rows)} player" + (f" · playoff: {len(playoffs)} match" if playoffs else "")
            )
        )


def run() -> None:
    with db():
        pass
    server = HTTPServer((HOST, PORT), Handler)
    print(f"Draft admin listening on http://{HOST}:{PORT} (DB={DB_PATH})")
    server.serve_forever()


if __name__ == "__main__":
    run()
