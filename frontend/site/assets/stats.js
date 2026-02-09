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


// --- Plugin: draw symmetric error bars (in data units) for bar charts ---
const errorBars = {
  id: "errorBars",
  afterDatasetsDraw(chart) {
    const ctx = chart.ctx;
    const ds = chart.data.datasets?.[0];
    const errs = ds?.errorBars;
    if (!errs || !Array.isArray(errs)) return;

    // Optional helpers provided by the dataset
    const zeroMarkers = Array.isArray(ds.zeroMarkers) ? ds.zeroMarkers : null;
    const ciStroke = (ds.ciColor && String(ds.ciColor).trim()) ? String(ds.ciColor).trim() : null;

    const meta = chart.getDatasetMeta(0);
    const xScale = chart.scales.x;
    const yScale = chart.scales.y;
    if (!meta || !xScale || !yScale) return;

    ctx.save();
    ctx.lineWidth = 2;
    // Use dataset CI color (preferred) or fall back to the current text color.
    ctx.strokeStyle = ciStroke || getComputedStyle(document.documentElement).getPropertyValue('--fg').trim() || '#e8eaed';

    meta.data.forEach((elem, i) => {
      const err = Number(errs[i] ?? 0);
      const val = Number(ds.data[i] ?? 0);
      if (!isFinite(val)) return;

      // For horizontal bars, Chart.js uses indexAxis: 'y'
      const y = elem.y;
      // Keep 0-axis marker inside the plot area (Chart.js may place 0 slightly outside)
      const xZero = Math.max(chart.chartArea.left + 2, xScale.getPixelForValue(0));

      // Draw CI only when > 0
      if (isFinite(err) && err > 0) {
        const x0 = xScale.getPixelForValue(Math.max(0, val - err));
        const x1 = xScale.getPixelForValue(Math.min(100, val + err));
        const cap = 6;

        ctx.beginPath();
        ctx.moveTo(x0, y);
        ctx.lineTo(x1, y);
        ctx.moveTo(x0, y - cap);
        ctx.lineTo(x0, y + cap);
        ctx.moveTo(x1, y - cap);
        ctx.lineTo(x1, y + cap);
        ctx.stroke();
      }

      // Explicit marker for 0% winrate (so it never "disappears")
      if (zeroMarkers && zeroMarkers[i]) {
        // Small marker at 0% so it never "disappears": short hairline + dot.
        // Draw slightly inside the plot area for maximum visibility.
        ctx.save();

        const x0 = xZero + 2;
        const x1 = xZero + 18;

        // Hairline
        ctx.lineWidth = 4;
        ctx.beginPath();
        ctx.moveTo(x0, y);
        ctx.lineTo(x1, y);
        ctx.stroke();

        // Dot (centered on the hairline)
        const r = 5;
        ctx.beginPath();
        ctx.arc((x0 + x1) / 2, y, r, 0, Math.PI * 2);
        ctx.fillStyle = ciStroke || ctx.strokeStyle;
        ctx.fill();
        // Inner highlight to stand out on dark bars
        ctx.beginPath();
        ctx.arc((x0 + x1) / 2, y, 2.2, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(255,255,255,0.85)";
        ctx.fill();

        ctx.restore();
      }
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
  const elMinGames = $("#fMinGames");
  const elHeatBody = $("#pcHeatBody");

  let stats = null;

  function _dateKey(s) {
    return (s || "").slice(0, 10);
  }

  function getPeriodLabel(games) {
    if (!Array.isArray(games) || games.length === 0) return null;
    let min = null, max = null;
    for (const g of games) {
      const d = _dateKey(g?.played_at);
      if (!d) continue;
      if (min === null || d < min) min = d;
      if (max === null || d > max) max = d;
    }
    return (min && max) ? `${min} → ${max}` : null;
  }

  let barChart = null;
  let bubbleChart = null;

  const COL_TEXT_MUTED = "#aab3d3";
  const COL_TEXT_MAIN = "#e9ecf7";
  // Default cap for percent-like plots (used as a safety net only)
  const MAX_Y_PLOTS = 100

  function pcGet(name) {
    return (window.PlayerColors && window.PlayerColors.get) ? window.PlayerColors.get(name) : "#9CA3AF";
  }

  function pcAlpha(color, alpha) {
    return (window.PlayerColors && window.PlayerColors.withAlpha) ? window.PlayerColors.withAlpha(color, alpha) : color;
  }

  // Darken a #RRGGBB color by multiplying RGB channels by `factor` (0..1).
  function darkenHex(hex, factor) {
    const h = String(hex || "").trim();
    if (!h.startsWith("#") || h.length !== 7) return hex;
    const r = parseInt(h.slice(1, 3), 16);
    const g = parseInt(h.slice(3, 5), 16);
    const b = parseInt(h.slice(5, 7), 16);
    if (![r, g, b].every(Number.isFinite)) return hex;
    const clamp = (x) => Math.max(0, Math.min(255, Math.round(x)));
    const rr = clamp(r * factor);
    const gg = clamp(g * factor);
    const bb = clamp(b * factor);
    const toHex = (x) => x.toString(16).padStart(2, "0");
    return `#${toHex(rr)}${toHex(gg)}${toHex(bb)}`;
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
  function getPlayerBaselineWinRate(playerName) {
    const rows = Array.isArray(stats?.by_player) ? stats.by_player : [];

    // Exact player baseline = wins/games from by_player (stable, no reliance on schema-specific fields)
    if (playerName) {
      const r = rows.find((x) => x && String(x.player) === String(playerName));
      if (r) {
        const g = asNum(r.games, 0);
        const w = asNum(r.wins, 0);
        if (g > 0) return (100 * w) / g;
      }
    }

    // Global baseline weighted by games
    let gsum = 0;
    let wsum = 0;
    for (const r of rows) {
      const g = asNum(r.games, 0);
      const w = asNum(r.wins, 0);
      if (g > 0) { gsum += g; wsum += w; }
    }
    return gsum > 0 ? (100 * wsum) / gsum : 0;
  }

  function computeCommandersAll() {
    const rows = Array.isArray(stats?.by_player_commander) ? stats.by_player_commander : [];
    const byCommander = new Map();
    for (const r of rows) {
      if (!r) continue;
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


  function renderPlayerCommanderWinrateChart(playerName) {
    const canvas = $("#pcWinChart");
    const hint = $("#pcWinChartHint");
    if (!canvas || !hint) return;

    // Only active when a specific player is selected (not "Tutti i giocatori")
    if (!playerName) {
      if (window.__pcWinChart) {
        window.__pcWinChart.destroy();
        window.__pcWinChart = null;
      }
      hint.textContent = "Seleziona un giocatore per vedere il winrate per commander.";
      hint.style.display = "block";
      return;
    }

    const minGames = elMinGames ? Math.max(1, parseInt(elMinGames.value || "1", 10)) : 1;

    const rows = computeCommandersForPlayer(playerName)
        .filter((r) => asNum(r.games, 0) >= minGames);

    if (!rows.length) {
      if (window.__pcWinChart) {
        window.__pcWinChart.destroy();
        window.__pcWinChart = null;
      }
      hint.textContent = `Nessun commander con almeno ${minGames} partite per ${playerName}.`;
      hint.style.display = "block";
      return;
    }

    // Sort by winrate desc, then games desc
    rows.sort((a, b) => {
      const wa = asNum(a.winRate, 0);
      const wb = asNum(b.winRate, 0);
      if (wb !== wa) return wb - wa;
      return asNum(b.games, 0) - asNum(a.games, 0);
    });

    const labels = rows.map((r) => r.commander);
    const data = rows.map((r) => asNum(r.winRate, 0));

    // Error bars: 95% CI for a proportion (normal approximation) in percentage points.
    // ci = 1.96 * sqrt(p*(1-p)/n) * 100
    const errors = rows.map((r) => {
      const n = Math.max(1, asNum(r.games, 0));
      const p = Math.min(1, Math.max(0, asNum(r.winRate, 0) / 100));
      const se = Math.sqrt((p * (1 - p)) / n);
      return 1.96 * se * 100;
    });

    const base = pcGet(playerName);
    // Make the bar slightly darker than the CI lines for contrast.
    const barColor = pcAlpha(darkenHex(base, 0.72), 0.95);
    const ciColor = pcAlpha(darkenHex(base, 0.90), 0.95);

    // Mark rows that have games but zero wins (to draw explicit 0% marker).
    const zeroMarkers = rows.map((r) => asNum(r.games, 0) > 0 && asNum(r.wins, 0) === 0);

    hint.style.display = "none";

    const ctx = canvas.getContext("2d");

    if (window.__pcWinChart) {
      // update
      window.__pcWinChart.data.labels = labels;
      window.__pcWinChart.data.datasets[0].data = data;
      window.__pcWinChart.data.datasets[0].backgroundColor = barColor;
      window.__pcWinChart.data.datasets[0].borderColor = barColor;
      window.__pcWinChart.data.datasets[0].errorBars = errors;
      window.__pcWinChart.data.datasets[0].ciColor = ciColor;
      window.__pcWinChart.data.datasets[0].zeroMarkers = zeroMarkers;
      window.__pcWinChart.update();
      return;
    }

    window.__pcWinChart = new Chart(ctx, {
      type: "bar",
      data: {
        labels,
        datasets: [{
          label: "Winrate (%)",
          data,
          errorBars: errors,
          ciColor: ciColor,
          zeroMarkers,
          backgroundColor: barColor,
          borderColor: barColor,
          borderWidth: 1,
          borderRadius: 10,
          barThickness: 14,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: "y", // horizontal bars
        scales: {
          x: {
            min: 0,
            max: 100,
            ticks: {
              callback: (v) => `${v}%`
            },
            grid: { display: true }
          },
          y: {
            ticks: {
              autoSkip: false,
              // Keep labels readable even when many commanders
              font: (ctx) => {
                const n = (ctx.chart?.data?.labels?.length || 1);
                const size = n > 18 ? 10 : (n > 12 ? 11 : 12);
                return { size };
              }
            },
            grid: { display: false }
          }
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (c) => {
                const i = c.dataIndex;
                const r = rows[i];
                const wr = asNum(r.winRate, 0);
                const g = asNum(r.games, 0);
                const w = asNum(r.wins, 0);
                const ci = errors[i];
                return ` ${wr.toFixed(1)}%  ·  ${w}/${g}  ·  ±${ci.toFixed(1)}pp (95% CI)`;
              }
            }
          }
        }
      },
      plugins: [errorBars]
    });
  }


  function fillPlayerSelect(players) {
    if (!elPlayer) return;
    const names = Array.from(new Set(players.map((p) => p.name))).sort((a, b) => a.localeCompare(b));
    elPlayer.innerHTML = '<option value="">Tutti i giocatori</option>' + names.map((n) => `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`).join("");
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

    const vMax = Math.max(0, ...values.map((v) => Number(v) || 0));
    const scaleMax = vMax > 0 ? Math.min(100, vMax + 0.10 * vMax) : 10;

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
            max: Math.min(MAX_Y_PLOTS, scaleMax),
            grace: 0, // niente extra spazio sopra
            position: "top",
            ticks: {
              color: COL_TEXT_MUTED,
              stepSize: 10,
              callback: (v) => {
                const n = typeof v === "string" ? Number(v) : v;
                if (!Number.isFinite(n)) return "";

                // elimina roba tipo 1.7763568394002505e-15 / -0
                const snapped = Math.abs(n) < 1e-6 ? 0 : n;

                // scegli tu: 0 decimali oppure 1
                return `${snapped.toFixed(1)}%`;   // oppure toFixed(0)
              },
            },
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
    const yMax = Math.max(0, ...rows.map((r) => Number(r.winRate) || 0));
    const yScaleMax = yMax > 0 ? Math.min(100, yMax + 0.10 * yMax) : 10;


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
            position: "top",
            title: { display: true, text: "Partite", color: COL_TEXT_MUTED },
            ticks: { color: COL_TEXT_MUTED },
            grid: { color: "rgba(255,255,255,0.05)" },
          },
          y: {
            min: -10,
            max: yScaleMax + yScaleMax * 0.1,
            grace: 0,
            title: { display: true, text: "Winrate (%)", color: COL_TEXT_MUTED },
            ticks: {
              color: COL_TEXT_MUTED,
              // Nasconde eventuali tick "artificiali" (es. negativi) se Chart.js li produce
              callback: (v) => {
                const n = typeof v === "string" ? Number(v) : v;
                if (!Number.isFinite(n) || n < 0 || n > 100) return "";
                return `${Math.round(n*10)/10}%`; //
              },
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
          ? `Stai visualizzando: ${chosen} (focus sui commander)`
          : "Stai visualizzando: Tutti i giocatori";
    }

    renderBar(players, chosen || null);
    renderBubble(players, chosen || null);


    renderPlayerCommanderWinrateChart(chosen || "");
  }

  async function init() {
    try {
      const res = await fetch("../data/stats.v1.json", { cache: "no-cache" });
      stats = await res.json();

      if (elMeta && stats?.generated_utc) {
        const games = stats?.counts?.games;
        const entries = stats?.counts?.entries;
        const period = getPeriodLabel(stats?.games);
        const gen = stats?.generated_utc;
        const parts = [];
        if (period) parts.push(`Periodo: ${period}`);
        if (Number.isFinite(games)) parts.push(`Partite: ${games}`);
        if (Number.isFinite(entries)) parts.push(`Entries: ${entries}`);
        if (gen) parts.push(`Gen: ${gen}`);
        // Mantieni il riepilogo nei dati ma non mostrarlo in UI
        const summary = parts.join(" · ");
        elMeta.dataset.summary = summary;
        elMeta.textContent = "";
        elMeta.style.display = "none";
      }

      const players = computePlayers();
      fillPlayerSelect(players);

      if (elPlayer) elPlayer.addEventListener("change", update);
      if (elMinGames) {
        elMinGames.addEventListener("input", update);
        elMinGames.addEventListener("change", update);
      }

      update();
    } catch (e) {
      console.error("Stats init error:", e);
      if (elHint) elHint.textContent = "Errore nel caricamento dei dati.";
    }
  }

  window.addEventListener("DOMContentLoaded", init);
})();
