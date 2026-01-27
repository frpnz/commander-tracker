import re
import shutil
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
REPO_BASE = f"/{REPO_NAME}/"  # usato nel tag <base>

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

FILE_EXTS = (".csv", ".json", ".pdf", ".html", ".txt")


def safe_slug(s: str) -> str:
    """
    Slug semplice + URL-safe per nomi player.
    Manteniamo anche quote() per sicurezza su caratteri strani.
    """
    s = s.strip()
    if not s:
        return "unknown"
    s2 = re.sub(r"\s+", "_", s)
    s2 = re.sub(r"[^A-Za-z0-9_\-\.]", "", s2)
    if not s2:
        s2 = "player"
    return quote(s2)


def ensure_base_tag(soup: BeautifulSoup) -> None:
    """
    Inietta <base href="/<repo>/"> nel <head>, così tutti i link relativi
    vengono risolti correttamente su GitHub Pages e NON diventano /summary/summary/.
    """
    # prova a trovare/creare <html> e <head>
    html_tag = soup.html
    if html_tag is None:
        html_tag = soup.new_tag("html")
        # se c’è del contenuto, inglobalo
        for child in list(soup.contents):
            html_tag.append(child.extract())
        soup.append(html_tag)

    head = soup.head
    if head is None:
        head = soup.new_tag("head")
        html_tag.insert(0, head)

    # se già presente, aggiornalo; altrimenti inseriscilo come primo elemento del head
    base = head.find("base")
    if base is None:
        base = soup.new_tag("base", href=REPO_BASE)
        head.insert(0, base)
    else:
        base["href"] = REPO_BASE


def make_consultation_only(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # 0) aggiungi <base href="/repo/"> per fixare link relativi su Pages
    ensure_base_tag(soup)

    # 1) Rimuovi input (form, button, textarea, select, input)
    for tag in soup.find_all(["form", "button", "textarea", "select", "input"]):
        tag.decompose()

    # 2) Riscrivi link assoluti "/xyz" -> "xyz/" o "file.ext"
    #    Con <base>, "xyz/" punta sempre a /<repo>/xyz/
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()

        # lascia stare ancore, mailto, http(s)
        if (
            href.startswith("#")
            or href.startswith("mailto:")
            or href.startswith("http://")
            or href.startswith("https://")
        ):
            continue

        # converti href="/" (home)
        if href == "/":
            a["href"] = "./"
            continue

        # converti href="/qualcosa" -> "qualcosa/"
        if href.startswith("/"):
            href2 = href[1:]  # togli lo slash iniziale

            # file -> lascia come file (export.csv, stats.json, ecc.)
            if href2.lower().endswith(FILE_EXTS):
                a["href"] = href2
            else:
                # pagina -> trailing slash
                a["href"] = href2.rstrip("/") + "/"

    return str(soup)


def write_page(path_key: str, html: str):
    """
    Salva pagina in:
    - "/" -> docs/index.html
    - "/stats" -> docs/stats/index.html
    """
    if path_key == "/":
        out_path = OUT_DIR / "index.html"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
        return

    folder = path_key.strip("/").split("?")[0]
    out_path = OUT_DIR / folder / "index.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")


def export():
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

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

    # --- esporta player_dashboard per ogni player (senza input) ---
    with Session(engine) as session:
        players = sorted(
            {e.player for e in session.exec(select(GameEntry)).all()},
            key=lambda s: s.lower(),
        )

    players_index = []
    for p in players:
        slug = safe_slug(p)

        # chiama la route con querystring originale
        r = client.get("/player_dashboard", params={"player": p})
        if r.status_code != 200:
            raise RuntimeError(f"GET /player_dashboard?player={p} -> {r.status_code}")
        html = make_consultation_only(r.text)

        # salva in docs/player/<slug>/index.html
        out_path = OUT_DIR / "player" / slug / "index.html"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")

        players_index.append((p, f"player/{slug}/"))

    # --- crea una pagina indice players cliccabile ---
    players_page = [
        "<!doctype html><html lang='it'><head><meta charset='utf-8'/>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'/>",
        f"<base href='{REPO_BASE}'>",
        "<title>Players</title>",
        "<style>body{font-family:system-ui,Segoe UI,Roboto,sans-serif;max-width:980px;margin:24px auto;padding:0 16px;} a{display:inline-block;margin:6px 10px 6px 0;}</style>",
        "</head><body>",
        "<h1>Player Dashboard</h1>",
        "<p><a href='./'>← Home</a></p>",
        "<div>",
    ]
    for name, href in players_index:
        players_page.append(f"<a href='{href}'>{name}</a>")
    players_page += ["</div></body></html>"]

    (OUT_DIR / "player" / "index.html").write_text("\n".join(players_page), encoding="utf-8")

    print(f"✅ Export completato in: {OUT_DIR.resolve()}")
    print(f"🌐 Base GitHub Pages usata: {REPO_BASE}")


if __name__ == "__main__":
    export()
