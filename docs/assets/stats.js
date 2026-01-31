/* Commander Stats - client side filtering (GitHub Pages friendly)
 *
 * Data source: ../data/stats.v1.json (generated offline by export_stats.py)
 * This script keeps the UI fully static (no backend) and robust against
 * missing/empty fields.
 */

const $ = (sel) => document.querySelector(sel);

// Charts (Chart.js)
let winrateBarChart = null;
let winrateBubbleChart = null;


function makeDarkScales({
  xTitle,
  yTitle = "Winrate (%)",
  yMax = 100,
  xBeginAtZero = true,
  dash = [1, 6],              // dotted/dashed pattern
} = {}) {
  const xGrid = {
    color: "rgba(255,255,255,0.30)",
    lineWidth: 1,
  };
  const yGrid = {
    color: "rgba(255,255,255,0.45)",
    lineWidth: 1,
  };

  const xTicks = { color: "rgba(255,255,255,0.5)" };
  const yTicks = { color: "rgba(255,255,255,0.5 )" };

  return {
    x: {
      ...(xBeginAtZero ? { beginAtZero: true } : {}),
      title: { display: true, text: xTitle || "" },
      grid: xGrid,
      ticks: xTicks,
      border: { dash, dashOffset: 0, color: "rgba(255,255,255,0.40)" },
    },
    y: {
      beginAtZero: true,
      ...(typeof yMax === "number" ? { max: yMax } : {}),
      title: { display: true, text: yTitle || "" },
      grid: yGrid,
      ticks: yTicks,
      border: { dash, dashOffset: 0, color: "rgba(255,255,255,0.40)" },
    },
  };
}


function fmtPct(x) {
  const v = x * 100;
  if (!isFinite(v)) return "0.0%";
  return v.toFixed(1) + "%";
}

function makeRateFragment(wins, games) {
  const span = document.createElement("span");
  const rate = games ? wins / games : 0;
  span.innerHTML = `${wins} / ${games} <span class="badge">${fmtPct(rate)}</span>`;
  return span;
}

function buildPlayerColorMap(players) {
  const arr = (players || []).slice().sort((a, b) => String(a || "").localeCompare(String(b || "")));
  const map = new Map();
  const n = Math.max(arr.length, 1);
  arr.forEach((p, i) => {
    const hue = Math.round((360 * i) / n);
    map.set(p, `hsl(${hue}, 70%, 58%)`);
  });
  return map;
}

function withAlpha(hslColor, alpha) {
  return String(hslColor || "hsl(0, 0%, 60%)")
    .replace(/^hsl\(/, "hsla(")
    .replace(/\)$/, `, ${alpha})`);
}

function aggregatePlayersFromPairs(rowsPair) {
  const map = new Map();
  for (const r of rowsPair || []) {
    const key = r.player ?? "";
    const cur = map.get(key) || { player: key, wins: 0, games: 0 };
    cur.wins += Number(r.wins || 0);
    cur.games += Number(r.games || 0);
    map.set(key, cur);
  }
  return Array.from(map.values());
}

function computePlayerRowsForCharts(data, state) {
  // If commander is selected, base charts on (player,commander,bracket) rows filtered by commander.
  // Otherwise, use pre-aggregated by_player.
  if (state.commander) {
    const rowsPairFiltered = (data.by_player_commander || [])
      .filter((r) => !state.player || r.player === state.player)
      .filter((r) => r.commander === state.commander);
    return aggregatePlayersFromPairs(rowsPairFiltered);
  }
  return (data.by_player || []).filter((r) => !state.player || r.player === state.player);
}

function renderCharts(rowsPlayer, allPlayers, state) {
  const info = $("#chartInfo");
  if (info) {
    const parts = [];
    if (state.player) parts.push(state.player);
    if (state.commander) parts.push(state.commander);
    info.textContent = parts.length
      ? parts.join(" · ")
      : `${rowsPlayer.length} player`;
  }

  // If Chart.js isn't loaded, keep page functional (tables still work).
  if (!window.Chart) return;

  const barEl = document.getElementById("winrateBar");
  const bubEl = document.getElementById("winrateBubble");
  if (!barEl || !bubEl) return;

  const colorMap = buildPlayerColorMap(allPlayers || []);
  const rows = (rowsPlayer || []).slice().sort((a, b) => {
    const ag = Number(a.games || 0), bg = Number(b.games || 0);
    const aw = Number(a.wins || 0), bw = Number(b.wins || 0);
    const ar = ag ? aw / ag : 0;
    const br = bg ? bw / bg : 0;
    return (ar - br) || (bg - ag) || String(a.player || "").localeCompare(String(b.player || ""));
  });
const labels = rows.map((r) => r.player);
  const winrates = rows.map((r) => {
    const g = Number(r.games || 0);
    const w = Number(r.wins || 0);
    const pct = g ? (w / g) * 100 : 0;
    return Math.round(pct * 10) / 10;
  });
  const colors = labels.map((p) => colorMap.get(p) || "hsl(0, 0%, 60%)");
  const maxWinrate = Math.max(...winrates, 0);
  const yMax = Math.min(100, Math.ceil(maxWinrate * 1.2));

  // Destroy previous charts (rerender on filters/sorts)
  if (winrateBarChart) winrateBarChart.destroy();
  if (winrateBubbleChart) winrateBubbleChart.destroy();

  winrateBarChart = new Chart(barEl, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label: "Winrate (%)",
        data: winrates,
        backgroundColor: colors.map((c) => withAlpha(c, 0.45)),
        borderColor: colors.map((c) => withAlpha(c, .8)),
        borderWidth: 1,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            afterLabel: (ctx) => {
              const r = rows[ctx.dataIndex];
              return `Partite: ${Number(r.games || 0)} · Vittorie: ${Number(r.wins || 0)}`;
            },
          },
        },
      },
      scales: makeDarkScales({ xTitle: "Player", yTitle: "Winrate (%)", yMax: yMax, xBeginAtZero: false })

,
    },
  });

  const bubbleDatasets = rows.map((r) => {
    const p = r.player;
    const c = colorMap.get(p) || "hsl(0, 0%, 60%)";
    const games = Number(r.games || 0);
    const wins = Number(r.wins || 0);
    const wrPct = games ? (wins / games) * 100 : 0;
    return {
      label: p,
      data: [{
        x: games,
        y: Math.round(wrPct * 10) / 10,
        r: Math.max(4, Math.sqrt(Math.max(games, 1)) * 2.2),
      }],
      backgroundColor: withAlpha(c, 0.30),
      borderColor: withAlpha(c, 1.0),
      borderWidth: 1,
    };
  });

  // Mediana partite (linea verticale)
  const gameCounts = rows.map((r) => Number(r.games || 0)).sort((a, b) => a - b);
  const medianGames = gameCounts.length
    ? (gameCounts.length % 2
        ? gameCounts[(gameCounts.length - 1) / 2]
        : (gameCounts[gameCounts.length / 2 - 1] + gameCounts[gameCounts.length / 2]) / 2)
    : null;

  winrateBubbleChart = new Chart(bubEl, {
    type: "bubble",
    data: { datasets: bubbleDatasets },
        options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {        legend: { display: true, position: "right" },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const p = ctx.dataset.label;
              const x = ctx.raw.x;
              const y = ctx.raw.y;
              const rr = rows.find((z) => z.player === p);
              const wins = rr ? Number(rr.wins || 0) : 0;
              return `${p}: Partite ${x}, Winrate ${y}%, Vittorie ${wins}`;
            },
          },
        },
      },
      scales: makeDarkScales({ xTitle: "Numero di partite", yTitle: "Winrate (%)", yMax: yMax, xBeginAtZero: true })


,
    },
  });
}

function setOptions(selectEl, values, keepValue = "") {
  const el = typeof selectEl === "string" ? $(selectEl) : selectEl;
  const prev = keepValue ?? el.value;

  // keep first option ("Tutti")
  while (el.options.length > 1) el.remove(1);

  (values || []).forEach((v) => {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    el.appendChild(opt);
  });

  // restore if possible
  if ([...el.options].some((o) => o.value === prev)) el.value = prev;
  else el.value = "";
}

function qsGet() {
  const p = new URLSearchParams(location.search);
  return {
    player: p.get("player") || "",
    commander: p.get("commander") || "",
  };
}

function qsSet(state) {
  const p = new URLSearchParams();
  if (state.player) p.set("player", state.player);
  if (state.commander) p.set("commander", state.commander);
  const url = `${location.pathname}${p.toString() ? "?" + p.toString() : ""}`;
  history.replaceState(null, "", url);
  return url;
}

function commandersForPlayer(data, player) {
  if (!player) {
    return (data.filters?.commanders || [])
      .slice()
      .sort((a, b) => String(a || "").localeCompare(String(b || "")));
  }
  const set = new Set();
  for (const r of data.by_player_commander || []) {
    if (r.player === player) set.add(r.commander);
  }
  return Array.from(set).sort((a, b) => a.localeCompare(b));
}

function aggregateBracketsFromPairs(rowsPair) {
  const map = new Map();
  for (const r of rowsPair || []) {
    const key = r.bracket === null || r.bracket === undefined || r.bracket === "" ? "n/a" : String(r.bracket);
    const cur = map.get(key) || { bracket: key, wins: 0, games: 0 };
    cur.wins += Number(r.wins || 0);
    cur.games += Number(r.games || 0);
    map.set(key, cur);
  }
  return Array.from(map.values()).sort((a, b) => b.games - a.games || a.bracket.localeCompare(b.bracket));
}

function sortRows(rows, mode, kind) {
  const arr = (rows || []).slice();
  const safeNum = (v) => Number.isFinite(Number(v)) ? Number(v) : 0;
  const wr = (r) => {
    const g = safeNum(r.games);
    return g ? safeNum(r.wins) / g : 0;
  };

  const cmpStr = (a, b) => String(a || "").localeCompare(String(b || ""));
  const alpha = (a, b) => {
    if (kind === "pair") {
      return (
        cmpStr(a.player, b.player) ||
        cmpStr(a.commander, b.commander) ||
        cmpStr(a.bracket, b.bracket)
      );
    }
    if (kind === "bracket") return cmpStr(a.bracket, b.bracket);
    return cmpStr(a.player, b.player);
  };

  switch (mode) {
    case "wins_desc":
      arr.sort((a, b) => safeNum(b.wins) - safeNum(a.wins) || alpha(a, b));
      break;
    case "games_desc":
      arr.sort((a, b) => safeNum(b.games) - safeNum(a.games) || alpha(a, b));
      break;
    case "wr_desc":
      arr.sort((a, b) => wr(b) - wr(a) || safeNum(b.games) - safeNum(a.games) || alpha(a, b));
      break;
    case "alpha":
    default:
      arr.sort(alpha);
      break;
  }
  return arr;
}

function td(text, className, label) {
  const cell = document.createElement("td");
  if (className) cell.className = className;
  if (label) cell.dataset.label = label;
  cell.textContent = text;
  return cell;
}

function renderPlayer(rows) {
  const tb = $("#tPlayer tbody");
  tb.innerHTML = "";

  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.appendChild(td(r.player ?? "", "", "Player"));
    tr.appendChild(td(String(r.wins ?? 0), "num", "Vittorie"));
    tr.appendChild(td(String(r.games ?? 0), "num", "Partite"));
    const rateCell = document.createElement("td");
    rateCell.className = "num";
    rateCell.dataset.label = "Win rate";
    rateCell.appendChild(makeRateFragment(Number(r.wins || 0), Number(r.games || 0)));
    tr.appendChild(rateCell);
    tb.appendChild(tr);
  }
  $("#countPlayer").textContent = `${rows.length} righe`;
}

function renderPair(rows) {
  const tb = $("#tPair tbody");
  tb.innerHTML = "";
  const cap = 400;

  for (const r of rows.slice(0, cap)) {
    const tr = document.createElement("tr");
    tr.appendChild(td(r.player ?? "", "", "Player"));
    tr.appendChild(td(r.commander ?? "", "", "Commander"));
    tr.appendChild(td(r.bracket === null || r.bracket === undefined ? "n/a" : String(r.bracket), "", "Bracket"));
    tr.appendChild(td(String(r.wins ?? 0), "num", "Vittorie"));
    tr.appendChild(td(String(r.games ?? 0), "num", "Partite"));
    const rateCell = document.createElement("td");
    rateCell.className = "num";
    rateCell.dataset.label = "Win rate";
    rateCell.appendChild(makeRateFragment(Number(r.wins || 0), Number(r.games || 0)));
    tr.appendChild(rateCell);
    tb.appendChild(tr);
  }

  $("#countPair").textContent = rows.length > cap ? `${cap}/${rows.length} righe` : `${rows.length} righe`;
}

function renderBracket(rows) {
  const tb = $("#tBracket tbody");
  tb.innerHTML = "";
  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.appendChild(td(r.bracket ?? "n/a", "", "Bracket"));
    tr.appendChild(td(String(r.wins ?? 0), "num", "Vittorie"));
    tr.appendChild(td(String(r.games ?? 0), "num", "Partite"));
    const rateCell = document.createElement("td");
    rateCell.className = "num";
    rateCell.dataset.label = "Win rate";
    rateCell.appendChild(makeRateFragment(Number(r.wins || 0), Number(r.games || 0)));
    tr.appendChild(rateCell);
    tb.appendChild(tr);
  }
  $("#countBracket").textContent = `${rows.length} righe`;
}

function updateCommanderOptions(data, player, keepCommanderValue = "") {
  setOptions($("#fCommander"), commandersForPlayer(data, player), keepCommanderValue);
}

function buildTables(data) {
  const state = {
    player: $("#fPlayer").value,
    commander: $("#fCommander").value,
  };
  qsSet(state);

  const parts = [];
  if (state.player) parts.push(`player: ${state.player}`);
  if (state.commander) parts.push(`commander: ${state.commander}`);
  $("#hint").textContent = parts.length ? `Filtri attivi → ${parts.join(" · ")}` : "Nessun filtro attivo.";

  // Charts (winrate per player + bubble x=partite)
  renderCharts(
    computePlayerRowsForCharts(data, state),
    data.filters?.players || [],
    state
  );

  const rowsP = sortRows(
    (data.by_player || []).filter((r) => !state.player || r.player === state.player),
    $("#sPlayer")?.value || "alpha",
    "player"
  );
  renderPlayer(rowsP);

  const rowsPair = sortRows(
    (data.by_player_commander || [])
      .filter((r) => !state.player || r.player === state.player)
      .filter((r) => !state.commander || r.commander === state.commander),
    $("#sPair")?.value || "alpha",
    "pair"
  );
  renderPair(rowsPair);

  const rowsBracket = sortRows(
    aggregateBracketsFromPairs(rowsPair),
    $("#sBracket")?.value || "games_desc",
    "bracket"
  );
  renderBracket(rowsBracket);
}

async function main() {
  const res = await fetch("../data/stats.v1.json", { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status} (${res.statusText})`);
  const data = await res.json();

  const games = data.counts?.games ?? 0;
  const entries = data.counts?.entries ?? 0;
  const gen = data.generated_utc ?? "";
  $("#meta").textContent = `${games} game · ${entries} entries${gen ? " · gen " + gen : ""}`;

  setOptions($("#fPlayer"), data.filters?.players || []);

  // Load state from querystring
  const qs = qsGet();
  $("#fPlayer").value = qs.player;
  updateCommanderOptions(data, qs.player, qs.commander);

  const rerender = () => buildTables(data);

  // Player change → Commander options become nested
  $("#fPlayer").addEventListener("change", () => {
    updateCommanderOptions(data, $("#fPlayer").value, $("#fCommander").value);
    rerender();
  });
  $("#fCommander").addEventListener("change", rerender);

  // Sorting dropdowns
  $("#sPlayer")?.addEventListener("change", rerender);
  $("#sPair")?.addEventListener("change", rerender);
  $("#sBracket")?.addEventListener("change", rerender);

  $("#btnReset").addEventListener("click", () => {
    $("#fPlayer").value = "";
    updateCommanderOptions(data, "", "");
    rerender();
  });

  $("#btnLink").addEventListener("click", async () => {
    const url = qsSet({
      player: $("#fPlayer").value,
      commander: $("#fCommander").value,
    });
    try {
      const full = location.origin ? location.origin + url : url;
      await navigator.clipboard.writeText(full);
      $("#hint").textContent = "Link copiato negli appunti ✅";
      setTimeout(rerender, 900);
    } catch {
      prompt("Copia questo link:", url);
    }
  });

  rerender();
}

main().catch((err) => {
  console.error(err);
  const sub = $("#subtitle");
  if (sub) sub.textContent = "Errore nel caricamento dei dati. Vedi console.";
});
