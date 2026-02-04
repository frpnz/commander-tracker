/* Commander Stats - client side filtering
 * Data source: ../data/stats.v1.json
 */

const $ = (sel) => document.querySelector(sel);

// Global Chart instances
let winrateBarChart = null;
let winrateBubbleChart = null;

// Configuration
const DEFAULT_TOP_N = 3;

// --- PARAMETRI UTENTE ---
const BUBBLE_RADIUS = 11; // Raggio fisso delle bolle

// Colors & Palette
const COL_TEXT_MUTED = "#aab3d3";
const COL_TEXT_MAIN = "#e9ecf7";

// --- COLOR MANAGER (deterministico, coerente tra pagine) ---
// Palette: colori ad alta distinzione (Tol/Okabe-Ito) + varianti light/dark deterministiche.
const PLAYER_PALETTE = [
  '#332288', '#88CCEE', '#44AA99', '#117733', '#999933',
  '#DDCC77', '#CC6677', '#882255', '#AA4499', '#E69F00',
  '#56B4E9', '#009E73', '#F0E442', '#0072B2', '#D55E00', '#CC79A7'
];

function hash32(str) {
  // DJB2 32-bit
  let h = 5381;
  for (let i = 0; i < str.length; i++) {
    h = ((h << 5) + h) + str.charCodeAt(i);
    h = h >>> 0;
  }
  return h >>> 0;
}

function hexToRgb(hex) {
  const s = hex.replace('#', '').trim();
  if (s.length !== 6) return null;
  const r = parseInt(s.slice(0, 2), 16);
  const g = parseInt(s.slice(2, 4), 16);
  const b = parseInt(s.slice(4, 6), 16);
  if (!Number.isFinite(r) || !Number.isFinite(g) || !Number.isFinite(b)) return null;
  return { r, g, b };
}

function adjustRgb(rgb, amount) {
  // amount in [-1, +1]; >0 => lighten, <0 => darken
  const clamp = (x) => Math.max(0, Math.min(255, Math.round(x)));
  let { r, g, b } = rgb;
  if (amount >= 0) {
    r = r + (255 - r) * amount;
    g = g + (255 - g) * amount;
    b = b + (255 - b) * amount;
  } else {
    const k = 1 + amount; // e.g. -0.18 => 0.82
    r = r * k;
    g = g * k;
    b = b * k;
  }
  return { r: clamp(r), g: clamp(g), b: clamp(b) };
}

function getPlayerColor(name) {
  if (!name) return '#666666';
  const h = hash32(String(name).trim().toLowerCase());
  const base = PLAYER_PALETTE[h % PLAYER_PALETTE.length];
  const variant = (h >>> 8) % 3; // 0 base, 1 light, 2 dark
  const rgb = hexToRgb(base) || { r: 102, g: 102, b: 102 };
  const amt = variant === 1 ? 0.18 : (variant === 2 ? -0.18 : 0.0);
  const adj = adjustRgb(rgb, amt);
  return `#${adj.r.toString(16).padStart(2,'0')}${adj.g.toString(16).padStart(2,'0')}${adj.b.toString(16).padStart(2,'0')}`.toUpperCase();
}

function withAlpha(color, alpha) {
  if (!color) return color;
  // Hex -> rgba
  if (color.startsWith('#') && color.length === 7) {
    const rgb = hexToRgb(color);
    if (!rgb) return color;
    return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${alpha})`;
  }
  // rgb(...) -> rgba(...)
  if (color.startsWith('rgb(')) {
    return color.replace(/^rgb\((.*)\)$/, `rgba($1, ${alpha})`);
  }
  // hsl(...) -> hsla(...)
  if (color.startsWith('hsl(')) {
    return color.replace(/^hsl\((.*)\)$/, `hsla($1, ${alpha})`);
  }
  // hsla(...) -> replace alpha
  if (color.startsWith('hsla(')) {
    return color.replace(/hsla\((.*),\s*([0-9.]+)\)$/, `hsla($1, ${alpha})`);
  }
  return color;
}
// --- MOBILE CSS INJECTION ---
(function injectMobileStyles() {
  const style = document.createElement('style');
  style.innerHTML = `
    @media (max-width: 768px) {
      table { border-collapse: collapse; width: 100%; }
      thead { display: none; } 
      tr { display: block; margin-bottom: 15px; background: rgba(255,255,255,0.03); border-radius: 8px; padding: 10px; border: 1px solid rgba(255,255,255,0.05); }
      td { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.05); text-align: right; font-size: 0.95em; }
      td:last-child { border-bottom: none; }
      td::before { content: attr(data-label); font-weight: 600; color: ${COL_TEXT_MUTED}; text-align: left; margin-right: 10px; }
      .chart-wrap canvas { max-width: 100% !important; height: auto !important; min-height: 250px; }
    }
  `;
  document.head.appendChild(style);
})();


function generateHtmlLegend(chart, containerId) {
  const container = document.getElementById(containerId);
  if (!container) {
    const div = document.createElement("div");
    div.id = containerId;
    div.style.display = "flex"; div.style.flexWrap = "wrap"; div.style.gap = "12px"; div.style.justifyContent = "center"; div.style.marginTop = "10px"; div.style.fontSize = "12px"; div.style.color = COL_TEXT_MUTED;
    chart.canvas.parentElement.parentElement.appendChild(div);
    return generateHtmlLegend(chart, containerId);
  }
  container.innerHTML = "";
  const data = chart.data;
  const labels = data.labels || [];
  let items = [];
  if (labels.length > 0) {
    items = labels.map((l, i) => ({ label: l, color: Array.isArray(data.datasets[0].borderColor) ? data.datasets[0].borderColor[i] : data.datasets[0].borderColor }));
  } else {
    const players = new Set();
    data.datasets[0].data.forEach(d => { if (d._raw) players.add(d._raw.player); });
    items = Array.from(players).sort().map(p => ({ label: p, color: getPlayerColor(p) }));
  }
  items.forEach(item => {
    const el = document.createElement("div"); el.style.display = "flex"; el.style.alignItems = "center"; el.style.gap = "6px";
    const box = document.createElement("span"); box.style.width = "10px"; box.style.height = "10px"; box.style.borderRadius = "50%"; box.style.backgroundColor = item.color;
    const text = document.createElement("span"); text.textContent = item.label;
    el.appendChild(box); el.appendChild(text); container.appendChild(el);
  });
}

function commonChartOptions(xTitle) {
  return {
    responsive: true, maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: 'rgba(11, 16, 32, 0.95)',
        titleColor: COL_TEXT_MUTED,
        bodyColor: COL_TEXT_MAIN,
        borderColor: 'rgba(255,255,255,0.1)',
        borderWidth: 1,
        padding: 10
      }
    },
    layout: { padding: { left: 10, right: 20, top: 20, bottom: 10 } },
    scales: { x: { title: { display: !!xTitle, text: xTitle, color: COL_TEXT_MUTED }, grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: COL_TEXT_MUTED } } }
  };
}

function getSafeYAxis() {
  return {
    min: -5, max: 75,
    ticks: { stepSize: 10, color: COL_TEXT_MUTED, callback: (v) => (v >= 0 && v <= 70) ? v + "%" : "" }
  };
}

function renderWinrateBarChart(playersData, highlightPlayer) {
  const canvas = $("#winrateBar"); if (!canvas) return;
  const sorted = [...playersData].filter(p => p.games > 0).sort((a, b) => b.winRate - a.winRate);
  const labels = sorted.map(p => p.name);
  const bgColors = sorted.map(p => withAlpha(getPlayerColor(p.name), highlightPlayer ? (p.name === highlightPlayer ? 1.0 : 0.15) : 0.6));
  const borderColors = sorted.map(p => highlightPlayer && p.name !== highlightPlayer ? withAlpha(getPlayerColor(p.name), 0.3) : getPlayerColor(p.name));

  if (winrateBarChart) winrateBarChart.destroy();
  winrateBarChart = new Chart(canvas.getContext("2d"), {
    type: 'bar',
    data: { labels, datasets: [{ data: sorted.map(p => p.winRate), backgroundColor: bgColors, borderColor: borderColors, borderWidth: 1, barPercentage: 0.7 }] },
    options: {
      ...commonChartOptions(),
      indexAxis: 'y',
      plugins: {
        ...commonChartOptions().plugins,
        tooltip: {
          ...commonChartOptions().plugins.tooltip,
          callbacks: {
            title: (items) => items?.[0]?.label || '',
            label: (ctx) => {
              const p = sorted[ctx.dataIndex];
              return `Winrate: ${p.winRate.toFixed(1)}%`;
            },
            afterLabel: (ctx) => {
              const p = sorted[ctx.dataIndex];
              return `Vittorie: ${p.wins} | Partite: ${p.games}`;
            }
          }
        }
      },
      scales: {
        x: { suggestedMax: 50, ticks: { color: COL_TEXT_MUTED } },
        y: { ticks: { color: COL_TEXT_MUTED } }
      }
    }
  });
  generateHtmlLegend(winrateBarChart, "legend-bar");
}

function renderBubbleChart(data, isPlayerView, maxGames) {
  const canvas = $("#winrateBubble"); if (!canvas) return;
  const points = data.map(d => ({ x: d.games, y: d.winRate, r: BUBBLE_RADIUS, _raw: d }));
  if (winrateBubbleChart) winrateBubbleChart.destroy();

  const options = commonChartOptions(isPlayerView ? "Partite (Player)" : "Partite (Commander)");
  options.scales.x = { min: 0, suggestedMax: maxGames * 1.15, ticks: { color: COL_TEXT_MUTED } };
  options.scales.y = getSafeYAxis();

  // Configurazione Tooltip Dinamico
  options.plugins.tooltip.callbacks = {
    label: (ctx) => {
      const d = ctx.raw._raw;
      if (isPlayerView) return d.name;
      return `${d.commander} (${d.player})`;
    },
    afterLabel: (ctx) => {
      const d = ctx.raw._raw;
      return `Winrate: ${d.winRate.toFixed(1)}% | Partite: ${d.games}`;
    }
  };

  winrateBubbleChart = new Chart(canvas.getContext("2d"), {
    type: 'bubble',
    data: {
      labels: isPlayerView ? data.map(d => d.name) : [],
      datasets: [{
        data: points,
        backgroundColor: data.map(d => withAlpha(getPlayerColor(isPlayerView ? d.name : d.player), 0.6)),
        borderColor: data.map(d => getPlayerColor(isPlayerView ? d.name : d.player)),
        borderWidth: 1,
        clip: false
      }]
    },
    options: options
  });
  generateHtmlLegend(winrateBubbleChart, "legend-bubble");
}

function buildTables(rawData) {
  const data = rawData;
  const player = $("#fPlayer")?.value || "";
  const topN = parseInt($("#fTopN")?.value || DEFAULT_TOP_N, 10);

  const sortPlayer = $("#sPlayer")?.value || "alpha";
  const sortPair = $("#sPair")?.value || "alpha";
  const sortBracket = $("#sBracket")?.value || "games_desc";

  const hint = $("#hint");
  const chartTitle = $("#chartTitle");
  const chartInfo = $("#chartInfo");

  const pStats = (data.by_player || []).map(r => ({
    name: r.player,
    games: r.games,
    wins: r.wins,
    winRate: r.games > 0 ? (r.wins / r.games) * 100 : 0
  }));

  const pairStatsAll = (data.by_player_commander || []).map(r => ({
    player: r.player,
    commander: r.commander,
    bracket: r.bracket ?? "-",
    games: r.games,
    wins: r.wins,
    winRate: r.games > 0 ? (r.wins / r.games) * 100 : 0
  }));

  const bracketStats = (data.by_bracket || []).map(r => ({
    bracket: r.bracket,
    games: r.games,
    wins: r.wins,
    winRate: r.games > 0 ? (r.wins / r.games) * 100 : 0
  }));

  // --- Charts ---
  if (player) {
    const filteredPairs = pairStatsAll.filter(r => r.player === player);
    if (chartTitle) chartTitle.textContent = `Winrate per ${player}`;
    if (chartInfo) chartInfo.textContent = `Commander mostrati: ${filteredPairs.length}`;
    renderWinrateBarChart(pStats, player);
    renderBubbleChart(filteredPairs, false, Math.max(...filteredPairs.map(c => c.games), 1));
    if (hint) hint.textContent = `Filtro attivo: ${player} · Ordinamenti applicati alle tabelle.`;
  } else {
    if (chartTitle) chartTitle.textContent = "Winrate per player";
    if (chartInfo) chartInfo.textContent = `Player: ${pStats.length}`;
    renderWinrateBarChart(pStats, "");
    renderBubbleChart(pStats, true, Math.max(...pStats.map(p => p.games), 1));
    if (hint) hint.textContent = `Mostro Top ${topN} commander per player nella tabella “Player + Commander”.`;
  }

  // --- Tables ---
  const tPlayer = $("#tPlayer");
  const tPair = $("#tPair");
  const tBracket = $("#tBracket");

  if (player) {
    if (tPlayer) tPlayer.style.display = "none";
    if (tPair) {
      tPair.style.display = "";
      const filteredPairs = pairStatsAll.filter(r => r.player === player);
      renderTable($("#tPair tbody"), filteredPairs, "pair", sortPair);
      const cp = $("#countPair"); if (cp) cp.textContent = `${filteredPairs.length}`;
    }
  } else {
    if (tPlayer) {
      tPlayer.style.display = "";
      renderTable($("#tPlayer tbody"), pStats, "player", sortPlayer);
      const cp = $("#countPlayer"); if (cp) cp.textContent = `${pStats.length}`;
    }
    if (tPair) {
      tPair.style.display = "";
      const topRows = [];
      const groups = {};
      pairStatsAll.forEach(r => { (groups[r.player] ||= []).push(r); });
      Object.values(groups).forEach(g => {
        g.sort((a, b) => b.games - a.games);
        topRows.push(...g.slice(0, topN));
      });
      renderTable($("#tPair tbody"), topRows, "pair", sortPair);
      const cp = $("#countPair"); if (cp) cp.textContent = `${topRows.length}`;
    }
  }

  if (tBracket) {
    renderTable($("#tBracket tbody"), bracketStats, "bracket", sortBracket);
    const cb = $("#countBracket"); if (cb) cb.textContent = `${bracketStats.length}`;
  }
}


function sortByKey(rows, sortKey, kind) {
  const num = (x) => (typeof x === "number" && isFinite(x)) ? x : 0;
  const str = (x) => (x == null ? "" : String(x)).toLowerCase();

  const cmpAlphaPlayer = (a, b) => str(a.name).localeCompare(str(b.name));
  const cmpAlphaPair = (a, b) => {
    const c1 = str(a.player).localeCompare(str(b.player));
    if (c1) return c1;
    const c2 = str(a.commander).localeCompare(str(b.commander));
    if (c2) return c2;
    // bracket: numeric first, then string
    const ba = a.bracket; const bb = b.bracket;
    const na = (ba == null || ba === "" || ba === "-") ? NaN : Number(ba);
    const nb = (bb == null || bb === "" || bb === "-") ? NaN : Number(bb);
    if (isFinite(na) && isFinite(nb)) return na - nb;
    return str(ba).localeCompare(str(bb));
  };
  const cmpAlphaBracket = (a, b) => {
    const na = Number(a.bracket);
    const nb = Number(b.bracket);
    if (isFinite(na) && isFinite(nb)) return na - nb;
    return str(a.bracket).localeCompare(str(b.bracket));
  };

  const cmp = {
    alpha: kind === "player" ? cmpAlphaPlayer : (kind === "pair" ? cmpAlphaPair : cmpAlphaBracket),
    games_desc: (a, b) => num(b.games) - num(a.games),
    wins_desc: (a, b) => num(b.wins) - num(a.wins),
    wr_desc: (a, b) => num(b.winRate) - num(a.winRate),
  }[sortKey] || (kind === "pair" ? cmpAlphaPair : (kind === "bracket" ? cmpAlphaBracket : cmpAlphaPlayer));

  rows.sort((a, b) => {
    const d = cmp(a, b);
    if (d) return d;
    // tie-break deterministici
    if (kind === "player") return str(a.name).localeCompare(str(b.name));
    if (kind === "pair") return cmpAlphaPair(a, b);
    return cmpAlphaBracket(a, b);
  });
  return rows;
}

function renderTable(tbody, rows, kind, sortKey) {
  if (!tbody) return;
  tbody.innerHTML = "";
  const rs = sortByKey([...rows], sortKey, kind);

  rs.forEach(r => {
    const tr = document.createElement("tr");
    if (kind === "pair") {
      tr.innerHTML = `<td data-label="Player">${r.player}</td><td data-label="Commander">${r.commander}</td><td data-label="Bracket">${r.bracket ?? "-"}</td>`;
    } else if (kind === "bracket") {
      tr.innerHTML = `<td data-label="Bracket">${r.bracket}</td>`;
    } else {
      tr.innerHTML = `<td data-label="Player">${r.name}</td>`;
    }
    tr.innerHTML += `<td data-label="Vittorie">${r.wins}</td><td data-label="Partite">${r.games}</td><td data-label="Win rate">${r.winRate.toFixed(1)}%</td>`;
    tbody.appendChild(tr);
  });
}


async function main() {
  const res = await fetch("../data/stats.v1.json", { cache: "no-cache" });
  const data = await res.json();
  const pSel = $("#fPlayer");
  if (pSel) (data.filters.players || []).sort().forEach(p => { const opt = document.createElement("option"); opt.value = p; opt.textContent = p; pSel.appendChild(opt); });

  const rerender = () => buildTables(data);
  pSel?.addEventListener("change", rerender);
  $("#fTopN")?.addEventListener("change", rerender);
  $("#sPlayer")?.addEventListener("change", rerender);
  $("#sPair")?.addEventListener("change", rerender);
  $("#sBracket")?.addEventListener("change", rerender);
  rerender();
}

main();