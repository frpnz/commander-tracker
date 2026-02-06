/* Commander Stats (charts-only)
   Data source: ../data/stats.v1.json
   Charts:
     1) Winrate per player (horizontal bar)
     2) Winrate vs Partite (bubble)
   Tooltip on bars shows: winrate + wins + total games.
   Player colors are shared via window.PlayerColors.
*/


// --- Plugin: print win rate on bars ---
const barValueLabels = {
  id: "barValueLabels",
  afterDatasetsDraw(chart, args, opts) {
    const { ctx } = chart;
    const meta = chart.getDatasetMeta(0);
    const data = chart.data.datasets[0].data || [];

    ctx.save();
    ctx.font = (opts && opts.font) || "600 11px system-ui, -apple-system, Segoe UI, Roboto, Arial";
    ctx.fillStyle = (opts && opts.color) || "rgba(255,255,255,0.9)";

    meta.data.forEach((bar, i) => {
      const v = data[i];
      if (v == null || Number.isNaN(v)) return;

      const p = bar.tooltipPosition();
      const txt = `${Number(v).toFixed(1)}%`;

      // clamp to chart area (avoid off-screen labels)
      const areaRight = chart.chartArea.right;
      const w = ctx.measureText(txt).width;
      let x = p.x + 8;
      if (x + w > areaRight - 2) x = areaRight - w - 2;

      ctx.fillText(txt, x, p.y + 4);
    });

    ctx.restore();
  }
};

(function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);

  const elMeta = $("#meta");
  const elPlayer = $("#fPlayer");
  const elHint = $("#hint");
  const canvasBar = $("#winrateBar");
  const canvasBubble = $("#winrateBubble");

  let stats = null;
  let barChart = null;
  let bubbleChart = null;

  const COL_TEXT_MUTED = "#aab3d3";
  const COL_TEXT_MAIN = "#e9ecf7";
  const MAX_Y_PLOTS = 60

  function pcGet(name) {
    return (window.PlayerColors && window.PlayerColors.get) ? window.PlayerColors.get(name) : "#9CA3AF";
  }

  function pcAlpha(color, alpha) {
    return (window.PlayerColors && window.PlayerColors.withAlpha) ? window.PlayerColors.withAlpha(color, alpha) : color;
  }

  function asNum(x, dflt = 0) {
    const n = Number(x);
    return Number.isFinite(n) ? n : dflt;
  }

  function computePlayers() {
    const rows = Array.isArray(stats?.by_player) ? stats.by_player : [];
    return rows
      .map((r) => {
        const games = asNum(r.games, 0);
        const wins = asNum(r.wins, 0);
        const wr = games > 0 ? (100 * wins) / games : 0;
        return { name: r.player, games, wins, winRate: wr };
      })
      .filter((p) => p.name);
  }

  function computeCommandersForPlayer(playerName) {
    const rows = Array.isArray(stats?.by_player_commander) ? stats.by_player_commander : [];
    const filtered = rows.filter((r) => r && r.player === playerName);
    const byCommander = new Map();
    for (const r of filtered) {
      const commander = String(r.commander || "").trim();
      if (!commander) continue;
      const games = asNum(r.games, 0);
      const wins = asNum(r.wins, 0);
      const cur = byCommander.get(commander) || { commander, games: 0, wins: 0 };
      cur.games += games;
      cur.wins += wins;
      byCommander.set(commander, cur);
    }
    return Array.from(byCommander.values()).map((c) => ({
      ...c,
      winRate: c.games > 0 ? (100 * c.wins) / c.games : 0,
    }));
  }

  function fillPlayerSelect(players) {
    if (!elPlayer) return;
    const names = Array.from(new Set(players.map((p) => p.name))).sort((a, b) => a.localeCompare(b));
    elPlayer.innerHTML = '<option value="">Tutti</option>' + names.map((n) => `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`).join("");
  }

  function escapeHtml(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function commonOptions() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "rgba(11, 16, 32, 0.95)",
          titleColor: COL_TEXT_MUTED,
          bodyColor: COL_TEXT_MAIN,
          borderColor: "rgba(255,255,255,0.10)",
          borderWidth: 1,
          padding: 10,
        },
      },
      scales: {
        x: { ticks: { color: COL_TEXT_MUTED }, grid: { color: "rgba(255,255,255,0.05)" } },
        y: { ticks: { color: COL_TEXT_MUTED }, grid: { color: "rgba(255,255,255,0.05)" } },
      },
    };
  }

  function renderBar(players, highlightName) {
    if (!canvasBar) return;
    if (barChart) barChart.destroy();

    const rows = [...players].filter((p) => p.games > 0).sort((a, b) => b.winRate - a.winRate);
    const labels = rows.map((p) => p.name);
    const values = rows.map((p) => p.winRate);

    const borderColors = rows.map((p) => pcGet(p.name));
    const bgColors = rows.map((p) => {
      const base = pcGet(p.name);
      if (!highlightName) return pcAlpha(base, 0.55);
      return pcAlpha(base, p.name === highlightName ? 0.90 : 0.15);
    });

    barChart = new Chart(canvasBar.getContext("2d"), {
      type: "bar",
      plugins: [barValueLabels],
      data: {
        labels,
        datasets: [{
          label: "Winrate",
          data: values,
          backgroundColor: bgColors,
          borderColor: borderColors,
          borderWidth: 1,
          barPercentage: 0.7,
        }],
      },
      options: {
        ...commonOptions(),
        indexAxis: "y",
        scales: {
          x: {
            min: 0,
            max: MAX_Y_PLOTS,
            grace: 0, // niente extra spazio sopra
            ticks: { color: COL_TEXT_MUTED, callback: (v) => `${v}%` },
            grid: { color: "rgba(255,255,255,0.05)" },
          },
          y: { ticks: { color: COL_TEXT_MUTED }, grid: { display: false } },
        },
        onClick: (evt, elements, chart) => {
          if (!elements?.length) return;
          const idx = elements[0].index;
          const player = chart?.data?.labels?.[idx];
          if (!player || !elPlayer) return;
          elPlayer.value = player;
          // Reuse existing wiring: the change handler triggers update() and the bubble focus.
          elPlayer.dispatchEvent(new Event("change"));
        },

        plugins: {
          
          barValueLabels: {},...commonOptions().plugins,
          tooltip: {
            ...commonOptions().plugins.tooltip,
            callbacks: {
              title: (items) => items?.[0]?.label || "",
              label: (ctx) => {
                const p = rows[ctx.dataIndex];
                return `Winrate: ${p.winRate.toFixed(1)}%`;
              },
              afterLabel: (ctx) => {
                const p = rows[ctx.dataIndex];
                return `Vittorie: ${p.wins} · Partite: ${p.games}`;
              },
            },
          },
        },
      },
    });
  }

  function renderBubble(players, highlightName) {
    if (!canvasBubble) return;
    if (bubbleChart) bubbleChart.destroy();

    const isFocus = !!highlightName;
    const rows = isFocus
      ? computeCommandersForPlayer(highlightName).filter((c) => c.games > 0)
      : [...players].filter((p) => p.games > 0);

    const maxGames = Math.max(1, ...rows.map((r) => r.games));

    
// Build points. In focus-mode (player -> commanders), multiple commanders can share the same (games, winRate)
// and end up perfectly overlapping. Apply a tiny deterministic "jitter" to separate overlaps so tooltips work reliably.
const basePoints = rows.map((r) => ({
  x: r.games,
  y: r.winRate,
  r: 11,
  _row: r,
  _mode: isFocus ? "commander" : "player",
  _player: highlightName || null,
  _rawX: r.games,
  _rawY: r.winRate,
}));

if (isFocus) {
  const groups = new Map();
  for (const pt of basePoints) {
    const key = `${pt.x}|${pt.y}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(pt);
  }
  for (const pts of groups.values()) {
    if (pts.length <= 1) continue;
    const m = pts.length;
    // offsets in data units (small but enough to separate hover targets)
    const dx = 0.25;   // quarter-game: visually tiny, but distinct hit-box
    const dy = 0.6;    // 0.6% winrate
    for (let i = 0; i < m; i++) {
      const ang = (2 * Math.PI * i) / m;
      pts[i].x = pts[i]._rawX + dx * Math.cos(ang);
      pts[i].y = pts[i]._rawY + dy * Math.sin(ang);
    }
  }
}

const points = basePoints;

    bubbleChart = new Chart(canvasBubble.getContext("2d"), {
      type: "bubble",
      data: {
        datasets: [{
          label: isFocus ? "Commanders" : "Players",
          data: points,
          backgroundColor: points.map((pt) => {
            if (pt._mode === "commander") {
              const base = pcGet(pt._player);
              return pcAlpha(base, 0.32);
            }
            const base = pcGet(pt._row.name);
            if (!highlightName) return pcAlpha(base, 0.30);
            return pcAlpha(base, pt._row.name === highlightName ? 0.45 : 0.12);
          }),
          borderColor: points.map((pt) => {
            if (pt._mode === "commander") return pcGet(pt._player);
            return pcGet(pt._row.name);
          }),
          borderWidth: points.map((pt) => {
            if (pt._mode === "commander") return 1;
            return (highlightName && pt._row.name === highlightName) ? 2 : 1;
          }),
        }],
      },
      options: {
        ...commonOptions(),
        scales: {
          x: {
            min: 0,
            suggestedMax: maxGames * 1.15,
            title: { display: true, text: "Partite", color: COL_TEXT_MUTED },
            ticks: { color: COL_TEXT_MUTED },
            grid: { color: "rgba(255,255,255,0.05)" },
          },
          y: {
            min: isFocus ? -10 : 0,
            max: isFocus ? 110 : 65,          // no-focus: zoom 0–65
            grace: 0,
            title: { display: true, text: "Winrate (%)", color: COL_TEXT_MUTED },
            ticks: {
              color: COL_TEXT_MUTED,
              // Nasconde eventuali tick "artificiali" (es. negativi) se Chart.js li produce
              callback: (v) => (v < 0 || v > 100) ? "" : `${v}%`,
              // opzionale (consigliato): rende la scala leggibile e stabile
              stepSize: 10,
            },
            grid: { color: "rgba(255,255,255,0.05)" },
          },
        },
        plugins: {
          ...commonOptions().plugins,
          tooltip: {
            ...commonOptions().plugins.tooltip,
            callbacks: {
              title: (items) => {
                const raw = items?.[0]?.raw;
                if (!raw) return "";
                if (raw._mode === "commander") return raw._row?.commander || "";
                return raw._row?.name || "";
              },
              label: (ctx) => {
                const r = ctx.raw._row;
                return `Winrate: ${r.winRate.toFixed(1)}% · Vittorie: ${r.wins} · Partite: ${r.games}`;
              },
            },
          },
        },
      },
    });
  }

  function update() {
    const players = computePlayers();
    const chosen = elPlayer ? elPlayer.value : "";

    if (elHint) {
      elHint.textContent = chosen
        ? `Selezionato: ${chosen}`
        : "";
    }

    renderBar(players, chosen || null);
    renderBubble(players, chosen || null);
  }

  async function init() {
    try {
      const res = await fetch("../data/stats.v1.json", { cache: "no-cache" });
      stats = await res.json();

      if (elMeta && stats?.generated_utc) {
        elMeta.textContent = `Generato il: ${stats.generated_utc}`;
      }

      const players = computePlayers();
      fillPlayerSelect(players);

      if (elPlayer) elPlayer.addEventListener("change", update);

      update();
    } catch (e) {
      console.error("Stats init error:", e);
      if (elHint) elHint.textContent = "Errore nel caricamento dei dati.";
    }
  }

  window.addEventListener("DOMContentLoaded", init);
})();
