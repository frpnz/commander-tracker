from __future__ import annotations

import json
from pathlib import Path

from bs4 import BeautifulSoup
from sqlmodel import Session

from app import engine
from dashboard_data import build_dashboard_dataset


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


DASHBOARD_JS = r"""
// Dashboard (GitHub Pages) - data-first rendering
// - Loads docs/data/dashboard.v1.json
// - Lets the user tweak view params client-side (min games, top N, selected player)

let DATA = null;

const state = {
  player: "__all__",
  min_pg: 3,
  min_pair: 3,
  min_cmd: 3,
  top_players: 10,
  top_pairs: 10,
  top_cmd: 10,
};

function qs(sel){ return document.querySelector(sel); }

function readQueryIntoState() {
  const url = new URL(window.location.href);
  const p = url.searchParams;
  if (p.get("player")) state.player = p.get("player");

  for (const k of ["min_pg","min_pair","min_cmd","top_players","top_pairs","top_cmd"]) {
    if (p.get(k) !== null) {
      const v = parseInt(p.get(k), 10);
      if (!Number.isNaN(v)) state[k] = v;
    }
  }

  // clamp
  state.min_pg = Math.max(1, state.min_pg);
  state.min_pair = Math.max(1, state.min_pair);
  state.min_cmd = Math.max(1, state.min_cmd);

  state.top_players = Math.max(1, Math.min(50, state.top_players));
  state.top_pairs = Math.max(1, Math.min(50, state.top_pairs));
  state.top_cmd = Math.max(1, Math.min(50, state.top_cmd));
}

function writeStateToQuery() {
  const url = new URL(window.location.href);
  const p = url.searchParams;
  p.set("player", state.player);
  for (const k of ["min_pg","min_pair","min_cmd","top_players","top_pairs","top_cmd"]) {
    p.set(k, String(state[k]));
  }
  // no reload
  window.history.replaceState({}, "", url);
}

function initForm() {
  // player select
  const sel = qs("#player");
  sel.innerHTML = "";
  const optAll = document.createElement("option");
  optAll.value = "__all__";
  optAll.textContent = "Tutti i player";
  sel.appendChild(optAll);

  for (const p of DATA.dimensions.players) {
    const opt = document.createElement("option");
    opt.value = p;
    opt.textContent = p;
    sel.appendChild(opt);
  }

  // set defaults
  sel.value = state.player;
  qs("#min_pg").value = state.min_pg;
  qs("#min_pair").value = state.min_pair;
  qs("#min_cmd").value = state.min_cmd;
  qs("#top_players").value = state.top_players;
  qs("#top_pairs").value = state.top_pairs;
  qs("#top_cmd").value = state.top_cmd;

  qs("#filters").addEventListener("submit", (ev) => {
    ev.preventDefault();
    state.player = qs("#player").value || "__all__";
    state.min_pg = parseInt(qs("#min_pg").value, 10) || 3;
    state.min_pair = parseInt(qs("#min_pair").value, 10) || 3;
    state.min_cmd = parseInt(qs("#min_cmd").value, 10) || 3;
    state.top_players = parseInt(qs("#top_players").value, 10) || 10;
    state.top_pairs = parseInt(qs("#top_pairs").value, 10) || 10;
    state.top_cmd = parseInt(qs("#top_cmd").value, 10) || 10;

    // clamp & update url
    readQueryIntoState();
    writeStateToQuery();

    render();
  });
}

function sortByWinrateThenGames(a, b) {
  // desc winrate, desc games, asc name-ish
  if (b.winrate !== a.winrate) return b.winrate - a.winrate;
  if (b.games !== a.games) return b.games - a.games;
  const an = (a.player || a.commander || "").toLowerCase();
  const bn = (b.player || b.commander || "").toLowerCase();
  return an.localeCompare(bn);
}

function colorForIndex(i) {
  // keep same palette as the legacy template
  const colors = [
    "#4e79a7", "#f28e2b", "#e15759", "#76b7b2",
    "#59a14f", "#edc949", "#af7aa1", "#ff9da7",
    "#9c755f", "#bab0ab"
  ];
  return colors[i % colors.length];
}

let charts = [];
function resetCharts() {
  for (const c of charts) {
    try { c.destroy(); } catch (_) {}
  }
  charts = [];
}

function bar(canvasId, labels, values, labelText) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  const c = new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets: [{ label: labelText || '', data: values }] },
    options: {
      responsive: true,
      plugins: { legend: { display: !!labelText } },
      scales: { y: { beginAtZero: true, max: 100 } }
    }
  });
  charts.push(c);
}

function line(canvasId, labels, values, labelText) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  const c = new Chart(ctx, {
    type: 'line',
    data: { labels, datasets: [{ label: labelText || '', data: values, tension: 0.2, fill: false }] },
    options: {
      responsive: true,
      plugins: { legend: { display: !!labelText } },
      scales: { y: { beginAtZero: true, max: 100 } }
    }
  });
  charts.push(c);
}

function render() {
  if (!DATA) return;
  resetCharts();

  // 1) Players
  const playerRows = DATA.player_stats
    .filter(r => r.games >= state.min_pg)
    .slice()
    .sort(sortByWinrateThenGames);

  const playerTop = playerRows.slice(0, state.top_players);
  bar("playerWinrateChart", playerTop.map(r => r.player), playerTop.map(r => r.winrate), "Winrate %");

  // Scatter: one dataset per player (for legend)
  const scatter = playerRows.map((r, i) => {
    const rr = 4 + Math.min(14, Math.floor(Math.sqrt(r.games) * 3));
    return {
      label: r.player,
      data: [{ x: r.games, y: r.winrate, r: rr, _meta: r }],
      backgroundColor: colorForIndex(i),
    };
  });

  const bubble = new Chart(document.getElementById("playerScatterChart"), {
    type: 'bubble',
    data: { datasets: scatter },
    options: {
      responsive: true,
      plugins: {
        legend: { position: 'right' },
        tooltip: {
          callbacks: {
            label: function(ctx) {
              const r = ctx.raw._meta;
              return `${r.player}: ${r.winrate}% (${r.wins}/${r.games})`;
            }
          }
        }
      },
      scales: {
        x: { title: { display: true, text: "# Partite" }, beginAtZero: true },
        y: { title: { display: true, text: "Winrate %" }, beginAtZero: true, max: 100 }
      }
    }
  });
  charts.push(bubble);

  // 2) Pairing
  const pairRows = DATA.pair_stats
    .filter(r => r.games >= state.min_pair)
    .slice()
    .sort((a, b) => {
      if (b.winrate !== a.winrate) return b.winrate - a.winrate;
      if (b.games !== a.games) return b.games - a.games;
      return (a.player + "|" + a.commander).toLowerCase().localeCompare((b.player + "|" + b.commander).toLowerCase());
    })
    .slice(0, state.top_pairs);

  bar(
    "pairingWinrateChart",
    pairRows.map(r => `${r.player} — ${r.commander}`),
    pairRows.map(r => r.winrate),
    "Winrate %"
  );

  const tbody = qs("#pairingWinrateTable");
  tbody.innerHTML = "";
  for (const r of pairRows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><b>${r.player}</b></td>
      <td>${r.commander}</td>
      <td>${r.games}</td>
      <td>${r.wins}</td>
      <td>${r.winrate}%</td>
    `;
    tbody.appendChild(tr);
  }

  // 3) Pod winrate (baseline)
  const pod = (state.player === "__all__")
    ? DATA.pod_stats["__all__"]
    : (DATA.pod_stats.by_player[state.player] || {});

  const podSizes = Object.keys(pod).map(x => parseInt(x, 10)).filter(x => !Number.isNaN(x)).sort((a,b) => a-b);
  const podLabels = podSizes.map(n => `${n}p`);

  const podValues = podSizes.map(n => {
    const v = pod[String(n)];
    const denom = v ? v.participations : 0;
    const wins = v ? v.wins : 0;
    return denom ? Math.round((wins/denom)*1000)/10 : 0;
  });
  const podBaseline = podSizes.map(n => Math.round((1/n)*1000)/10);

  const podChart = new Chart(document.getElementById("podWinrateChart"), {
    type: 'bar',
    data: {
      labels: podLabels,
      datasets: [
        { label: "WR%", data: podValues },
        { label: "Baseline 1/N", data: podBaseline }
      ]
    },
    options: { responsive: true, scales: { y: { beginAtZero: true, max: 100 } } }
  });
  charts.push(podChart);

  // 4) Commander
  const cmdRows = DATA.commander_stats
    .filter(r => r.games >= state.min_cmd)
    .slice()
    .sort((a, b) => {
      if (b.winrate !== a.winrate) return b.winrate - a.winrate;
      if (b.games !== a.games) return b.games - a.games;
      return a.commander.toLowerCase().localeCompare(b.commander.toLowerCase());
    })
    .slice(0, state.top_cmd);

  bar(
    "commanderWinrateChart",
    cmdRows.map(r => r.commander),
    cmdRows.map(r => r.winrate),
    "Winrate %"
  );

  // 5) Trend (solo se player specifico)
  const trendWrap = qs("#trendWrap");
  const trendNote = qs("#trendNote");
  if (state.player === "__all__") {
    trendNote.textContent = "Seleziona un player specifico per vedere il trend cumulativo.";
    trendWrap.style.display = "none";
  } else {
    const t = DATA.trend[state.player];
    trendNote.textContent = `Player: ${state.player}`;
    trendWrap.style.display = "block";
    if (t && t.labels && t.values) {
      line("trendChart", t.labels, t.values, "Cumulative WR%");
    }
  }

  // Header text updates
  qs("#hPlayers").textContent = `Winrate Player (top ${state.top_players}, min ${state.min_pg} partite)`;
  qs("#hPairs").textContent = `Top pairing Player+Commander per winrate (min ${state.min_pair} partite)`;
  qs("#hCmd").textContent = `Top Commander per winrate (min ${state.min_cmd} partite)`;
  qs("#hPod").textContent = `Winrate per pod size — ${state.player === "__all__" ? "Tutti i player" : state.player}`;
}

async function main() {
  readQueryIntoState();
  const res = await fetch("../data/dashboard.v1.json", { cache: "no-store" });
  DATA = await res.json();

  // if query asks unknown player, reset
  if (state.player !== "__all__" && !DATA.dimensions.players.includes(state.player)) {
    state.player = "__all__";
  }

  initForm();
  render();
}

main().catch(err => {
  console.error(err);
  const el = document.getElementById("error");
  if (el) el.textContent = "Errore nel caricamento dati dashboard.";
});
"""


def build_dashboard_html(css: str) -> str:
    css = css.strip() if css else ""
    if not css:
        css = "body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:1200px;margin:24px auto;padding:0 16px;} .row{display:flex;gap:16px;flex-wrap:wrap;} .card{border:1px solid #ddd;border-radius:12px;padding:16px;flex:1;min-width:320px;} .muted{color:#666} table{width:100%;border-collapse:collapse;} th,td{border-bottom:1px solid #eee;padding:8px;text-align:left;} select,input{padding:6px;} button{padding:8px 12px;}"  # noqa: E501

    return f"""<!doctype html>
<html lang=\"it\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Dashboard</title>
  <style>{css}</style>
</head>
<body>
  <div style=\"display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;\">
    <h1 style=\"margin:0;\">Dashboard</h1>
    <div class=\"muted\" style=\"font-size:14px;\">Static (JSON-driven)</div>
  </div>

  <p id=\"error\" class=\"muted\"></p>

  <form id=\"filters\" class=\"card\" style=\"margin:16px 0;\">
    <div class=\"row\" style=\"align-items:end;\">
      <div style=\"min-width:240px;\">
        <label>Player (pod + trend)</label><br>
        <select id=\"player\" name=\"player\"></select>
      </div>

      <div>
        <label>Min partite (player)</label><br>
        <input id=\"min_pg\" type=\"number\" min=\"1\" style=\"width:90px;\">
      </div>

      <div>
        <label>Min partite (pairing)</label><br>
        <input id=\"min_pair\" type=\"number\" min=\"1\" style=\"width:90px;\">
      </div>

      <div>
        <label>Min partite (commander)</label><br>
        <input id=\"min_cmd\" type=\"number\" min=\"1\" style=\"width:90px;\">
      </div>

      <div>
        <label>Top players</label><br>
        <input id=\"top_players\" type=\"number\" min=\"1\" max=\"50\" style=\"width:90px;\">
      </div>

      <div>
        <label>Top pairs</label><br>
        <input id=\"top_pairs\" type=\"number\" min=\"1\" max=\"50\" style=\"width:90px;\">
      </div>

      <div>
        <label>Top commanders</label><br>
        <input id=\"top_cmd\" type=\"number\" min=\"1\" max=\"50\" style=\"width:110px;\">
      </div>

      <div>
        <button type=\"submit\">Aggiorna</button>
      </div>
    </div>
  </form>

  <div class=\"row\">
    <div class=\"card\">
      <h3 id=\"hPlayers\">Winrate Player</h3>
      <canvas id=\"playerWinrateChart\"></canvas>
    </div>

    <div class=\"card\">
      <h3>WR% vs #Partite (sample size)</h3>
      <canvas id=\"playerScatterChart\"></canvas>
      <p class=\"muted\" style=\"margin-top:8px;\">Ogni punto = un player. Più a destra = più partite.</p>
    </div>
  </div>

  <div class=\"row\">
    <div class=\"card\">
      <h3 id=\"hCmd\">Top Commander per winrate</h3>
      <canvas id=\"commanderWinrateChart\"></canvas>
    </div>

    <div class=\"card\">
      <h3 id=\"hPod\">Winrate per pod size</h3>
      <canvas id=\"podWinrateChart\"></canvas>
      <p class=\"muted\" style=\"margin-top:8px;\">Baseline = 1/N (es. in 4p è 25%).</p>
    </div>
  </div>

  <div class=\"row\">
    <div class=\"card\">
      <h3>Trend winrate cumulativo</h3>
      <p id=\"trendNote\" class=\"muted\" style=\"margin-top:-8px;\"></p>
      <div id=\"trendWrap\">
        <canvas id=\"trendChart\"></canvas>
      </div>
    </div>

    <div class=\"card\">
      <h3 id=\"hPairs\">Top pairing Player+Commander per winrate</h3>
      <canvas id=\"pairingWinrateChart\"></canvas>
      <table style=\"margin-top:12px;\">
        <thead>
          <tr><th>Player</th><th>Commander</th><th>#</th><th>W</th><th>WR%</th></tr>
        </thead>
        <tbody id=\"pairingWinrateTable\"></tbody>
      </table>
    </div>
  </div>

  <script src=\"https://cdn.jsdelivr.net/npm/chart.js\"></script>
  <script src=\"../assets/dashboard.js\"></script>
</body>
</html>
"""


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "dashboard").mkdir(parents=True, exist_ok=True)

    # 1) Data
    with Session(engine) as session:
        dataset = build_dashboard_dataset(session)

    (DATA_DIR / "dashboard.v1.json").write_text(
        json.dumps(dataset, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    # 2) JS
    (ASSETS_DIR / "dashboard.js").write_text(DASHBOARD_JS.strip() + "\n", encoding="utf-8")

    # 3) HTML
    css = _read_base_css()
    html = build_dashboard_html(css)
    (OUT_DIR / "dashboard" / "index.html").write_text(html, encoding="utf-8")

    print("Wrote:")
    print(" - docs/dashboard/index.html")
    print(" - docs/assets/dashboard.js")
    print(" - docs/data/dashboard.v1.json")


if __name__ == "__main__":
    main()
