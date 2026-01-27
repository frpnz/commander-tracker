import os
import re
import shutil
from pathlib import Path
from urllib.parse import quote

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

# Importa la tua app e (opzionale) il DB per ricavare i player
from app import app, engine, GameEntry
from sqlmodel import Session, select


OUT_DIR = Path("docs")  # GitHub Pages può servire /docs
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


def safe_slug(s: str) -> str:
    """
    Slug semplice + URL-safe per nomi player.
    Manteniamo anche quote() per sicurezza su caratteri strani.
    """
    s = s.strip()
    if not s:
        return "unknown"
    # sostituisci spazi con underscore e rimuovi caratteri "problematici"
    s2 = re.sub(r"\s+", "_", s)
    s2 = re.sub(r"[^A-Za-z0-9_\-\.]", "", s2)
    if not s2:
        s2 = "player"
    return quote(s2)


def make_consultation_only(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # 1) Rimuovi input (form, button, textarea, select, input)
    for tag in soup.find_all(["form", "button", "textarea", "select", "input"]):
        tag.decompose()

    # 2) Riscrivi link assoluti "/xyz" -> "xyz/"
    #    Nota: GitHub Pages vive sotto /<repo>/, quindi i link assoluti si rompono.
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()

        # lascia stare ancore, mailto, http(s)
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("http://") or href.startswith("https://"):
            continue

        # converti href="/"
        if href == "/":
            a["href"] = "./"
            continue

        # converti href="/qualcosa" -> "qualcosa/"
        if href.startswith("/"):
            # elimina lo slash iniziale
            href2 = href[1:]

            # se è un file (es. export.csv) lo lasciamo file
            if href2.endswith(".csv") or href2.endswith(".json") or href2.endswith(".pdf") or href2.endswith(".html"):
                a["href"] = href2
            else:
                # pagine -> cartella con trailing slash
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
        players = sorted({e.player for e in session.exec(select(GameEntry)).all()}, key=lambda s: s.lower())

    players_index = []
    for p in players:
        slug = safe_slug(p)
        url = f"/player/{slug}"
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
        "<title>Players</title>",
        "<style>body{font-family:system-ui,Segoe UI,Roboto,sans-serif;max-width:980px;margin:24px auto;padding:0 16px;} a{display:inline-block;margin:6px 10px 6px 0;}</style>",
        "</head><body>",
        "<h1>Player Dashboard</h1>",
        "<p><a href='../'>← Home</a></p>",
        "<div>",
    ]
    for name, href in players_index:
        players_page.append(f"<a href='../{href}'>{name}</a>")
    players_page += ["</div></body></html>"]

    (OUT_DIR / "player" / "index.html").write_text("\n".join(players_page), encoding="utf-8")

    print(f"✅ Export completato in: {OUT_DIR.resolve()}")


if __name__ == "__main__":
    export()
