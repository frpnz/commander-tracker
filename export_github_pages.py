import re
import shutil
import posixpath
from pathlib import Path
from urllib.parse import quote

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

# Importa la tua app e (opzionale) il DB per ricavare i player
from app import app, engine, GameEntry
from sqlmodel import Session, select


# === CONFIG ===
OUT_DIR = Path("docs")  # GitHub Pages può servire /docs

# Nome repo GitHub (quello dopo https://<user>.github.io/<repo>/ )
REPO_NAME = "commander-tracker"
REPO_BASE = f"/{REPO_NAME}/"

BASE_PAGES = [
    ("/", "index"),  # -> docs/index.html
    ("/stats", "stats"),
    ("/dashboard_mini", "dashboard"),
    ("/dashboard_mini_bracket", "dashboard_bracket"),
    ("/summary", "summary"),
    ("/commander_brackets", "commander_brackets"),
]

# anche questi possono essere utili su Pages come file scaricabili
EXTRA_FILES = [
    ("/export.csv", "export.csv"),
    ("/stats.json", "stats.json"),
]

# estensioni "file" (non pagine)
FILE_EXTS = (
    ".csv", ".json", ".pdf", ".html", ".txt",
    ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
    ".woff", ".woff2", ".ttf", ".eot", ".map"
)

# Link che vogliamo disabilitare nella versione statica (per evitare 404)
# Nota: i PDF nella tua app sono tipo /summary.pdf -> verranno disabilitati qui.
DISABLED_PREFIXES = (
    "edit",
    "match_edit",
    "delete",
    "pdf",          # /pdf/...
    "export_pdf",
    "generate_pdf",
)
DISABLED_FILE_EXTS = (".pdf",)


def safe_slug(s: str) -> str:
    """Slug semplice + URL-safe per nomi player."""
    s = s.strip()
    if not s:
        return "unknown"
    s2 = re.sub(r"\s+", "_", s)
    s2 = re.sub(r"[^A-Za-z0-9_\-\.]", "", s2)
    if not s2:
        s2 = "player"
    return quote(s2)


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
    """Se già include /<repo>/..., togliamolo per normalizzare."""
    if path.startswith(REPO_BASE):
        return path[len(REPO_BASE):]
    if path.startswith("/" + REPO_NAME + "/"):
        return path[len("/" + REPO_NAME + "/"):]
    return path


def _normalize_internal_path(raw: str) -> str:
    """
    Normalizza un path interno (href) in forma "pulita" (senza query/fragment,
    senza / iniziale, senza repo base).
    """
    href = (raw or "").strip()
    if _is_external(href):
        return ""

    # togli fragment/query
    href = href.split("#", 1)[0].split("?", 1)[0].strip()

    # normalizza repo base
    if href.startswith(REPO_BASE):
        href = href[len(REPO_BASE):]
    elif href.startswith("/" + REPO_NAME + "/"):
        href = href[len("/" + REPO_NAME + "/"):]

    href = href.lstrip("/")

    # togli ./ e ../ in modo semplice
    while href.startswith("./"):
        href = href[2:]
    while href.startswith("../"):
        href = href[3:]

    href = posixpath.normpath(href).lstrip(".").lstrip("/")
    return href


def _is_disabled_path(raw: str) -> bool:
    """
    True se il link punta a funzionalità non supportate in statico (edit/pdf ecc.).
    """
    p = _normalize_internal_path(raw)
    if not p:
        return False

    low = p.lower()

    # disabilita tutti i .pdf (es: summary.pdf)
    if low.endswith(DISABLED_FILE_EXTS):
        return True

    for pref in DISABLED_PREFIXES:
        pref = pref.lower()
        if low == pref or low.startswith(pref + "/"):
            return True

    return False


def _onclick_contains_disabled(oc: str) -> bool:
    """
    Intercetta navigazioni via onclick tipo:
    window.location='/summary.pdf'
    location.href="edit/123"
    """
    if not oc:
        return False
    s = oc.lower()

    # se contiene un .pdf in qualunque forma, disabilita
    if ".pdf" in s:
        return True

    # se contiene riferimenti a route disabilitate
    for pref in DISABLED_PREFIXES:
        if pref.lower() in s:
            return True

    # anche "summary.pdf" è comune
    if "summary.pdf" in s:
        return True

    return False


def _to_pages_url(raw: str) -> str:
    """
    Converte qualsiasi URL interno (assoluto o relativo) in:
    - pagine:  /<repo>/qualcosa/
    - file:    /<repo>/qualcosa.ext

    In più: forza route dinamiche su equivalenti statici:
    - player_dashboard?...  -> /<repo>/player_dashboard/
    - add                  -> /<repo>/add/
    """
    href = (raw or "").strip()

    if href in ("", ".", "./", "/"):
        return REPO_BASE

    if _is_external(href):
        return href

    # separa fragment e query
    frag = ""
    if "#" in href:
        href, frag_ = href.split("#", 1)
        frag = "#" + frag_

    query = ""
    if "?" in href:
        href, q_ = href.split("?", 1)
        query = "?" + q_

    # normalizza: rimuovi repo base se già presente
    href = _strip_repo_base(href)

    # rendi "pulito": rimuovi leading /, ./ e ../
    href = href.lstrip("/")
    while href.startswith("./"):
        href = href[2:]
    while href.startswith("../"):
        href = href[3:]

    href = posixpath.normpath(href).lstrip(".")
    if href in ("", "/"):
        return REPO_BASE + frag

    # --- ROUTE DINAMICHE -> STATICHE ---
    if href == "player_dashboard" or href.startswith("player_dashboard/"):
        # ignora query (anche se c'era ?player=...) e manda al selettore
        return f"{REPO_BASE}player_dashboard/{frag}"

    if href == "add" or href.startswith("add/"):
        return f"{REPO_BASE}add/{frag}"

    lower = href.lower()

    # file: niente slash finale
    if lower.endswith(FILE_EXTS):
        return f"{REPO_BASE}{href}{query}{frag}"

    # pagina: forziamo trailing slash
    href = href.strip("/")
    return f"{REPO_BASE}{href}/{query}{frag}"


def make_consultation_only(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # 1) consultazione-only: rimuovi input (nelle pagine esportate dal backend)
    for tag in soup.find_all(["form", "button", "textarea", "select", "input"]):
        tag.decompose()

    # CSS per link disabilitati
    head = soup.head
    if head is not None:
        style = soup.new_tag("style")
        style.string = ".disabled-link{pointer-events:none;opacity:.45;cursor:not-allowed;text-decoration:none}"
        head.append(style)

        # Disabilita Export HTML quando la pagina è embeddeda (es. confronto side-by-side)
        style2 = soup.new_tag("style")
        style2.string = ".embedded .export-html{pointer-events:none;opacity:.45;cursor:not-allowed;text-decoration:none}"
        head.append(style2)

        script = soup.new_tag("script")
        script.string = "if (window.self !== window.top) { document.documentElement.classList.add(\"embedded\"); }"
        head.append(script)

    # 2) disabilita anche navigazione via onclick verso pdf/edit
    for tag in soup.find_all(True):
        if tag.has_attr("onclick") and _onclick_contains_disabled(tag.get("onclick", "")):
            # se è un <a>, lo rendiamo visivamente disabilitato
            if tag.name == "a":
                tag["href"] = "#"
                tag["title"] = "Non disponibile nella versione statica"
                cls = tag.get("class", [])
                if "disabled-link" not in cls:
                    cls.append("disabled-link")
                tag["class"] = cls
            # rimuovi il comportamento
            del tag["onclick"]

    # 3) riscrivi href (e disabilita pdf/edit)
    for a in soup.find_all("a", href=True):
        raw = a["href"]

        # Marca i link di Export HTML (li disabilitiamo solo quando la pagina è in iframe)
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

    # 4) riscrivi anche risorse statiche (css/js/img ecc.)
    for link in soup.find_all("link", href=True):
        link["href"] = _to_pages_url(link["href"])

    for script in soup.find_all("script", src=True):
        script["src"] = _to_pages_url(script["src"])

    for tag in soup.find_all(["img", "source", "iframe"], src=True):
        tag["src"] = _to_pages_url(tag["src"])

    return str(soup)


def write_page(path_key: str, html: str):
    """Salva pagina in cartelle con index.html."""
    if path_key == "/":
        out_path = OUT_DIR / "index.html"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
        return

    folder = path_key.strip("/").split("?")[0]
    out_path = OUT_DIR / folder / "index.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")


def write_player_dashboard_selector(players_index: list[tuple[str, str]]):
    """Crea /player_dashboard/ con una select (client-side) che porta a /player/<slug>/."""
    page = [
        "<!doctype html><html lang='it'><head><meta charset='utf-8'/>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'/>",
        "<title>Player Dashboard</title>",
        "<style>",
        "body{font-family:system-ui,Segoe UI,Roboto,sans-serif;max-width:980px;margin:24px auto;padding:0 16px;}",
        "select{padding:10px;font-size:16px;min-width:280px;}",
        ".row{display:flex;gap:12px;align-items:center;flex-wrap:wrap;}",
        "</style></head><body>",
        "<h1>Player Dashboard</h1>",
        f"<p><a href='{REPO_BASE}'>← Home</a> &nbsp;|&nbsp; <a href='{REPO_BASE}player/'>Lista player</a></p>",
        "<div class='row'>",
        "<label for='p'>Seleziona player:</label>",
        "<select id='p'><option value=''>— scegli —</option>",
    ]
    for name, href in players_index:
        page.append(f"<option value='{REPO_BASE}{href}'>{name}</option>")

    page += [
        "</select>",
        "</div>",
        "<script>",
        "  const sel = document.getElementById('p');",
        "  sel.addEventListener('change', () => {",
        "    const v = sel.value;",
        "    if (v) window.location.href = v;",
        "  });",
        "</script>",
        "</body></html>",
    ]

    out_path = OUT_DIR / "player_dashboard" / "index.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(page), encoding="utf-8")


def write_add_page():
    """Crea /add/ statico: genera JSON o CSV + download (client-side)."""
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
        "function payload(){",
        "  return {",
        "    player: getVal('player'),",
        "    commander: getVal('commander'),",
        "    position: Number(getVal('position') || 0),",
        "    notes: getVal('notes')",
        "  };",
        "}",
        "function validate(p){",
        "  if(!p.player || !p.commander || !p.position){",
        "    alert('Compila almeno Player, Commander e Posizione');",
        "    return false;",
        "  }",
        "  return true;",
        "}",
        "document.getElementById('make_json').onclick = () => {",
        "  const p = payload(); if(!validate(p)) return;",
        "  document.getElementById('out').value = JSON.stringify(p, null, 2);",
        "};",
        "document.getElementById('make_csv').onclick = () => {",
        "  const p = payload(); if(!validate(p)) return;",
        "  const esc = (s)=>('\"'+String(s).replaceAll('\"','\"\"')+'\"');",
        "  document.getElementById('out').value = [esc(p.player),esc(p.commander),p.position,esc(p.notes)].join(',');",
        "};",
        "document.getElementById('download').onclick = () => {",
        "  const p = payload(); if(!validate(p)) return;",
        "  const blob = new Blob([JSON.stringify(p, null, 2)], {type:'application/json'});",
        "  const a = document.createElement('a');",
        "  a.href = URL.createObjectURL(blob);",
        "  a.download = 'new_game_entry.json';",
        "  a.click();",
        "  URL.revokeObjectURL(a.href);",
        "};",
        "</script>",
        "</body></html>",
    ]

    out_path = OUT_DIR / "add" / "index.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(page), encoding="utf-8")


def export():
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # evita che GitHub Pages/Jekyll tocchi cartelle con underscore ecc.
    (OUT_DIR / ".nojekyll").write_text("", encoding="utf-8")

    client = TestClient(app)

    # --- esporta pagine base ---
    for route, _name in BASE_PAGES:
        r = client.get(route)
        if r.status_code != 200:
            raise RuntimeError(f"GET {route} -> {r.status_code}")
        html = make_consultation_only(r.text)
        write_page(route, html)

    # --- esporta files (csv/json) ---
    for route, filename in EXTRA_FILES:
        r = client.get(route)
        if r.status_code != 200:
            raise RuntimeError(f"GET {route} -> {r.status_code}")
        (OUT_DIR / filename).write_bytes(r.content)

    # --- esporta player_dashboard per ogni player (pagine statiche) ---
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

    # --- crea una pagina indice players cliccabile ---
    players_page = [
        "<!doctype html><html lang='it'><head><meta charset='utf-8'/>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'/>",
        "<title>Players</title>",
        "<style>body{font-family:system-ui,Segoe UI,Roboto,sans-serif;max-width:980px;margin:24px auto;padding:0 16px;} a{display:inline-block;margin:6px 10px 6px 0;}</style>",
        "</head><body>",
        "<h1>Player Dashboard</h1>",
        f"<p><a href='{REPO_BASE}'>← Home</a> &nbsp;|&nbsp; <a href='{REPO_BASE}player_dashboard/'>Selettore player</a></p>",
        "<div>",
    ]
    for name, href in players_index:
        players_page.append(f"<a href='{REPO_BASE}{href}'>{name}</a>")
    players_page += ["</div></body></html>"]
    (OUT_DIR / "player" / "index.html").write_text("\n".join(players_page), encoding="utf-8")

    # --- crea /player_dashboard/ con select ---
    write_player_dashboard_selector(players_index)

    # --- crea /add/ statico ---
    write_add_page()

    print(f"✅ Export completato in: {OUT_DIR.resolve()}")
    print(f"🌐 Base GitHub Pages usata: {REPO_BASE}")


if __name__ == "__main__":
    export()
