from __future__ import annotations

import json
import posixpath
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import app, engine, GameEntry

# === CONFIG ===
OUT_DIR = Path("docs")
REPO_NAME = "commander-tracker"
REPO_BASE = f"/{REPO_NAME}/"

DATA_DIR = OUT_DIR / "data"
ASSETS_DIR = OUT_DIR / "assets"

# === HOME CONFIG ===
HOME_TITLE = "Tempio Tracker"
HOME_SUBTITLE = ""
HOME_NOTE = ""  # es: "Versione statica per GitHub Pages"
HOME_HERO_PNG = "assets/tempio.jpeg"

# Analisi da pubblicare (read-only)
ANALYSIS_ROUTES = [
    "/summary",
    "/stats",
    "/dashboard_mini",
    "/dashboard_mini_bracket",
    # "/commander_brackets",
]

# file scaricabili
EXTRA_FILES = [
    ("/export.csv", "export.csv"),
    ("/stats.json", "stats.json"),
]

FILE_EXTS = (
    ".csv", ".json", ".pdf", ".html", ".txt",
    ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
    ".woff", ".woff2", ".ttf", ".eot", ".map",
)

# route non supportate in statico (scrittura / azioni)
DISABLED_PREFIXES = (
    "add",
    "edit",
    "match_edit",
    "delete",
    "pdf",
    "export_pdf",
    "generate_pdf",
    "import",
)
DISABLED_FILE_EXTS = [".pdf",".html"]

# ===== Helpers URL / slug =====

def safe_slug(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return "unknown"
    s2 = re.sub(r"\s+", "_", s)
    s2 = re.sub(r"[^A-Za-z0-9_\-\.]", "", s2)
    return quote(s2 or "player")


def _is_external(url: str) -> bool:
    u = (url or "").strip().lower()
    return (
        u.startswith("#")
        or u.startswith("mailto:")
        or u.startswith("tel:")
        or u.startswith("http://")
        or u.startswith("https://")
        or u.startswith("data:")
        or u.startswith("javascript:")
    )


def _strip_repo_base(path: str) -> str:
    if path.startswith(REPO_BASE):
        return path[len(REPO_BASE):]
    if path.startswith("/" + REPO_NAME + "/"):
        return path[len("/" + REPO_NAME + "/"):]
    return path


def _normalize_internal_path(raw: str) -> str:
    href = (raw or "").strip()
    if _is_external(href):
        return ""
    href = href.split("#", 1)[0].split("?", 1)[0].strip()
    href = _strip_repo_base(href).lstrip("/")
    while href.startswith("./"):
        href = href[2:]
    while href.startswith("../"):
        href = href[3:]
    return posixpath.normpath(href).lstrip(".").lstrip("/")


def _is_disabled_path(raw: str) -> bool:
    p = _normalize_internal_path(raw)
    if not p:
        return False
    low = p.lower()
    for d in DISABLED_FILE_EXTS:
        if low.endswith(d):
            return True
        for pref in DISABLED_PREFIXES:
            pref = pref.lower()
            if low == pref or low.startswith(pref + "/"):
                return True
    return False


def _to_pages_url(raw: str) -> str:
    """
    Converte URL interno in URL GitHub Pages:
    - pagine:  /<repo>/path/
    - file:    /<repo>/path.ext
    Special case:
    - "/" (root) su Pages è la HOME statica introduttiva.
    """
    href = (raw or "").strip()

    if href in ("", ".", "./"):
        return REPO_BASE

    if _is_external(href):
        return href

    frag = ""
    if "#" in href:
        href, frag_ = href.split("#", 1)
        frag = "#" + frag_

    query = ""
    if "?" in href:
        href, q_ = href.split("?", 1)
        query = "?" + q_

    href = _strip_repo_base(href).lstrip("/")
    while href.startswith("./"):
        href = href[2:]
    while href.startswith("../"):
        href = href[3:]

    href = posixpath.normpath(href).lstrip(".")
    if href in ("", "/"):
        # root -> home statica
        return REPO_BASE + frag

    lower = href.lower()
    if lower.endswith(FILE_EXTS):
        return f"{REPO_BASE}{href}{query}{frag}"

    href = href.strip("/")
    return f"{REPO_BASE}{href}/{query}{frag}"


# ===== Static navbar =====

NAV_LINKS = [
    ("Home", "/"),
    ("Ultime 30", "/recent"),
    ("Summary", "/summary"),
    ("Decks info", "/triplette"),
    ("Statistiche", "/stats"),
    ("Dashboard", "/dashboard_mini"),
    ("Dashboard (Bracket)", "/dashboard_mini_bracket"),
    # ("Bracket Commander", "/commander_brackets"),
    ("Player", "/player_dashboard"),
    ("Export CSV", "/export.csv"),
]


def _read_base_css() -> str:
    """Best-effort: reuse the CSS from templates/base.html so static pages match the current rendering."""
    try:
        base = Path("templates") / "base.html"
        if not base.exists():
            return ""
        soup = BeautifulSoup(base.read_text(encoding="utf-8"), "html.parser")
        style = soup.find("style")
        return (style.text or "").strip() if style else ""
    except Exception:
        return ""


BASE_CSS = _read_base_css()


def _wrap_static_page(*, title: str, body_html: str, extra_head: str = "") -> str:
    """Build a static page that visually matches the current Jinja rendering (base.html)."""
    css = BASE_CSS
    # fallback minimal css if base.html changes
    if not css:
        css = "body{font-family:system-ui,Segoe UI,Roboto,sans-serif;max-width:1200px;margin:24px auto;padding:0 16px;} nav a{margin-right:12px;}"  # noqa: E501

    html = f"""<!doctype html>
<html lang=\"it\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{title}</title>
  <style>{css}</style>
  {extra_head}
</head>
<body>
  <nav></nav>
  <hr />
  {body_html}
</body>
</html>"""

    soup = BeautifulSoup(html, "html.parser")
    _inject_static_navbar(soup)
    return str(soup)


def _inject_static_navbar(soup: BeautifulSoup) -> None:
    nav = soup.find("nav")
    if not nav:
        # create a nav at top if missing
        body = soup.body
        if not body:
            return
        nav = soup.new_tag("nav")
        body.insert(0, nav)

    nav.clear()
    for i, (label, href) in enumerate(NAV_LINKS):
        a = soup.new_tag("a", href=_to_pages_url(href))
        a.string = label
        nav.append(a)
        if i != len(NAV_LINKS) - 1:
            nav.append(soup.new_string("\n"))


# ===== Read-only transformation =====

def make_consultation_only(html: str, *, page_key: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # 1) Navbar consistente
    _inject_static_navbar(soup)

    # 2) Remove all input controls (read-only on Pages)
    for tag in soup.find_all(["form", "button", "textarea", "select", "input"]):
        tag.decompose()

    # 3) CSS helper for disabled links + hide navbar in iframes
    head = soup.head
    if head is not None:
        style = soup.new_tag("style")
        style.string = ".disabled-link{pointer-events:none;opacity:.45;cursor:not-allowed;text-decoration:none}"
        head.append(style)

        style3 = soup.new_tag("style")
        style3.string = """
html.embedded nav,
html.embedded hr {
  display:none !important;
}
html.embedded body{
  margin-top:0 !important;
  padding-top:0 !important;
}
"""
        head.append(style3)

        script = soup.new_tag("script")
        script.string = "if (window.self !== window.top) { document.documentElement.classList.add('embedded'); }"
        head.append(script)

    # 4) Disable unsupported actions (href or onclick)
    for tag in soup.find_all(True):
        if tag.has_attr("onclick"):
            del tag["onclick"]

    for a in soup.find_all("a", href=True):
        raw = a["href"]
        if _is_disabled_path(raw):
            a["href"] = "#"
            a["title"] = "Non disponibile nella versione statica"
            cls = a.get("class", [])
            if "disabled-link" not in cls:
                cls.append("disabled-link")
            a["class"] = cls
            continue
        a["href"] = _to_pages_url(raw)

    # 5) Rewrite assets
    for link in soup.find_all("link", href=True):
        link["href"] = _to_pages_url(link["href"])
    for script in soup.find_all("script", src=True):
        script["src"] = _to_pages_url(script["src"])
    for tag in soup.find_all(["img", "source", "iframe"], src=True):
        tag["src"] = _to_pages_url(tag["src"])

    # 6) Extract embedded JSON (if present) to docs/data
    _extract_embedded_json(soup, page_key=page_key)

    return str(soup)


def _extract_embedded_json(soup: BeautifulSoup, *, page_key: str) -> None:
    """
    Estrae <script type="application/json">...</script> in file JSON:
    - per dashboard/summary/player ecc.
    """
    scripts = soup.find_all("script", attrs={"type": "application/json"})
    if not scripts:
        return

    payloads = []
    for s in scripts:
        txt = (s.text or "").strip()
        if not txt:
            continue
        try:
            payloads.append(json.loads(txt))
        except Exception:
            continue

    if not payloads:
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "page": page_key,
        "payloads": payloads,
    }
    (DATA_DIR / f"{page_key}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


# ===== Writers =====

def write_page(path_key: str, html: str):
    if path_key == "/":
        out_path = OUT_DIR / "index.html"
    else:
        folder = path_key.strip("/").split("?")[0]
        out_path = OUT_DIR / folder / "index.html"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")


def write_home_page():
    """
    Home statica per GitHub Pages: pagina pulita con solo titolo + immagine hero.
    (Niente widget / form per evitare UI "interattive" in Home.)
    """
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    body_html = f"""
  <main class="home">
    <img
      class="home-hero"
      src="{REPO_BASE}{HOME_HERO_PNG}"
      alt="Tempio"
      loading="eager"
      decoding="async"
    />
    <h1 class="home-title">{HOME_TITLE}</h1>
  </main>
"""
    write_page("/", _wrap_static_page(title=HOME_TITLE, body_html=body_html))









def write_triplette_page():
    # Reads docs/data/triplette.json if present; otherwise builds from DB.
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    trip_file = DATA_DIR / "triplette.json"
    if not trip_file.exists():
        with Session(engine) as session:
            entries = session.exec(select(GameEntry.player, GameEntry.commander, GameEntry.bracket)).all()
        c = Counter((p, cmd, br) for (p, cmd, br) in entries)
        rows = [{"player": p, "commander": cmd, "bracket": br, "games": n} for (p, cmd, br), n in c.items()]
        rows.sort(key=lambda r: (r["player"].lower(), r["commander"].lower(), (r["bracket"] or "")))
        trip_file.write_text(json.dumps({"version":1,"generated_at":datetime.now(timezone.utc).isoformat(),"data":rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    body_html = f"""
  <h1>Decks info</h1>
  <p class="muted">Combinazioni Player – Commander – Bracket con numero di partite.</p>
  <input id="q" placeholder="Filtra (player/commander/bracket)…" />
  <table>
    <thead><tr><th>Player</th><th>Commander</th><th>Bracket</th><th style="text-align:right;"># Partite</th></tr></thead>
    <tbody id="tb"></tbody>
  </table>

  <script>
    const BASE = {json.dumps(REPO_BASE)};
    let data = [];
    function esc(s) {{
      return String(s ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
    }}
    function row(r) {{
      const br = (r.bracket === null || r.bracket === undefined || r.bracket === '') ? '-' : r.bracket;
      return `<tr><td>${{esc(r.player)}}</td><td>${{esc(r.commander)}}</td><td>${{esc(br)}}</td><td style="text-align:right;">${{esc(r.games)}}</td></tr>`;
    }}
    function render() {{
      const q = document.getElementById('q').value.trim().toLowerCase();
      const rows = q ? data.filter(r => (`${{r.player}} ${{r.commander}} ${{r.bracket ?? ''}}`).toLowerCase().includes(q)) : data;
      document.getElementById('tb').innerHTML = rows.map(row).join('');
    }}
    fetch(BASE + 'data/triplette.json').then(r => r.json()).then(j => {{
      data = j.data || j;
      render();
    }});
    document.getElementById('q').addEventListener('input', render);
  </script>
"""
    write_page("/triplette", _wrap_static_page(title="Triplette", body_html=body_html))


def write_triplette_json():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with Session(engine) as session:
        entries = session.exec(select(GameEntry.player, GameEntry.commander, GameEntry.bracket)).all()
    c = Counter((p, cmd, br) for (p, cmd, br) in entries)
    rows = [{"player": p, "commander": cmd, "bracket": br, "games": n} for (p, cmd, br), n in c.items()]
    rows.sort(key=lambda r: (r["player"].lower(), r["commander"].lower(), (r["bracket"] or "")))
    out = {"version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "data": rows}
    (DATA_DIR / "triplette.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def write_recent_games_json(limit: int = 30):
    """Write docs/data/recent_games.json with the latest games + full lineups."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with Session(engine) as session:
        # Latest games first
        from app import Game  # local import to avoid circulars at module import time

        latest_games = session.exec(
            select(Game).order_by(Game.played_at.desc(), Game.id.desc()).limit(limit)
        ).all()

        game_ids = [int(g.id) for g in latest_games if g.id is not None]
        if game_ids:
            entries = session.exec(
                select(GameEntry).where(GameEntry.game_id.in_(game_ids)).order_by(GameEntry.game_id.asc())
            ).all()
        else:
            entries = []

    entries_by_game: dict[int, list[dict]] = {}
    for e in entries:
        gid = int(e.game_id)
        entries_by_game.setdefault(gid, []).append(
            {
                "player": e.player,
                "commander": e.commander,
                "bracket": e.bracket,
            }
        )

    def _iso(dt):
        try:
            return dt.isoformat() if dt else ""
        except Exception:
            return ""

    data = []
    for g in latest_games:
        if g.id is None:
            continue
        gid = int(g.id)
        lineup = entries_by_game.get(gid, [])
        lineup.sort(key=lambda r: (str(r.get("player") or "").lower(), str(r.get("commander") or "").lower()))
        data.append(
            {
            "played_at_utc": _iso(getattr(g, "played_at", None)),
                "winner_player": getattr(g, "winner_player", None) or "",
                "notes": getattr(g, "notes", None) or "",
                "participants": len(lineup),
                "lineup": lineup,
            }
        )

    out = {"version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "limit": limit, "games": data}
    (DATA_DIR / "recent_games.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def write_recent_games_page():
    """Static page with a small filter form + table (latest 30 games)."""
    body_html = f"""
  <h1>Ultime 30 partite</h1>
  <p class="muted">Pagina statica (GitHub Pages). Filtra per player o commander e scorri le partite più recenti.</p>

  <div class="card">
    <label for="q"><b>Filtro</b></label><br/>
    <input id="q" placeholder="Es: Luca / Atraxa / bracket 3…" style="width:min(520px, 100%);" />
    <div class="muted" style="margin-top:8px;">Suggerimento: puoi cercare anche per <i>winner</i> e per <i>note</i>.</div>
  </div>

  <table>
    <thead>
      <tr>
        <th>Data (UTC)</th>
        <th>Partecipanti</th>
        <th>Winner</th>
        <th>Lineup</th>
        <th>Note</th>
      </tr>
    </thead>
    <tbody id="tb"></tbody>
  </table>

  <script>
    const BASE = {json.dumps(REPO_BASE)};
    let games = [];

    function esc(s) {{
      return String(s ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
    }}

    function fmtLineup(lineup) {{
      if (!Array.isArray(lineup) || !lineup.length) return '';
      return lineup.map(e => {{
        const br = (e.bracket === null || e.bracket === undefined || e.bracket === '') ? '' : ` (B${{e.bracket}})`;
        return `${{esc(e.player)}} = ${{esc(e.commander)}}${{esc(br)}}`;
      }}).join('<br/>');
    }}

    function row(g) {{
      const dt = esc(g.played_at_utc || '');
      const parts = esc(g.participants ?? '');
      const win = esc(g.winner_player || '');
      const notes = esc(g.notes || '');
      return `<tr>
        <td style="white-space:nowrap;">${{dt}}</td>
        <td style="text-align:right;">${{parts}}</td>
        <td>${{win}}</td>
        <td>${{fmtLineup(g.lineup)}}</td>
        <td>${{notes}}</td>
      </tr>`;
    }}

    function render() {{
      const q = document.getElementById('q').value.trim().toLowerCase();
      const rows = q
        ? games.filter(g => {{
            const blob = `${{g.played_at_utc}} ${{g.winner_player}} ${{g.notes}} ` +
              (Array.isArray(g.lineup) ? g.lineup.map(e => `${{e.player}} ${{e.commander}} ${{e.bracket ?? ''}}`).join(' ') : '');
            return blob.toLowerCase().includes(q);
          }})
        : games;
      document.getElementById('tb').innerHTML = rows.map(row).join('');
    }}

    fetch(BASE + 'data/recent_games.json')
      .then(r => r.json())
      .then(j => {{ games = j.games || []; render(); }});

    document.getElementById('q').addEventListener('input', render);
  </script>
"""
    write_page("/recent", _wrap_static_page(title="Ultime 30 partite", body_html=body_html))


def write_player_compare_page(players: list[str]):
    """Static player compare: two dropdowns + two iframes side-by-side."""
    # Build <option> list once (stable order)
    opts = "\n".join(
        [f"<option value='{safe_slug(p)}'>{p}</option>" for p in players]
    )

    body_html = f"""
  <h1>Confronto Player</h1>
  <p class='muted'>Seleziona due player per vedere le dashboard affiancate. (Sola lettura)</p>

  <div class='card'>
    <div class='row' style='gap:12px; flex-wrap:wrap; align-items:end;'>
      <div style='min-width:240px;'>
        <label>Player A</label><br/>
        <select id='a'>
          <option value=''>— scegli —</option>
          {opts}
        </select>
      </div>

      <div style='min-width:240px;'>
        <label>Player B</label><br/>
        <select id='b'>
          <option value=''>— scegli —</option>
          {opts}
        </select>
      </div>

      <div>
        <label>Altezza</label><br/>
        <input id='h' type='number' min='600' step='100' value='1600' style='width:120px;' />
      </div>

      <div>
        <button id='swap' type='button'>Scambia</button>
      </div>
    </div>
  </div>

  <div class='row' style='gap:12px; flex-wrap:wrap;'>
    <div class='card' style='flex:1; min-width:360px;'>
      <h2 style='margin-top:0;'>Player A</h2>
      <iframe id='fa' style='width:100%; border:1px solid #ddd; border-radius:10px;'></iframe>
    </div>
    <div class='card' style='flex:1; min-width:360px;'>
      <h2 style='margin-top:0;'>Player B</h2>
      <iframe id='fb' style='width:100%; border:1px solid #ddd; border-radius:10px;'></iframe>
    </div>
  </div>

  <script>
    const BASE = {json.dumps(REPO_BASE)};
    const selA = document.getElementById('a');
    const selB = document.getElementById('b');
    const fa = document.getElementById('fa');
    const fb = document.getElementById('fb');
    const h = document.getElementById('h');
    const swap = document.getElementById('swap');

    function playerUrl(slug) {{
      return slug ? (BASE + 'player/' + encodeURIComponent(slug) + '/') : '';
    }}

    function getParams() {{
      const p = new URLSearchParams(window.location.search);
      return {{ a: p.get('a') || '', b: p.get('b') || '' }};
    }}

    function setParams(a, b) {{
      const p = new URLSearchParams();
      if (a) p.set('a', a);
      if (b) p.set('b', b);
      const qs = p.toString();
      const url = window.location.pathname + (qs ? ('?' + qs) : '');
      history.replaceState(null, '', url);
    }}

    function apply() {{
      const a = selA.value;
      const b = selB.value;
      fa.src = playerUrl(a);
      fb.src = playerUrl(b);
      const px = parseInt(h.value || '1600', 10);
      fa.style.height = px + 'px';
      fb.style.height = px + 'px';
      setParams(a, b);
    }}

    selA.addEventListener('change', apply);
    selB.addEventListener('change', apply);
    h.addEventListener('change', apply);
    swap.addEventListener('click', () => {{
      const tmp = selA.value;
      selA.value = selB.value;
      selB.value = tmp;
      apply();
    }});

    const init = getParams();
    if (init.a) selA.value = init.a;
    if (init.b) selB.value = init.b;
    apply();
  </script>
"""

    html = _wrap_static_page(title="Player (Confronto)", body_html=body_html)
    write_page("/player_dashboard", html)


def export_static() -> None:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / ".nojekyll").write_text("", encoding="utf-8")

    client = TestClient(app)

    # 1) Home introduttiva (solo Pages)
    write_home_page()

    # 2) JSON extra (triplette) + pagina
    write_triplette_json()
    write_triplette_page()

    # 2b) Ultime partite (JSON + pagina)
    write_recent_games_json(limit=30)
    write_recent_games_page()

    # 3) Analisi HTML "identiche" (rendering attuale) in sola lettura
    for route in ANALYSIS_ROUTES:
        r = client.get(route)
        if r.status_code != 200:
            raise RuntimeError(f"GET {route} -> {r.status_code}")
        page_key = route.strip("/").replace("/", "_") or "root"
        html = make_consultation_only(r.text, page_key=page_key)
        write_page(route, html)

    # 4) file extra
    for route, filename in EXTRA_FILES:
        r = client.get(route)
        if r.status_code != 200:
            raise RuntimeError(f"GET {route} -> {r.status_code}")
        (OUT_DIR / filename).write_bytes(r.content)

    # 5) Player pages (read-only)
    with Session(engine) as session:
        players = sorted(
            {e.player for e in session.exec(select(GameEntry)).all()},
            key=lambda s: s.lower(),
        )

    # 5b) Player compare page (read-only, but interactive)
    write_player_compare_page(players)

    for p in players:
        slug = safe_slug(p)
        r = client.get("/player_dashboard", params={"player": p})
        if r.status_code != 200:
            raise RuntimeError(f"GET /player_dashboard?player={p} -> {r.status_code}")
        html = make_consultation_only(r.text, page_key=f"player_{slug}")
        out_path = OUT_DIR / "player" / slug / "index.html"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")

        # also write JSON extracted (done by make_consultation_only) - file name already player_<slug>.json

    # 6) Player index page (static, read-only)
    links = "\n".join([f"<a href='{REPO_BASE}player/{safe_slug(p)}/'>{p}</a>" for p in players])
    body_html = f"""
  <h1>Players</h1>
  <p class='muted'>Lista player (sola lettura). Per il confronto, usa <a href='{REPO_BASE}player_dashboard/'>Player</a>.</p>
  <div class='card'>
    {links}
  </div>
"""
    out_path = OUT_DIR / "player" / "index.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_wrap_static_page(title="Players", body_html=body_html), encoding="utf-8")

    print(f"✅ Export completato in: {OUT_DIR.resolve()}")
    print(f"🌐 Base GitHub Pages usata: {REPO_BASE}")


if __name__ == "__main__":
    export_static()
