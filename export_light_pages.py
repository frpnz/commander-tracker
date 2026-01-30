from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from sqlmodel import Session

from app import engine
from dashboard_data import build_dashboard_dataset
from stats_data import build_stats_dataset


OUT_DIR = Path("docs")
DATA_DIR = OUT_DIR / "data"
ASSETS_DIR = OUT_DIR / "assets"


def _read_base_css() -> str:
    """Best-effort reuse CSS from templates/base.html so Pages matches the app."""
    base = Path("templates") / "base.html"
    if not base.exists():
        return ""
    soup = BeautifulSoup(base.read_text(encoding="utf-8"), "html.parser")
    style = soup.find("style")
    return (style.text or "").strip() if style else ""


INDEX_HTML = """<!doctype html>
<html lang=\"it\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Tempio Tracker (static)</title>
  <link rel=\"stylesheet\" href=\"./assets/style.css\" />
</head>
<body>
  <div class=\"container\">
    <h1>Tempio Tracker</h1>
    <p class=\"muted\">Versione statica (GitHub Pages). I dati arrivano da JSON generati da Python.</p>
    <ul>
      <li><a href=\"./dashboard/\">Dashboard</a></li>
      <li><a href=\"./stats/\">Stats</a></li>
    </ul>
  </div>
</body>
</html>
"""


DASHBOARD_HTML = """<!doctype html>
<html lang=\"it\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Dashboard</title>
  <link rel=\"stylesheet\" href=\"../assets/style.css\" />
  <script src=\"https://cdn.jsdelivr.net/npm/chart.js\"></script>
</head>
<body>
  <div class=\"container\">
    <div class=\"nav\"><a href=\"../\">← Home</a> · <a href=\"../stats/\">Stats</a></div>
    <h1>Dashboard</h1>

    <form id=\"filters\" class=\"panel\">
      <div class=\"grid\">
        <label>Player
          <select id=\"player\"></select>
        </label>
        <label>Min partite (player)
          <input id=\"min_pg\" type=\"number\" min=\"1\" step=\"1\" value=\"3\" />
        </label>
        <label>Min partite (pair)
          <input id=\"min_pair\" type=\"number\" min=\"1\" step=\"1\" value=\"3\" />
        </label>
        <label>Min partite (commander)
          <input id=\"min_cmd\" type=\"number\" min=\"1\" step=\"1\" value=\"3\" />
        </label>
        <label>Top players
          <input id=\"top_players\" type=\"number\" min=\"1\" max=\"50\" step=\"1\" value=\"10\" />
        </label>
        <label>Top pair
          <input id=\"top_pairs\" type=\"number\" min=\"1\" max=\"50\" step=\"1\" value=\"10\" />
        </label>
        <label>Top commander
          <input id=\"top_cmd\" type=\"number\" min=\"1\" max=\"50\" step=\"1\" value=\"10\" />
        </label>
      </div>
      <button class=\"btn\" type=\"submit\">Applica</button>
    </form>

    <div class=\"grid2\">
      <div class=\"panel\">
        <h2>Winrate player (Top)</h2>
        <canvas id=\"playerWinrateChart\"></canvas>
      </div>
      <div class=\"panel\">
        <h2>Winrate vs Partite</h2>
        <canvas id=\"scatterChart\"></canvas>
      </div>
      <div class=\"panel\">
        <h2>Winrate pair (Top)</h2>
        <canvas id=\"pairWinrateChart\"></canvas>
      </div>
      <div class=\"panel\">
        <h2>Winrate commander (Top)</h2>
        <canvas id=\"commanderWinrateChart\"></canvas>
      </div>
      <div class=\"panel\">
        <h2>Pod size distribution</h2>
        <canvas id=\"podChart\"></canvas>
      </div>
      <div class=\"panel\">
        <h2>Trend winrate cumulativa</h2>
        <canvas id=\"trendChart\"></canvas>
      </div>
    </div>

    <p class=\"muted\" id=\"buildInfo\"></p>
  </div>

  <script src=\"../assets/dashboard.js\"></script>
</body>
</html>
"""


STATS_HTML = """<!doctype html>
<html lang=\"it\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Stats</title>
  <link rel=\"stylesheet\" href=\"../assets/style.css\" />
</head>
<body>
  <div class=\"container\">
    <div class=\"nav\"><a href=\"../\">← Home</a> · <a href=\"../dashboard/\">Dashboard</a></div>
    <h1>Stats</h1>

    <form id=\"controls\" class=\"panel\">
      <div class=\"grid\">
        <label>Pod size
          <select id=\"podSize\"></select>
        </label>
        <label>Top triples
          <input id=\"topTriples\" type=\"number\" min=\"10\" max=\"500\" step=\"1\" value=\"50\" />
        </label>
        <label>Max unique (hygiene)
          <input id=\"maxUnique\" type=\"number\" min=\"10\" max=\"5000\" step=\"10\" value=\"200\" />
        </label>
      </div>
      <button class=\"btn\" type=\"submit\">Applica</button>
    </form>

    <div class=\"panel\">
      <h2>Overall: players</h2>
      <div id=\"tblPlayers\"></div>
    </div>
    <div class=\"panel\">
      <h2>Overall: player + commander</h2>
      <div id=\"tblPairs\"></div>
    </div>

    <div class=\"panel\">
      <h2>Per pod size: players</h2>
      <div id=\"tblPlayersBySize\"></div>
    </div>
    <div class=\"panel\">
      <h2>Per pod size: player + commander</h2>
      <div id=\"tblPairsBySize\"></div>
    </div>

    <div class=\"panel\">
      <h2>Bracket</h2>
      <div class=\"grid2\">
        <div>
          <h3>Entries per bracket</h3>
          <div id=\"tblBracketEntries\"></div>
        </div>
        <div>
          <h3>Winner bracket counts</h3>
          <div id=\"tblBracketWinners\"></div>
        </div>
      </div>
      <h3>Winrate per bracket</h3>
      <div id=\"tblBracketWinrate\"></div>
    </div>

    <div class=\"panel\">
      <h2>Triples (player, commander, bracket)</h2>
      <div id=\"tblTriples\"></div>
    </div>

    <div class=\"panel\">
      <h2>Unique triples (Commander, Player, Bracket)</h2>
      <div id=\"tblUniqueTriples\"></div>
    </div>

    <p class=\"muted\" id=\"buildInfo\"></p>
  </div>

  <script src=\"../assets/stats.js\"></script>
</body>
</html>
"""


STATS_JS = r"""
let DATA = null;

const state = {
  podSize: "__all__",
  topTriples: 50,
  maxUnique: 200,
};

function qs(sel){ return document.querySelector(sel); }

function readQuery(){
  const url = new URL(window.location.href);
  const p = url.searchParams;
  if (p.get("pod")) state.podSize = p.get("pod");
  if (p.get("top")) state.topTriples = parseInt(p.get("top"), 10) || state.topTriples;
  if (p.get("max")) state.maxUnique = parseInt(p.get("max"), 10) || state.maxUnique;
  state.topTriples = Math.max(10, Math.min(500, state.topTriples));
  state.maxUnique = Math.max(10, Math.min(5000, state.maxUnique));
}

function writeQuery(){
  const url = new URL(window.location.href);
  url.searchParams.set("pod", state.podSize);
  url.searchParams.set("top", String(state.topTriples));
  url.searchParams.set("max", String(state.maxUnique));
  window.history.replaceState({}, "", url);
}

function escapeHtml(s){
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function fmt(n, digits=1){
  if (n === null || n === undefined) return "";
  const x = Number(n);
  if (Number.isNaN(x)) return String(n);
  return x.toFixed(digits);
}

function table(el, rows, cols){
  // cols: [{key, label, fmt?}]
  if (!rows || rows.length === 0) { el.innerHTML = "<p class='muted'>n/a</p>"; return; }
  const thead = cols.map(c => `<th>${escapeHtml(c.label)}</th>`).join("");
  const tbody = rows.map(r => {
    const tds = cols.map(c => {
      const v = r[c.key];
      const vv = c.fmt ? c.fmt(v) : v;
      return `<td>${escapeHtml(vv)}</td>`;
    }).join("");
    return `<tr>${tds}</tr>`;
  }).join("\n");
  el.innerHTML = `<div class='tablewrap'><table><thead><tr>${thead}</tr></thead><tbody>${tbody}</tbody></table></div>`;
}

function kvTable(el, obj){
  const rows = Object.entries(obj || {}).map(([k,v]) => ({k, v}));
  rows.sort((a,b) => {
    const ak = a.k === "n/a" ? "~" : a.k;
    const bk = b.k === "n/a" ? "~" : b.k;
    return ak.localeCompare(bk);
  });
  table(el, rows, [
    {key: "k", label: "bucket"},
    {key: "v", label: "count", fmt: (x) => String(x)}
  ]);
}

function init(){
  // pod sizes
  const sel = qs("#podSize");
  sel.innerHTML = "";
  const optAll = document.createElement("option");
  optAll.value = "__all__";
  optAll.textContent = "Tutti";
  sel.appendChild(optAll);
  for (const n of (DATA.sizes || [])) {
    const opt = document.createElement("option");
    opt.value = String(n);
    opt.textContent = String(n);
    sel.appendChild(opt);
  }

  // defaults
  sel.value = state.podSize;
  qs("#topTriples").value = state.topTriples;
  qs("#maxUnique").value = state.maxUnique;

  qs("#controls").addEventListener("submit", (ev) => {
    ev.preventDefault();
    state.podSize = qs("#podSize").value || "__all__";
    state.topTriples = parseInt(qs("#topTriples").value, 10) || state.topTriples;
    state.maxUnique = parseInt(qs("#maxUnique").value, 10) || state.maxUnique;
    state.topTriples = Math.max(10, Math.min(500, state.topTriples));
    state.maxUnique = Math.max(10, Math.min(5000, state.maxUnique));
    writeQuery();
    render();
  });
}

function render(){
  if (!DATA) return;

  table(qs("#tblPlayers"), DATA.player_rows, [
    {key: "player", label: "player"},
    {key: "games", label: "games", fmt: (x) => String(x)},
    {key: "wins", label: "wins", fmt: (x) => String(x)},
    {key: "winrate", label: "winrate %", fmt: (x) => fmt(x, 1)},
    {key: "unique_commanders", label: "unique commanders", fmt: (x) => String(x)},
    {key: "top_commander", label: "top commander"},
    {key: "top_commander_games", label: "top cmd games", fmt: (x) => String(x)},
  ]);

  table(qs("#tblPairs"), DATA.pair_rows, [
    {key: "player", label: "player"},
    {key: "commander", label: "commander"},
    {key: "games", label: "games", fmt: (x) => String(x)},
    {key: "wins", label: "wins", fmt: (x) => String(x)},
    {key: "winrate", label: "winrate %", fmt: (x) => fmt(x, 1)},
  ]);

  const psKey = state.podSize;
  const playersBy = (psKey === "__all__") ? null : (DATA.player_by_size_tables || {})[psKey];
  const pairsBy = (psKey === "__all__") ? null : (DATA.pair_by_size_tables || {})[psKey];
  table(qs("#tblPlayersBySize"), playersBy, [
    {key: "player", label: "player"},
    {key: "games", label: "games", fmt: (x) => String(x)},
    {key: "wins", label: "wins", fmt: (x) => String(x)},
    {key: "winrate", label: "winrate %", fmt: (x) => fmt(x, 1)},
  ]);
  table(qs("#tblPairsBySize"), pairsBy, [
    {key: "player", label: "player"},
    {key: "commander", label: "commander"},
    {key: "games", label: "games", fmt: (x) => String(x)},
    {key: "wins", label: "wins", fmt: (x) => String(x)},
    {key: "winrate", label: "winrate %", fmt: (x) => fmt(x, 1)},
  ]);

  kvTable(qs("#tblBracketEntries"), DATA.bracket_entry_counts);
  kvTable(qs("#tblBracketWinners"), DATA.bracket_winner_counts);
  table(qs("#tblBracketWinrate"), DATA.bracket_rows, [
    {key: "bracket", label: "bracket"},
    {key: "games", label: "games", fmt: (x) => String(x)},
    {key: "wins", label: "wins", fmt: (x) => String(x)},
    {key: "winrate", label: "winrate %", fmt: (x) => fmt(x, 1)},
  ]);

  const triples = (DATA.triple_rows || []).slice(0, state.topTriples);
  table(qs("#tblTriples"), triples, [
    {key: "player", label: "player"},
    {key: "commander", label: "commander"},
    {key: "bracket", label: "bracket"},
    {key: "games", label: "games", fmt: (x) => String(x)},
    {key: "wins", label: "wins", fmt: (x) => String(x)},
    {key: "winrate", label: "winrate %", fmt: (x) => fmt(x, 1)},
    {key: "weighted_wr", label: "weighted %", fmt: (x) => fmt(x, 1)},
    {key: "bpi", label: "bpi", fmt: (x) => x === null ? "" : fmt(x, 2)},
    {key: "bpi_label", label: "bpi label"},
    {key: "delta_coverage", label: "coverage %", fmt: (x) => x === null ? "" : fmt(x, 1)},
    {key: "avg_table_bracket", label: "avg table", fmt: (x) => x === null ? "" : fmt(x, 2)},
  ]);

  const uniques = (DATA.unique_triples_rows || []).slice(0, state.maxUnique);
  table(qs("#tblUniqueTriples"), uniques, [
    {key: "commander", label: "commander"},
    {key: "player", label: "player"},
    {key: "bracket", label: "bracket"},
    {key: "entries", label: "entries", fmt: (x) => String(x)},
  ]);

  qs("#buildInfo").textContent = `Build: ${DATA.generated_at || ""}`;
}

readQuery();

fetch("../data/stats.v1.json")
  .then(r => r.json())
  .then(j => { DATA = j; init(); render(); })
  .catch(err => {
    console.error(err);
    qs("#buildInfo").textContent = "Errore nel caricare stats.v1.json";
  });
"""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    # CSS
    base_css = _read_base_css()
    extra_css = """
    .container { max-width: 1100px; margin: 0 auto; padding: 18px; }
    .nav { margin-bottom: 12px; }
    .muted { opacity: 0.75; }
    .panel { border: 1px solid rgba(127,127,127,0.25); border-radius: 10px; padding: 12px; margin: 12px 0; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; align-items: end; }
    .grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 12px; }
    label { display: grid; gap: 6px; font-size: 14px; }
    input, select { padding: 8px; border-radius: 8px; border: 1px solid rgba(127,127,127,0.35); }
    .btn { padding: 9px 12px; border-radius: 10px; border: 1px solid rgba(127,127,127,0.35); cursor: pointer; }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    th, td { padding: 8px; border-bottom: 1px solid rgba(127,127,127,0.25); text-align: left; }
    th { position: sticky; top: 0; background: rgba(250,250,250,0.9); }
    .tablewrap { max-height: 420px; overflow: auto; border-radius: 10px; }
    """
    _write(ASSETS_DIR / "style.css", (base_css + "\n\n" + extra_css).strip() + "\n")

    # Pages
    _write(OUT_DIR / "index.html", INDEX_HTML)
    _write(OUT_DIR / "dashboard" / "index.html", DASHBOARD_HTML)
    _write(OUT_DIR / "stats" / "index.html", STATS_HTML)

    # JS assets
    # Reuse the existing dashboard JS from export_dashboard_light.py for now.
    from export_dashboard_light import DASHBOARD_JS  # noqa

    _write(ASSETS_DIR / "dashboard.js", DASHBOARD_JS.strip() + "\n")
    _write(ASSETS_DIR / "stats.js", STATS_JS.strip() + "\n")

    # Data
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with Session(engine) as session:
        dash = build_dashboard_dataset(session)
        stats = build_stats_dataset(session)

    dash["generated_at"] = now
    stats["generated_at"] = now

    (DATA_DIR / "dashboard.v1.json").write_text(json.dumps(dash, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_DIR / "stats.v1.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "generated_at": now,
        "datasets": {
            "dashboard": {"schema": dash.get("schema"), "path": "data/dashboard.v1.json"},
            "stats": {"schema": stats.get("schema"), "path": "data/stats.v1.json"},
        },
    }
    (DATA_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Wrote:")
    print(" - docs/index.html")
    print(" - docs/dashboard/index.html")
    print(" - docs/stats/index.html")
    print(" - docs/data/dashboard.v1.json")
    print(" - docs/data/stats.v1.json")
    print(" - docs/data/manifest.json")


if __name__ == "__main__":
    main()
