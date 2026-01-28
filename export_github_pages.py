import re
import shutil
import posixpath
from pathlib import Path
from urllib.parse import quote

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from app import app, engine, GameEntry
from sqlmodel import Session, select

import json
from collections import Counter

# === CONFIG ===
OUT_DIR = Path("docs")  # GitHub Pages serve /docs
REPO_NAME = "commander-tracker"
REPO_BASE = f"/{REPO_NAME}/"

# HOME (/) viene generata dalla route /summary (vedi export()).
BASE_ROUTES = [
    "/summary",                 # -> HOME + /summary/
    "/stats",
    "/dashboard_mini",
    "/dashboard_mini_bracket",
    "/commander_brackets",
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

# route non supportate in statico
DISABLED_PREFIXES = (
    "edit",
    "match_edit",
    "delete",
    "pdf",
    "export_pdf",
    "generate_pdf",
)
DISABLED_FILE_EXTS = (".pdf",)

# ordine navbar (facoltativo)
NAV_ORDER = [
    "",          # Home (Summary)
    "triplette",
    "player_dashboard",
    "dashboard_mini",
    "dashboard_mini_bracket",
    "stats",
    "commander_brackets",
    "partite",   # Partite (index)
    "export.csv",
    "add",
]
# nascondi voci navbar (facoltativo)
NAV_HIDE = {
    "add",
    "commander_brackets",
    "export.csv"
}


def safe_slug(s: str) -> str:
    """Slug semplice + URL-safe per nomi player."""
    s = s.strip()
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
    """Normalizza href interno: niente query/fragment, niente leading '/', niente repo base."""
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
    if low.endswith(DISABLED_FILE_EXTS):
        return True

    for pref in DISABLED_PREFIXES:
        pref = pref.lower()
        if low == pref or low.startswith(pref + "/"):
            return True
    return False


def _onclick_contains_disabled(oc: str) -> bool:
    if not oc:
        return False
    s = oc.lower()
    if ".pdf" in s or "summary.pdf" in s:
        return True
    for pref in DISABLED_PREFIXES:
        if pref.lower() in s:
            return True
    return False


def _to_pages_url(raw: str) -> str:
    """
    Converte URL interno in URL GitHub Pages:
    - pagine:  /<repo>/path/
    - file:    /<repo>/path.ext

    Redirect logici:
    - /player_dashboard -> /player_dashboard/ (confronto)
    - /player (senza slug) -> /player_dashboard/ (evita "lista player" come entrypoint)
    - / (root) resta root: ora è SUMMARY (perché docs/index.html = summary)
    """
    href = (raw or "").strip()

    if href in ("", ".", "./", "/"):
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
        return REPO_BASE + frag

    parts = [p for p in href.strip("/").split("/") if p]

    if parts and parts[0] == "player" and len(parts) == 1:
        return f"{REPO_BASE}player_dashboard/{frag}"

    if href == "player_dashboard" or href.startswith("player_dashboard/"):
        return f"{REPO_BASE}player_dashboard/{frag}"

    if href == "add" or href.startswith("add/"):
        return f"{REPO_BASE}add/{frag}"

    lower = href.lower()
    if lower.endswith(FILE_EXTS):
        return f"{REPO_BASE}{href}{query}{frag}"

    href = href.strip("/")
    return f"{REPO_BASE}{href}/{query}{frag}"


def _reorder_and_filter_navbar(soup: BeautifulSoup) -> None:
    """Riordina e/o rimuove voci della navbar (<nav> ... <a/> ...)."""
    nav = soup.find("nav")
    if not nav:
        return

    # links = nav.find_all("a", href=True, recursive=False)
    links = nav.find_all("a", href=True)  # prende anche quelli annidati

    visible = []
    for a in links:
        p = _normalize_internal_path(a.get("href", ""))
        if p in (".", "/"):
            p = ""
        if p in NAV_HIDE:
            continue
        visible.append(a)

    def nav_key(a_tag):
        p = _normalize_internal_path(a_tag.get("href", ""))
        if p in (".", "/"):
            p = ""
        for i, wanted in enumerate(NAV_ORDER):
            if wanted == p or (wanted and p.startswith(wanted + "/")):
                return (i, p)
        return (999, p)

    ordered = sorted(visible, key=nav_key)

    nav.clear()
    for a in ordered:
        nav.append(a)
        nav.append(soup.new_string("\n"))


def make_consultation_only(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # --- NAV FIX per export: separa Home (Summary) da Partite ---
    nav = soup.find("nav")
    if nav:
        for a in nav.find_all("a", href=True):
            href = a["href"].strip()

            # "Partite" (/) nello statico deve andare a /partite
            if href == "/":
                a["href"] = "/partite"

            # "Summary" (/summary) nello statico deve diventare la Home
            elif href == "/summary":
                a["href"] = "/"
                # opzionale: rinomina voce
                # a.string = "Home"

    # aggiungi link "Triplette" solo nello statico (dopo Summary/Home)
    nav = soup.find("nav")
    if nav:
        # evita duplicati
        exists = any(_normalize_internal_path(a.get("href","")) == "triplette" for a in nav.find_all("a", href=True))
        if not exists:
            a = soup.new_tag("a", href="/triplette")
            a.string = "Triplette"
            # la inseriamo subito dopo il link a Summary (che nello statico hai rimappato a "/")
            inserted = False
            links = nav.find_all("a", href=True)
            for i, link in enumerate(links):
                if link.get("href","").strip() in ("/", "/summary"):
                    link.insert_after(a)
                    inserted = True
                    break
            if not inserted:
                nav.append(a)


    _reorder_and_filter_navbar(soup)

    for tag in soup.find_all(["form", "button", "textarea", "select", "input"]):
        tag.decompose()

    head = soup.head
    if head is not None:
        style = soup.new_tag("style")
        style.string = ".disabled-link{pointer-events:none;opacity:.45;cursor:not-allowed;text-decoration:none}"
        head.append(style)

        style2 = soup.new_tag("style")
        style2.string = "html.embedded .export-html{pointer-events:none;opacity:.45;cursor:not-allowed;text-decoration:none}"
        head.append(style2)

        # Embedded: nascondi navbar / header chrome negli iframe
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

    for tag in soup.find_all(True):
        if tag.has_attr("onclick") and _onclick_contains_disabled(tag.get("onclick", "")):
            if tag.name == "a":
                tag["href"] = "#"
                tag["title"] = "Non disponibile nella versione statica"
                cls = tag.get("class", [])
                if "disabled-link" not in cls:
                    cls.append("disabled-link")
                tag["class"] = cls
            del tag["onclick"]

    for a in soup.find_all("a", href=True):
        raw = a["href"]

        norm = _normalize_internal_path(raw)
        if norm and norm.lower().startswith("player_dashboard.html"):
            cls = a.get("class", [])
            if "export-html" not in cls:
                cls.append("export-html")
            a["class"] = cls
            a["title"] = a.get("title", "Export non disponibile nella vista confronto")

        if _is_disabled_path(raw):
            a["href"] = "#"
            a["title"] = "Non disponibile nella versione statica"
            cls = a.get("class", [])
            if "disabled-link" not in cls:
                cls.append("disabled-link")
            a["class"] = cls
            continue

        a["href"] = _to_pages_url(raw)

    for link in soup.find_all("link", href=True):
        link["href"] = _to_pages_url(link["href"])

    for script in soup.find_all("script", src=True):
        script["src"] = _to_pages_url(script["src"])

    for tag in soup.find_all(["img", "source", "iframe"], src=True):
        tag["src"] = _to_pages_url(tag["src"])

    return str(soup)


def write_page(path_key: str, html: str):
    if path_key == "/":
        out_path = OUT_DIR / "index.html"
    else:
        folder = path_key.strip("/").split("?")[0]
        out_path = OUT_DIR / folder / "index.html"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")


def write_player_compare_page(players_index: list[tuple[str, str]], out_folder: str = "player_dashboard"):
    page = [
        "<!doctype html><html lang='it'><head><meta charset='utf-8'/>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'/>",
        "<title>Confronto Player</title>",
        "<style>",
        "body{font-family:system-ui,Segoe UI,Roboto,sans-serif;max-width:1200px;margin:24px auto;padding:0 16px;}",
        ".top{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin:12px 0 18px;}",
        "select,input,button{padding:10px;font-size:16px;}",
        ".grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;align-items:start;}",
        "@media (max-width: 980px){.grid{grid-template-columns:1fr;}}",
        "iframe{width:100%;border:1px solid #ddd;border-radius:10px;}",
        ".hint{color:#555;margin-top:0;}",
        "</style></head><body>",
        "<h1>Confronto Player</h1>",
        f"<p><a href='{REPO_BASE}'>← Home</a> &nbsp;|&nbsp; <a href='{REPO_BASE}player/'>Lista player</a></p>",
        "<p class='hint'>Seleziona due player per vedere le loro dashboard affiancate.</p>",
        "<div class='top'>",
        "<label for='a'>Player A</label>",
        "<select id='a'><option value=''>— scegli —</option>",
    ]

    for name, href in players_index:
        slug = href.strip("/").split("/")[-1]
        page.append(f"<option value='{slug}'>{name}</option>")

    page += [
        "</select>",
        "<label for='b'>Player B</label>",
        "<select id='b'><option value=''>— scegli —</option>",
    ]

    for name, href in players_index:
        slug = href.strip("/").split("/")[-1]
        page.append(f"<option value='{slug}'>{name}</option>")

    page += [
        "</select>",
        "<label for='h'>Altezza</label>",
        "<input id='h' type='number' min='600' step='100' value='1600' style='width:110px'/>",
        "<button id='swap' type='button'>Scambia</button>",
        "</div>",
        "<div class='grid'>",
        "<div><iframe id='frameA' title='Dashboard A'></iframe></div>",
        "<div><iframe id='frameB' title='Dashboard B'></iframe></div>",
        "</div>",
        "<script>",
        "  const selA = document.getElementById('a');",
        "  const selB = document.getElementById('b');",
        "  const frameA = document.getElementById('frameA');",
        "  const frameB = document.getElementById('frameB');",
        "  const h = document.getElementById('h');",
        "  const swap = document.getElementById('swap');",
        "  function getParams(){",
        "    const p = new URLSearchParams(window.location.search);",
        "    return { a: p.get('a') || '', b: p.get('b') || '' };",
        "  }",
        "  function setParams(a, b){",
        "    const p = new URLSearchParams();",
        "    if (a) p.set('a', a);",
        "    if (b) p.set('b', b);",
        "    const qs = p.toString();",
        "    const url = window.location.pathname + (qs ? ('?' + qs) : '');",
        "    history.replaceState(null, '', url);",
        "  }",
        f"  function playerUrl(slug){{ return slug ? '{REPO_BASE}player/' + encodeURIComponent(slug) + '/' : ''; }}",
        "  function apply(){",
        "    const a = selA.value;",
        "    const b = selB.value;",
        "    frameA.src = playerUrl(a);",
        "    frameB.src = playerUrl(b);",
        "    const px = parseInt(h.value || '1600', 10);",
        "    frameA.style.height = px + 'px';",
        "    frameB.style.height = px + 'px';",
        "    setParams(a, b);",
        "  }",
        "  selA.addEventListener('change', apply);",
        "  selB.addEventListener('change', apply);",
        "  h.addEventListener('change', apply);",
        "  swap.addEventListener('click', () => {",
        "    const tmp = selA.value;",
        "    selA.value = selB.value;",
        "    selB.value = tmp;",
        "    apply();",
        "  });",
        "  const init = getParams();",
        "  if (init.a) selA.value = init.a;",
        "  if (init.b) selB.value = init.b;",
        "  apply();",
        "</script>",
        "</body></html>",
    ]

    out_path = OUT_DIR / out_folder / "index.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(page), encoding="utf-8")


def write_add_page():
    page = [
        "<!doctype html><html lang='it'><head><meta charset='utf-8'/>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'/>",
        "<title>Aggiungi partita (statica)</title>",
        "<style>",
        "body{font-family:system-ui,Segoe UI,Roboto,sans-serif;max-width:980px;margin:24px auto;padding:0 16px;}",
        "input,button,textarea{padding:10px;font-size:16px;}",
        "label{display:block;margin-top:12px;font-weight:600;}",
        ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;}",
        "textarea{width:100%;min-height:160px;}",
        ".hint{color:#555;}",
        "</style></head><body>",
        "<h1>Aggiungi partita (modalità statica)</h1>",
        "<p class='hint'>Su GitHub Pages non esiste backend, quindi non posso salvare nel database. "
        "Qui puoi però generare un JSON/CSV da copiare o scaricare e poi inserirlo nel backend.</p>",
        f"<p><a href='{REPO_BASE}'>← Home</a></p>",
        "<div class='grid'>",
        "<div><label>Player</label><input id='player' placeholder='Nome player'></div>",
        "<div><label>Commander</label><input id='commander' placeholder='Nome commander'></div>",
        "<div><label>Posizione (1..N)</label><input id='position' type='number' min='1' step='1'></div>",
        "<div><label>Note</label><input id='notes' placeholder='(opzionale)'></div>",
        "</div>",
        "<div style='margin-top:16px;display:flex;gap:12px;flex-wrap:wrap;'>",
        "<button id='make_json' type='button'>Genera JSON</button>",
        "<button id='make_csv' type='button'>Genera riga CSV</button>",
        "<button id='download' type='button'>Scarica JSON</button>",
        "</div>",
        "<label style='margin-top:16px;'>Output</label>",
        "<textarea id='out' readonly></textarea>",
        "<script>",
        "function getVal(id){return document.getElementById(id).value.trim();}",
        "function payload(){return {player:getVal('player'), commander:getVal('commander'), position:Number(getVal('position')||0), notes:getVal('notes')};}",
        "function validate(p){if(!p.player||!p.commander||!p.position){alert('Compila almeno Player, Commander e Posizione');return false;}return true;}",
        "document.getElementById('make_json').onclick=()=>{const p=payload();if(!validate(p))return;document.getElementById('out').value=JSON.stringify(p,null,2);};",
        "document.getElementById('make_csv').onclick=()=>{const p=payload();if(!validate(p))return;const esc=s=>'\"'+String(s).replaceAll('\"','\"\"')+'\"';document.getElementById('out').value=[esc(p.player),esc(p.commander),p.position,esc(p.notes)].join(',');};",
        "document.getElementById('download').onclick=()=>{const p=payload();if(!validate(p))return;const blob=new Blob([JSON.stringify(p,null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='new_game_entry.json';a.click();URL.revokeObjectURL(a.href);};",
        "</script>",
        "</body></html>",
    ]
    out_path = OUT_DIR / "add" / "index.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(page), encoding="utf-8")

def write_triplette_page():
    page = [
        "<!doctype html><html lang='it'><head><meta charset='utf-8'/>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'/>",
        "<title>Triplette</title>",
        "<style>",
        "body{font-family:system-ui,Segoe UI,Roboto,sans-serif;max-width:1200px;margin:24px auto;padding:0 16px;}",
        "table{border-collapse:collapse;width:100%;}",
        "th,td{border-bottom:1px solid #eee;padding:10px 8px;text-align:left;}",
        "th{position:sticky;top:0;background:#fff;}",
        "input{padding:10px;font-size:16px;width:320px;max-width:100%;}",
        ".muted{color:#666;}",
        "</style></head><body>",
        f"<p><a href='{REPO_BASE}'>← Home</a></p>",
        "<h1>Triplette</h1>",
        "<p class='muted'>Combinazioni Player – Commander – Bracket con numero di partite.</p>",
        "<input id='q' placeholder='Filtra (player/commander/bracket)…' />",
        "<div style='margin-top:14px;overflow:auto;'>",
        "<table>",
        "<thead><tr><th>Player</th><th>Commander</th><th>Bracket</th><th style='text-align:right;'># Partite</th></tr></thead>",
        "<tbody id='tb'></tbody>",
        "</table></div>",
        "<script>",
        f"const BASE = {repr(REPO_BASE)};",
        "let data = [];",
        "function esc(s){return String(s ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');}",
        "function row(r){",
        "  const br = r.bracket ?? '-';",
        "  return `<tr><td>${esc(r.player)}</td><td>${esc(r.commander)}</td><td>${esc(br)}</td><td style='text-align:right;'>${esc(r.games)}</td></tr>`;",
        "}",
        "function render(){",
        "  const q = document.getElementById('q').value.trim().toLowerCase();",
        "  const tb = document.getElementById('tb');",
        "  const rows = (q ? data.filter(r => (r.player+' '+r.commander+' '+(r.bracket??'')).toLowerCase().includes(q)) : data);",
        "  tb.innerHTML = rows.map(row).join('');",
        "}",
        "fetch(BASE + 'triplette.json').then(r=>r.json()).then(j=>{data=j; render();});",
        "document.getElementById('q').addEventListener('input', render);",
        "</script>",
        "</body></html>",
    ]
    out_path = OUT_DIR / "triplette" / "index.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(page), encoding="utf-8")


def export():
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / ".nojekyll").write_text("", encoding="utf-8")

    client = TestClient(app)

    # pagine base
    for route in BASE_ROUTES:
        r = client.get(route)
        if r.status_code != 200:
            raise RuntimeError(f"GET {route} -> {r.status_code}")
        html = make_consultation_only(r.text)

        if route == "/summary":
            write_page("/", html)         # HOME
            write_page("/summary", html)  # alias
        else:
            write_page(route, html)

    # pagina Partite: route dinamica "/" -> pagina statica "/partite/"
    r = client.get("/")
    if r.status_code != 200:
        raise RuntimeError(f"GET / -> {r.status_code}")
    html = make_consultation_only(r.text)
    write_page("/partite", html)

    # file extra
    for route, filename in EXTRA_FILES:
        r = client.get(route)
        if r.status_code != 200:
            raise RuntimeError(f"GET {route} -> {r.status_code}")
        (OUT_DIR / filename).write_bytes(r.content)

    # triplette: (player, commander, bracket) -> count
    with Session(engine) as session:
        entries = session.exec(select(GameEntry.player, GameEntry.commander, GameEntry.bracket)).all()

    c = Counter((p, cmd, br) for (p, cmd, br) in entries)
    triplette = [
        {"player": p, "commander": cmd, "bracket": br, "games": n}
        for (p, cmd, br), n in c.items()
    ]
    triplette.sort(key=lambda r: (r["player"].lower(), r["commander"].lower(), (r["bracket"] or "")))

    (OUT_DIR / "triplette.json").write_text(
        json.dumps(triplette, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    write_triplette_page()

    # player
    with Session(engine) as session:
        players = sorted(
            {e.player for e in session.exec(select(GameEntry)).all()},
            key=lambda s: s.lower(),
        )

    players_index: list[tuple[str, str]] = []
    for p in players:
        slug = safe_slug(p)
        r = client.get("/player_dashboard", params={"player": p})
        if r.status_code != 200:
            raise RuntimeError(f"GET /player_dashboard?player={p} -> {r.status_code}")
        html = make_consultation_only(r.text)

        out_path = OUT_DIR / "player" / slug / "index.html"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
        players_index.append((p, f"player/{slug}/"))

    # lista player (pagina di servizio)
    players_page = [
        "<!doctype html><html lang='it'><head><meta charset='utf-8'/>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'/>",
        "<title>Players</title>",
        "<style>body{font-family:system-ui,Segoe UI,Roboto,sans-serif;max-width:980px;margin:24px auto;padding:0 16px;} a{display:inline-block;margin:6px 10px 6px 0;}</style>",
        "</head><body>",
        "<h1>Players</h1>",
        f"<p><a href='{REPO_BASE}'>← Home</a> &nbsp;|&nbsp; <a href='{REPO_BASE}player_dashboard/'>Confronta 2 player</a></p>",
        "<div>",
    ]
    for name, href in players_index:
        players_page.append(f"<a href='{REPO_BASE}{href}'>{name}</a>")
    players_page += ["</div></body></html>"]
    (OUT_DIR / "player" / "index.html").parent.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "player" / "index.html").write_text("\n".join(players_page), encoding="utf-8")

    # confronto
    write_player_compare_page(players_index, out_folder="player_dashboard")
    write_player_compare_page(players_index, out_folder="player_compare")  # alias

    # add
    write_add_page()

    print(f"✅ Export completato in: {OUT_DIR.resolve()}")
    print(f"🌐 Base GitHub Pages usata: {REPO_BASE}")


if __name__ == "__main__":
    export()
