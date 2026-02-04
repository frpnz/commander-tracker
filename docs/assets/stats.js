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

// --- COLOR MANAGER ---
const playerColorCache = {};
let playerColorIndex = 0;

function getPlayerColor(name) {
  if (!name) return "#666";
  if (playerColorCache[name]) return playerColorCache[name];
  const hue = (playerColorIndex * 137.508) % 360;
  const color = `hsl(${hue}, 75%, 60%)`;
  playerColorCache[name] = color;
  playerColorIndex++;
  return color;
}

function withAlpha(color, alpha) {
  if (color.startsWith("#")) {
    const r = parseInt(color.slice(1, 3), 16);
    const g = parseInt(color.slice(3, 5), 16);
    const b = parseInt(color.slice(5, 7), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }
  if (color.startsWith("hsl")) {
    return color.replace("hsl", "hsla").replace(")", `, ${alpha})`);
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
    options: { ...commonChartOptions(), indexAxis: 'y', scales: { x: { suggestedMax: 50, ticks: { color: COL_TEXT_MUTED } }, y: { ticks: { color: COL_TEXT_MUTED } } } }
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
  const player = $("#fPlayer").value;
  const topN = parseInt($("#fTopN")?.value || DEFAULT_TOP_N, 10);

  let pStats = (data.by_player || []).map(r => ({ name: r.player, games: r.games, wins: r.wins, winRate: r.games > 0 ? (r.wins / r.games) * 100 : 0 }));
  renderWinrateBarChart(pStats, player);

  let cStats = (data.by_player_commander || []).map(r => ({ player: r.player, commander: r.commander, games: r.games, wins: r.wins, winRate: r.games > 0 ? (r.wins / r.games) * 100 : 0, bracket: r.bracket }));

  if (player) {
    const filtered = cStats.filter(r => r.player === player);
    renderBubbleChart(filtered, false, Math.max(...filtered.map(c => c.games), 1));
    if ($("#tPlayer")) $("#tPlayer").style.display = "none";
    if ($("#tPair")) { $("#tPair").style.display = ""; renderTable($("#tPair tbody"), filtered, true); }
  } else {
    renderBubbleChart(pStats, true, Math.max(...pStats.map(p => p.games), 1));
    if ($("#tPlayer")) { $("#tPlayer").style.display = ""; renderTable($("#tPlayer tbody"), pStats, false); }
    if ($("#tPair")) {
      $("#tPair").style.display = "";
      const topRows = [];
      const groups = {}; cStats.forEach(r => { if (!groups[r.player]) groups[r.player] = []; groups[r.player].push(r); });
      Object.values(groups).forEach(g => { g.sort((a,b) => b.games - a.games); topRows.push(...g.slice(0, topN)); });
      renderTable($("#tPair tbody"), topRows, true);
    }
  }
}

function renderTable(tbody, rows, isComm) {
  if (!tbody) return;
  rows.sort((a, b) => b.games - a.games);
  tbody.innerHTML = "";
  rows.forEach(r => {
    const tr = document.createElement("tr");
    if (isComm) {
      tr.innerHTML = `<td data-label="Player">${r.player}</td><td data-label="Commander">${r.commander}</td><td data-label="Bracket">${r.bracket || "-"}</td>`;
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
  rerender();
}

main();