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
  const elTrendPlayer = $("#trendPlayer");
  const elTrendCommanderChips = $("#trendCommanderChips");
  const elTrendCommanderClear = $("#trendCommanderClear");
  const elTrendCommanderSub = $("#trendCommanderSub");
  const elTrendHint = $("#trendHint");
  const canvasTrend = $("#trendChart");
  const canvasPod = $("#podChart");
  const elPodHint = $("#podHint");
  const elPodMatrix = $("#podMatrix");
  const elTrendSummary = $("#trendSummary");

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
  let trendChart = null;
  let podChart = null;

  const COL_TEXT_MUTED = "#aab3d3";
  const COL_TEXT_MAIN = "#e9ecf7";
  const POD_SIZE_COLORS = {
    3: "#4e79a7",
    4: "#f28e2b",
    5: "#59a14f",
    6: "#e15759",
  };
  // Default cap for percent-like plots (used as a safety net only)
  const MAX_Y_PLOTS = 100

  function fmtPct(x, digits = 1) {
    const n = Number(x);
    if (!Number.isFinite(n)) return "—";
    return `${n.toFixed(digits)}%`;
  }

  function fmtSigned(x, digits = 1) {
    const n = Number(x);
    if (!Number.isFinite(n)) return "—";
    const sign = n > 0 ? "+" : "";
    return `${sign}${n.toFixed(digits)}`;
  }

  function pcGet(name) {
    return (window.PlayerColors && window.PlayerColors.get) ? window.PlayerColors.get(name) : "#9CA3AF";
  }

  function pcAlpha(color, alpha) {
    return (window.PlayerColors && window.PlayerColors.withAlpha) ? window.PlayerColors.withAlpha(color, alpha) : color;
  }

  function podSizeColor(podSize) {
    const n = Number(podSize);
    return POD_SIZE_COLORS[n] || "#9c755f";
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

  function mixHex(hex, targetHex, amount) {
    const h1 = String(hex || "").trim();
    const h2 = String(targetHex || "").trim();
    if (!h1.startsWith("#") || h1.length !== 7 || !h2.startsWith("#") || h2.length !== 7) return hex;
    const c1 = [parseInt(h1.slice(1, 3), 16), parseInt(h1.slice(3, 5), 16), parseInt(h1.slice(5, 7), 16)];
    const c2 = [parseInt(h2.slice(1, 3), 16), parseInt(h2.slice(3, 5), 16), parseInt(h2.slice(5, 7), 16)];
    if (![...c1, ...c2].every(Number.isFinite)) return hex;
    const t = Math.max(0, Math.min(1, Number(amount) || 0));
    const clamp = (x) => Math.max(0, Math.min(255, Math.round(x)));
    const mixed = c1.map((v, i) => clamp(v + (c2[i] - v) * t));
    const toHex = (x) => x.toString(16).padStart(2, "0");
    return `#${toHex(mixed[0])}${toHex(mixed[1])}${toHex(mixed[2])}`;
  }

  function commanderVariantColor(baseColor, idx, total) {
    const base = String(baseColor || "").trim();
    const n = Math.max(1, Number(total) || 1);
    const i = Math.max(0, Number(idx) || 0);
    if (!base.startsWith("#") || base.length !== 7) {
      const alpha = Math.max(0.35, 0.92 - i * 0.12);
      return pcAlpha(baseColor, alpha);
    }
    if (n === 1) return base;
    const palette = [
      mixHex(base, '#ffffff', 0.18),
      mixHex(base, '#ffffff', 0.08),
      base,
      mixHex(base, '#000000', 0.10),
      mixHex(base, '#000000', 0.20),
      mixHex(base, '#ffffff', 0.26),
      mixHex(base, '#000000', 0.28),
    ];
    return palette[i % palette.length];
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
    const names = Array.from(new Set(players.map((p) => p.name))).sort((a, b) => a.localeCompare(b));
    if (elPlayer) {
      elPlayer.innerHTML = '<option value="">Tutti i giocatori</option>' + names.map((n) => `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`).join("");
    }
    if (elTrendPlayer) {
      elTrendPlayer.innerHTML = '<option value="">Seleziona un giocatore</option>' + names.map((n) => `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`).join("");
    }
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
              display: false,
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
              max: Math.ceil(yScaleMax * 1.1 / 10) * 10,
              // Nasconde eventuali tick "artificiali" (es. negativi) se Chart.js li produce
              callback: (v) => {
                const n = typeof v === "string" ? Number(v) : v;
                if (!Number.isFinite(n) || n < 0 || n > 100) return "";
                return `${Math.round(n / 10) * 10}%`;
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


  function computeCommanderPodRows(playerName, minGames) {
    const games = Array.isArray(stats?.games) ? stats.games : [];
    const byKey = new Map();
    for (const g of games) {
      const winner = String(g?.winner_player || "");
      const entries = Array.isArray(g?.entries) ? g.entries : [];
      const podSize = entries.length;
      if (!podSize) continue;
      const expected = 1 / podSize;
      for (const e of entries) {
        if (String(e?.player || "") !== String(playerName)) continue;
        const commander = String(e?.commander || "").trim();
        if (!commander) continue;
        const key = `${commander}||${podSize}`;
        const cur = byKey.get(key) || { commander, podSize, games: 0, wins: 0, expectedWins: 0 };
        cur.games += 1;
        cur.wins += winner === playerName ? 1 : 0;
        cur.expectedWins += expected;
        byKey.set(key, cur);
      }
    }
    const minN = Math.max(1, parseInt(minGames || "1", 10));
    return Array.from(byKey.values())
      .filter((r) => r.games >= minN)
      .map((r) => {
        const rawWr = r.games > 0 ? (100 * r.wins) / r.games : 0;
        const expectedWr = r.games > 0 ? (100 * r.expectedWins) / r.games : 0;
        const winsAboveExpected = r.wins - r.expectedWins;
        return {
          ...r,
          rawWr,
          expectedWr,
          deltaWr: rawWr - expectedWr,
          winsAboveExpected,
        };
      })
      .sort((a, b) => a.commander.localeCompare(b.commander) || a.podSize - b.podSize);
  }

  function renderPodMatrix(playerName) {
    if (!elPodMatrix || !elPodHint) return;
    const minGames = elMinGames ? Math.max(1, parseInt(elMinGames.value || "1", 10)) : 1;
    if (!playerName) {
      elPodMatrix.innerHTML = "";
      elPodHint.textContent = "Seleziona un giocatore per vedere la matrice commander × pod size.";
      if (podChart) { podChart.destroy(); podChart = null; }
      return;
    }

    const rows = computeCommanderPodRows(playerName, minGames);
    if (!rows.length) {
      elPodMatrix.innerHTML = "";
      elPodHint.textContent = `Nessun dato con almeno ${minGames} partite per commander/pod size.`;
      if (podChart) { podChart.destroy(); podChart = null; }
      return;
    }

    elPodHint.textContent = `${playerName}: ${rows.length} combinazioni commander/pod size con almeno ${minGames} partite.`;
    const podSizes = Array.from(new Set(rows.map((r) => r.podSize))).sort((a, b) => a - b);
    const commanders = Array.from(new Set(rows.map((r) => r.commander))).sort((a, b) => a.localeCompare(b));
    const byKey = new Map(rows.map((r) => [`${r.commander}||${r.podSize}`, r]));

    const head = `<tr><th>Commander</th><th>Tot</th>${podSizes.map((n) => `<th>${n}p</th>`).join("")}</tr>`;
    const body = commanders.map((commander) => {
      const cRows = rows.filter((r) => r.commander === commander);
      const totalGames = cRows.reduce((a, r) => a + r.games, 0);
      const totalWins = cRows.reduce((a, r) => a + r.wins, 0);
      const totalExpected = cRows.reduce((a, r) => a + r.expectedWins, 0);
      const totalWae = totalWins - totalExpected;
      const tClass = totalWae > 0.0001 ? "pos" : (totalWae < -0.0001 ? "neg" : "");
      const cells = podSizes.map((pod) => {
        const r = byKey.get(`${commander}||${pod}`);
        if (!r) return '<td class="muted">—</td>';
        const cls = r.winsAboveExpected > 0.0001 ? "pos" : (r.winsAboveExpected < -0.0001 ? "neg" : "");
        return `<td title="${escapeHtml(commander)} · ${pod} player: ${r.wins}/${r.games}, WR ${fmtPct(r.rawWr)}, atteso ${fmtPct(r.expectedWr)}"><span class="pod-wae ${cls}">${fmtSigned(r.winsAboveExpected, 1)}</span><span class="pod-cell-sub">${r.wins}/${r.games} · ${fmtPct(r.rawWr, 0)}</span></td>`;
      }).join("");
      return `<tr><td>${escapeHtml(commander)}</td><td><span class="pod-wae ${tClass}">${fmtSigned(totalWae, 1)}</span><span class="pod-cell-sub">${totalWins}/${totalGames}</span></td>${cells}</tr>`;
    }).join("");
    elPodMatrix.innerHTML = `<table class="pod-matrix">${head}${body}</table>`;

    renderPodChart(playerName, rows, podSizes);
  }

  function renderPodChart(playerName, rows, podSizes) {
    if (!canvasPod) return;
    if (podChart) { podChart.destroy(); podChart = null; }
    const byCommander = new Map();
    for (const r of rows) {
      const cur = byCommander.get(r.commander) || { commander: r.commander, games: 0, absWae: 0 };
      cur.games += r.games;
      cur.absWae += Math.abs(r.winsAboveExpected);
      byCommander.set(r.commander, cur);
    }
    const topCommanders = Array.from(byCommander.values())
      .sort((a, b) => (b.games - a.games) || (b.absWae - a.absWae) || a.commander.localeCompare(b.commander))
      .slice(0, 10)
      .map((r) => r.commander);
    if (!topCommanders.length) return;

    const byKey = new Map(rows.map((r) => [`${r.commander}||${r.podSize}`, r]));
    const datasets = podSizes.map((pod) => {
      const color = podSizeColor(pod);
      return {
        label: `${pod} player`,
        data: topCommanders.map((c) => {
          const r = byKey.get(`${c}||${pod}`);
          return r ? Number(r.winsAboveExpected.toFixed(3)) : null;
        }),
        backgroundColor: pcAlpha(color, 0.82),
        borderColor: color,
        borderWidth: 1,
        _podSize: pod,
      };
    });

    podChart = new Chart(canvasPod.getContext("2d"), {
      type: "bar",
      data: { labels: topCommanders, datasets },
      options: {
        ...commonOptions(),
        scales: {
          x: { ticks: { color: COL_TEXT_MUTED, maxRotation: 35, minRotation: 0 }, grid: { display: false } },
          y: {
            ticks: { color: COL_TEXT_MUTED, callback: (v) => fmtSigned(v, 1) },
            grid: { color: "rgba(255,255,255,0.05)" },
            title: { display: true, text: "Wins Above Expected", color: COL_TEXT_MUTED },
          },
        },
        plugins: {
          ...commonOptions().plugins,
          legend: { display: true, labels: { color: COL_TEXT_MUTED } },
          tooltip: {
            ...commonOptions().plugins.tooltip,
            callbacks: {
              label: (ctx) => {
                const commander = ctx.chart.data.labels[ctx.dataIndex];
                const pod = ctx.dataset._podSize;
                const r = byKey.get(`${commander}||${pod}`);
                if (!r) return `${ctx.dataset.label}: —`;
                return `${ctx.dataset.label}: WAE ${fmtSigned(r.winsAboveExpected, 1)} · ${r.wins}/${r.games} · WR ${fmtPct(r.rawWr)} · atteso ${fmtPct(r.expectedWr)}`;
              },
            },
          },
        },
      },
    });
  }


  function getPlayerGameRows(playerName) {
    const games = Array.isArray(stats?.games) ? stats.games : [];
    const rows = [];
    for (const g of games) {
      const playedAt = String(g?.played_at || "").slice(0, 10);
      if (!playedAt) continue;
      const gameId = asNum(g?.id, 0);
      const winner = String(g?.winner_player || "");
      const entries = Array.isArray(g?.entries) ? g.entries : [];
      for (let idx = 0; idx < entries.length; idx += 1) {
        const e = entries[idx] || {};
        if (String(e.player || "") !== String(playerName)) continue;
        rows.push({
          playedAt,
          gameId,
          entryIdx: idx,
          commander: String(e.commander || "").trim(),
          podSize: entries.length,
          expected: entries.length > 0 ? 1 / entries.length : 0,
          win: winner === playerName ? 1 : 0,
        });
      }
    }
    rows.sort((a, b) => {
      if (a.playedAt !== b.playedAt) return a.playedAt.localeCompare(b.playedAt);
      if (a.gameId !== b.gameId) return a.gameId - b.gameId;
      return a.entryIdx - b.entryIdx;
    });
    return rows;
  }

  function getEligibleCommandersForTrend(playerName) {
    const rows = getPlayerGameRows(playerName);
    const byCommander = new Map();
    for (const r of rows) {
      if (!r.commander) continue;
      const cur = byCommander.get(r.commander) || { commander: r.commander, games: 0 };
      cur.games += 1;
      byCommander.set(r.commander, cur);
    }
    return Array.from(byCommander.values())
      .filter((r) => r.games >= 1)
      .sort((a, b) => (b.games - a.games) || a.commander.localeCompare(b.commander));
  }

  function getSelectedTrendCommanders() {
    if (!elTrendCommanderChips) return [];
    const btn = elTrendCommanderChips.querySelector('.trend-chip.is-selected');
    const commander = btn ? (btn.dataset.commander || '') : '';
    return commander ? [commander] : [];
  }

  function updateTrendCommanderSub(playerName, eligible) {
    if (!elTrendCommanderSub) return;
    if (!playerName) {
      elTrendCommanderSub.textContent = 'Mostra il totale player finché non selezioni un commander.';
      return;
    }
    if (!eligible.length) {
      elTrendCommanderSub.textContent = `${playerName} non ha ancora commander disponibili per il focus.`;
      return;
    }
    elTrendCommanderSub.textContent = `${eligible.length} commander eleggibili per ${playerName}. Tocca un commander per passare dal totale player al focus dedicato.`;
  }

  function fillTrendCommanderSelect(playerName) {
    const eligible = playerName ? getEligibleCommandersForTrend(playerName) : [];
    const prevSelected = getSelectedTrendCommanders()[0] || '';
    updateTrendCommanderSub(playerName, eligible);
    if (!elTrendCommanderChips) return;
    if (!playerName) {
      elTrendCommanderChips.innerHTML = '<div class="trend-chip-empty">Seleziona prima un giocatore.</div>';
      elTrendCommanderChips.classList.add('is-disabled');
      if (elTrendCommanderClear) elTrendCommanderClear.disabled = true;
      return;
    }
    if (!eligible.length) {
      elTrendCommanderChips.innerHTML = '<div class="trend-chip-empty">Nessun commander disponibile.</div>';
      elTrendCommanderChips.classList.add('is-disabled');
      if (elTrendCommanderClear) elTrendCommanderClear.disabled = true;
      return;
    }
    elTrendCommanderChips.classList.remove('is-disabled');
    const tone = pcGet(playerName);
    elTrendCommanderChips.innerHTML = eligible.map((item) => {
      const isSelected = prevSelected === item.commander;
      const selected = isSelected ? ' is-selected' : '';
      const bg = isSelected ? pcAlpha(tone, 0.18) : 'rgba(255,255,255,.04)';
      const border = isSelected ? pcAlpha(tone, 0.85) : 'rgba(255,255,255,.10)';
      const swatch = `style="--trend-chip-tone:${tone}; background:${bg}; border-color:${border};"`;
      return `<button type="button" class="trend-chip${selected}" data-commander="${escapeHtml(item.commander)}" ${swatch}><span class="trend-chip-swatch" aria-hidden="true"></span><span class="trend-chip-name">${escapeHtml(item.commander)}</span><span class="trend-chip-meta">${item.games}p</span></button>`;
    }).join('');
    if (elTrendCommanderClear) {
      elTrendCommanderClear.disabled = getSelectedTrendCommanders().length === 0;
    }
  }

  function weekStart(dateKey) {
    const d = new Date(`${dateKey}T00:00:00Z`);
    const day = d.getUTCDay();
    const diff = (day + 6) % 7;
    d.setUTCDate(d.getUTCDate() - diff);
    return d.toISOString().slice(0, 10);
  }

  function weeksBetweenInclusive(startKey, endKey) {
    const out = [];
    if (!startKey || !endKey) return out;
    let d = new Date(`${weekStart(startKey)}T00:00:00Z`);
    const end = new Date(`${weekStart(endKey)}T00:00:00Z`);
    while (d <= end) {
      out.push(d.toISOString().slice(0, 10));
      d.setUTCDate(d.getUTCDate() + 7);
    }
    return out;
  }

  function buildCumulativeSeries(gameRows) {
    const rows = Array.isArray(gameRows) ? gameRows : [];
    if (!rows.length) return null;
    let wins = 0;
    let expectedWins = 0;
    let cumulativeDelta = 0;
    const points = [];
    for (let i = 0; i < rows.length; i += 1) {
      const r = rows[i];
      const expected = Number.isFinite(Number(r.expected)) ? Number(r.expected) : 0;
      wins += r.win;
      expectedWins += expected;
      cumulativeDelta += r.win - expected;
      points.push({
        x: String(i + 1),
        y: Number(cumulativeDelta.toFixed(3)),
        wins,
        expectedWins: Number(expectedWins.toFixed(3)),
        games: i + 1,
        playedAt: r.playedAt,
        commander: r.commander,
        podSize: r.podSize,
        actual: r.win,
        expected,
      });
    }
    return points;
  }

  function summarizeCumulativeRows(rows) {
    const n = rows.length;
    const wins = rows.reduce((a, r) => a + (r.win ? 1 : 0), 0);
    const expectedWins = rows.reduce((a, r) => a + (Number(r.expected) || 0), 0);
    const wae = wins - expectedWins;
    return {
      games: n,
      wins,
      expectedWins,
      winsAboveExpected: wae,
      rawWr: n > 0 ? (100 * wins) / n : 0,
      expectedWr: n > 0 ? (100 * expectedWins) / n : 0,
    };
  }

  function renderTrendSummary(rows) {
    if (!elTrendSummary) return;
    if (!rows.length) {
      elTrendSummary.innerHTML = "";
      return;
    }
    const s = summarizeCumulativeRows(rows);
    const cards = [
      ["Partite", String(s.games)],
      ["Vittorie", String(s.wins)],
      ["Expected wins", s.expectedWins.toFixed(1)],
      ["Wins above expected", fmtSigned(s.winsAboveExpected, 1)],
      ["WR vs atteso", `${fmtPct(s.rawWr)} / ${fmtPct(s.expectedWr)}`],
    ];
    elTrendSummary.innerHTML = cards.map(([label, value]) => `<div class="trend-summary-card"><div class="trend-summary-label">${label}</div><div class="trend-summary-value">${value}</div></div>`).join("");
  }


  function buildTrendDatasets(playerName, selectedCommanders) {
    const base = getPlayerGameRows(playerName);
    const chosen = Array.isArray(selectedCommanders) ? selectedCommanders.filter(Boolean) : [];
    const targetRows = chosen.length ? base.filter((r) => r.commander === chosen[0]) : base;
    const pts = buildCumulativeSeries(targetRows);
    if (!pts) return { datasets: [], rows: targetRows };
    const color = pcGet(playerName);
    const label = chosen.length ? `${chosen[0]} · cumulata WAE` : `${playerName} · cumulata WAE`;
    return {
      rows: targetRows,
      datasets: [{
        label,
        data: pts,
        borderColor: color,
        backgroundColor: pcAlpha(color, 0.16),
        pointBackgroundColor: color,
        pointBorderColor: color,
        borderWidth: 2,
      }],
    };
  }


  function renderTrendChart() {
    if (!canvasTrend || !elTrendHint) return;
    const playerName = elTrendPlayer ? elTrendPlayer.value : "";
    if (!playerName) {
      if (trendChart) {
        trendChart.destroy();
        trendChart = null;
      }
      renderTrendSummary([]);
      fillTrendCommanderSelect("");
      elTrendHint.textContent = "Nessun giocatore selezionato.";
      return;
    }

    fillTrendCommanderSelect(playerName);
    const selectedCommanders = getSelectedTrendCommanders();
    const built = buildTrendDatasets(playerName, selectedCommanders);
    const datasets = built.datasets || [];
    const targetRows = built.rows || [];

    if (!datasets.length) {
      if (trendChart) {
        trendChart.destroy();
        trendChart = null;
      }
      renderTrendSummary([]);
      elTrendHint.textContent = selectedCommanders.length
        ? `Nessuna partita disponibile per il commander selezionato.`
        : `${playerName} non ha ancora partite disponibili per la cumulata.`;
      return;
    }

    renderTrendSummary(targetRows);
    elTrendHint.textContent = selectedCommanders.length
      ? `${playerName}: cumulata del commander selezionato.`
      : `${playerName}: cumulata totale player.`;

    const allY = datasets.flatMap((ds) => ds.data.map((p) => Number(p.y) || 0));
    const yMin = Math.min(0, ...allY);
    const yMax = Math.max(0, ...allY);
    const pad = Math.max(0.5, (yMax - yMin) * 0.15);

    const ctx = canvasTrend.getContext("2d");
    if (trendChart) trendChart.destroy();
    trendChart = new Chart(ctx, {
      type: "line",
      data: { datasets },
      options: {
        ...commonOptions(),
        maintainAspectRatio: false,
        parsing: false,
        elements: {
          line: { tension: 0.12, cubicInterpolationMode: "monotone" },
          point: {
            radius: (ctx) => window.matchMedia('(max-width: 720px)').matches ? 0 : 2,
            hoverRadius: window.matchMedia('(max-width: 720px)').matches ? 7 : 5,
            hitRadius: window.matchMedia('(max-width: 720px)').matches ? 16 : 10,
          },
        },
        scales: {
          x: {
            type: "category",
            offset: true,
            labels: datasets[0].data.map((p) => p.x),
            ticks: {
              color: COL_TEXT_MUTED,
              maxRotation: 0,
              autoSkip: true,
              maxTicksLimit: window.matchMedia('(max-width: 720px)').matches ? 5 : 8,
            },
            grid: { color: "rgba(255,255,255,0.05)" },
            title: { display: true, text: "Partita progressiva", color: COL_TEXT_MUTED },
          },
          y: {
            min: yMin - pad,
            max: yMax + pad,
            ticks: { color: COL_TEXT_MUTED, callback: (v) => fmtSigned(v, 1) },
            grid: { color: "rgba(255,255,255,0.05)" },
            title: { display: true, text: "Wins Above Expected cumulato", color: COL_TEXT_MUTED },
          },
        },
        plugins: {
          ...commonOptions().plugins,
          legend: { display: false },
          tooltip: {
            ...commonOptions().plugins.tooltip,
            callbacks: {
              title: (items) => {
                const raw = items?.[0]?.raw || {};
                return raw.playedAt ? `Partita #${raw.games} · ${raw.playedAt}` : `Partita #${raw.games || ""}`;
              },
              label: (ctx) => {
                const raw = ctx.raw || {};
                return `${ctx.dataset.label}: ${fmtSigned(raw.y, 1)} WAE`;
              },
              afterLabel: (ctx) => {
                const raw = ctx.raw || {};
                const commander = raw.commander ? ` · ${raw.commander}` : "";
                return `Record cumulato: ${raw.wins}/${raw.games} · Expected wins: ${Number(raw.expectedWins || 0).toFixed(1)} · Pod: ${raw.podSize || "—"}${commander}`;
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
    renderPodMatrix(chosen || "");
    renderTrendChart();
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
      if (elTrendPlayer) {
        elTrendPlayer.addEventListener("change", () => {
          fillTrendCommanderSelect(elTrendPlayer.value || "");
          update();
        });
      }
      if (elTrendCommanderChips) {
        elTrendCommanderChips.addEventListener('click', (evt) => {
          const btn = evt.target.closest('.trend-chip');
          if (!btn) return;
          const wasSelected = btn.classList.contains('is-selected');
          elTrendCommanderChips.querySelectorAll('.trend-chip.is-selected').forEach((el) => {
            el.classList.remove('is-selected');
          });
          if (!wasSelected) btn.classList.add('is-selected');
          if (elTrendCommanderClear) {
            elTrendCommanderClear.disabled = getSelectedTrendCommanders().length === 0;
          }
          update();
        });
      }
      if (elTrendCommanderClear) {
        elTrendCommanderClear.addEventListener('click', () => {
          if (!elTrendCommanderChips) return;
          elTrendCommanderChips.querySelectorAll('.trend-chip.is-selected').forEach((el) => el.classList.remove('is-selected'));
          elTrendCommanderClear.disabled = true;
          update();
        });
      }

      document.querySelectorAll('[data-stats-tab]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const key = btn.dataset.statsTab;
          document.querySelectorAll('[data-stats-tab]').forEach((b) => b.classList.toggle('is-active', b === btn));
          document.querySelectorAll('[data-stats-panel]').forEach((panel) => panel.classList.toggle('is-active', panel.dataset.statsPanel === key));
          setTimeout(() => {
            [barChart, bubbleChart, window.__pcWinChart, podChart, trendChart].forEach((chart) => {
              if (chart && chart.resize) chart.resize();
            });
          }, 0);
        });
      });

      update();
    } catch (e) {
      console.error("Stats init error:", e);
      if (elHint) elHint.textContent = "Errore nel caricamento dei dati.";
    }
  }

  window.addEventListener("DOMContentLoaded", init);
})();
