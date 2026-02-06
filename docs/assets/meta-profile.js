/* Meta Profile (vettori)
   - X: MDI  (delta player bracket vs media tavolo, player escluso)  -> signed
   - Y: OEWR_Z (Over-Expected Win Rate: actual - expected, expected=softmax(bracket)) -> signed
   - Ogni player è una freccia che parte dall'origine (0,0) e punta verso (MDI, OEWR)
   - La bolla in punta è proporzionale al volume di partite (games_total)
*/

(function () {
  "use strict";

  const elMeta = document.getElementById("meta");
  const canvas = document.getElementById("mdiMpiPlayers");

  let chart = null;
  let stats = null;

function _dateKey(s){ return (s||"").slice(0,10); }
function getPeriodLabel(games){
  if(!Array.isArray(games) || games.length===0) return null;
  let min=null, max=null;
  for(const g of games){
    const d=_dateKey(g?.played_at);
    if(!d) continue;
    if(min===null || d<min) min=d;
    if(max===null || d>max) max=d;
  }
  return (min&&max)?`${min} → ${max}`:null;
}

  function pcGet(name) {
    return (window.PlayerColors && window.PlayerColors.get) ? window.PlayerColors.get(name) : "#9CA3AF";
  }

  function pcAlpha(color, alpha) {
    return (window.PlayerColors && window.PlayerColors.withAlpha) ? window.PlayerColors.withAlpha(color, alpha) : color;
  }



  function clamp(x, lo, hi) {
    return x < lo ? lo : x > hi ? hi : x;
  }


  function isMobile() {
    return window.matchMedia && window.matchMedia("(max-width: 640px)").matches;
  }


  function supportsFullscreen() {
    return !!(document.fullscreenEnabled || document.webkitFullscreenEnabled);
  }
  function isFullscreen() {
    return !!(document.fullscreenElement || document.webkitFullscreenElement);
  }
  async function enterFullscreen(el) {
    if (el.requestFullscreen) return el.requestFullscreen();
    if (el.webkitRequestFullscreen) return el.webkitRequestFullscreen();
  }
  async function exitFullscreen() {
    if (document.exitFullscreen) return document.exitFullscreen();
    if (document.webkitExitFullscreen) return document.webkitExitFullscreen();
  }

  function setupFullscreenButton(cardEl, chartInstance) {
    if (!cardEl || !chartInstance) return;
    const tools = cardEl.querySelector(".head-tools");
    if (!tools) return;

    const btn = document.createElement("button");
    btn.className = "btn-ico";
    btn.type = "button";
    btn.title = "Fullscreen";
    btn.setAttribute("aria-label", "Fullscreen chart");
    btn.textContent = "⤢";
    tools.appendChild(btn);

    const sync = () => {
      const fs = isFullscreen();
      if (fs) cardEl.classList.add("chart-fs");
      else cardEl.classList.remove("chart-fs");
      setTimeout(() => chartInstance.resize(), 50);
    };

    btn.addEventListener("click", async () => {
      if (supportsFullscreen()) {
        if (!isFullscreen()) await enterFullscreen(cardEl);
        else await exitFullscreen();
      } else {
        cardEl.classList.toggle("chart-fs");
        setTimeout(() => chartInstance.resize(), 50);
      }
    });

    document.addEventListener("fullscreenchange", sync);
    document.addEventListener("webkitfullscreenchange", sync);

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && cardEl.classList.contains("chart-fs") && !isFullscreen()) {
        cardEl.classList.remove("chart-fs");
        setTimeout(() => chartInstance.resize(), 50);
      }
    });
  }

  function getBracketRange(stats) {
    const br = stats && stats.filters && Array.isArray(stats.filters.brackets) ? stats.filters.brackets : null;
    if (!br || br.length < 2) return null;
    const nums = br.map((x) => Number(x)).filter((x) => Number.isFinite(x));
    if (nums.length < 2) return null;
    const minB = Math.min(...nums);
    const maxB = Math.max(...nums);
    const rng = maxB - minB;
    return (Number.isFinite(rng) && rng > 0) ? { minB, maxB, rng } : null;
  }

  function normalizeMdi(mdiRaw, bracketInfo) {
    if (typeof mdiRaw !== "number" || !Number.isFinite(mdiRaw)) return null;
    if (!bracketInfo || !Number.isFinite(bracketInfo.rng) || bracketInfo.rng <= 0) return mdiRaw; // fallback: no normalization
    return mdiRaw / bracketInfo.rng;
  }

  function computeAxisLimitY(points) {
    let m = 0;
    for (const p of points) {
      if (typeof p.oewr_z === "number") m = Math.max(m, Math.abs(p.oewr_z));
    }
    if (!isFinite(m) || m <= 0) m = 1;
    m *= 1.12; // padding
    m = Math.max(0.75, Math.min(3.0, m)); // sane clamp
    return m;
  }

  function computeAxisLimitXNormalized(bracketInfo) {
    // Normalized MDI lives roughly in [-1, +1] (exact if bracket range is complete).
    // Add a little padding and keep it within reasonable bounds.
    let m = 1.0;
    // If no bracketInfo, we fall back to raw MDI and let Y logic drive; keep previous behavior later.
    m *= 1.08;
    m = Math.max(0.75, Math.min(1.5, m));
    return m;
  }


  function computeAxisLimit(points) {
    let m = 0;
    for (const p of points) {
      if (typeof p.mdi === "number") m = Math.max(m, Math.abs(p.mdi));
      if (typeof p.oewr_z === "number") m = Math.max(m, Math.abs(p.oewr_z));
    }
    if (!isFinite(m) || m <= 0) m = 1;
    m *= 1.12; // padding
    m = Math.max(0.75, Math.min(3.0, m)); // sane clamp
    return m;
  }

  // --- PLUGIN: sfondo quadranti + assi zero + vettori ---
  const vectorPlugin = {
    id: "vectorPlugin",
    beforeDraw: (c) => {
      const { ctx, chartArea, scales } = c;
      if (!chartArea) return;
      const { top, bottom, left, right } = chartArea;
      const x0 = scales.x.getPixelForValue(0);
      const y0 = scales.y.getPixelForValue(0);

      // Sfondi quadranti (molto tenui)
      ctx.save();
      ctx.fillStyle = "rgba(34, 197, 94, 0.05)"; // top-right
      ctx.fillRect(x0, top, right - x0, y0 - top);
      ctx.fillStyle = "rgba(59, 130, 246, 0.05)"; // top-left
      ctx.fillRect(left, top, x0 - left, y0 - top);
      ctx.fillStyle = "rgba(245, 158, 11, 0.05)"; // bottom-right
      ctx.fillRect(x0, y0, right - x0, bottom - y0);
      ctx.fillStyle = "rgba(156, 163, 175, 0.05)"; // bottom-left
      ctx.fillRect(left, y0, x0 - left, bottom - y0);

      // Assi centrali
      ctx.strokeStyle = "rgba(255,255,255,0.25)";
      ctx.setLineDash([4, 4]);
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(left, y0);
      ctx.lineTo(right, y0);
      ctx.moveTo(x0, top);
      ctx.lineTo(x0, bottom);
      ctx.stroke();
      ctx.setLineDash([]);

      // Label quadranti (coerenti con MDI/OEWR)
      ctx.fillStyle = "rgba(255, 255, 255, 0.22)";
      ctx.font = "bold 11px Inter, system-ui";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";

      const cxL = left + (x0 - left) / 2;
      const cxR = x0 + (right - x0) / 2;
      const cyT = top + 18;
      const cyB = bottom - 16;

      ctx.fillText("OUTPLAYING", cxL, cyT);      // MDI<0, OEWR>0
      ctx.fillText("DOMINANT", cxR, cyT);       // MDI>0, OEWR>0
      ctx.fillText("STRUGGLING", cxL, cyB);     // MDI<0, OEWR<0
      ctx.fillText("INEFFICIENT", cxR, cyB);    // MDI>0, OEWR<0

      ctx.restore();
    },
    afterDatasetsDraw: (c) => {
      const { ctx, scales } = c;
      const x0 = scales.x.getPixelForValue(0);
      const y0 = scales.y.getPixelForValue(0);

      c.data.datasets.forEach((ds, di) => {
        const meta = c.getDatasetMeta(di);
        if (meta.hidden) return;

        meta.data.forEach((pt, i) => {
          const raw = ds.data[i];
          if (!raw) return;

          const tx = pt.x;
          const ty = pt.y;
          const dx = tx - x0;
          const dy = ty - y0;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (!isFinite(dist) || dist < 2) return;

          const rPx = (pt.options && pt.options.radius) ? pt.options.radius : 6;
          const pad = 6;
          const cut = clamp((rPx + pad) / dist, 0, 0.9);
          const ex = tx - dx * cut;
          const ey = ty - dy * cut;

          // Linea vettore (tratteggiata)
          ctx.save();
          ctx.strokeStyle = pt.options.borderColor || "rgba(255,255,255,0.6)";
          ctx.globalAlpha = 0.65;
          ctx.lineWidth = 2;
          ctx.setLineDash([6, 4]);
          ctx.beginPath();
          ctx.moveTo(x0, y0);
          ctx.lineTo(ex, ey);
          ctx.stroke();
          ctx.setLineDash([]);

          // Punta freccia
          const ang = Math.atan2(ty - y0, tx - x0);
          const ah = 9; // head length
          const aw = 6; // head width
          ctx.translate(ex, ey);
          ctx.rotate(ang);
          ctx.globalAlpha = 0.85;
          ctx.beginPath();
          ctx.moveTo(0, 0);
          ctx.lineTo(-ah, -aw / 2);
          ctx.lineTo(-ah, aw / 2);
          ctx.closePath();
          ctx.fillStyle = pt.options.borderColor || "rgba(255,255,255,0.6)";
          ctx.fill();
          ctx.restore();
        });
      });
    },
  };

  function render(points, bracketInfo) {
    if (!canvas) return;
    if (chart) chart.destroy();

    const axisY = computeAxisLimitY(points);

    // MDI is shown normalized on X when bracket range is available (hybrid: tooltip keeps raw MDI).
    const axisX = bracketInfo ? computeAxisLimitXNormalized(bracketInfo) : computeAxisLimit(points);
    const datasets = (points || [])
      .filter((p) => typeof p.mdi === "number" && typeof p.oewr_z === "number" && normalizeMdi(p.mdi, bracketInfo) !== null)
      .map((p) => {
        const col = pcGet(p.player);
        const games = Number(p.games_total || 0);
        const r = Math.max(5, Math.sqrt(Math.max(1, games)) * 2);
        return {
          label: p.player,
          data: [{ x: normalizeMdi(p.mdi, bracketInfo), y: p.oewr_z, r, oewr: p.oewr, mdi_raw: p.mdi }],
          backgroundColor: pcAlpha(col, 0.25),
          borderColor: col,
          borderWidth: 2,
          hoverRadius: r + 3,
        };
      });

    chart = new Chart(canvas.getContext("2d"), {
      type: "bubble",
      data: { datasets },
      plugins: [vectorPlugin],
      options: {
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: isMobile() ? 4 : 10 },
        scales: {
          x: {
            min: -axisX,
             max: axisX,
            title: {
              display: !isMobile(),
              text: "MDI (normalizzato)  ← sotto tavolo | sopra tavolo →",
              color: "#aab3d3",
            },
            ticks: { color: "#aab3d3", maxTicksLimit: isMobile() ? 5 : 7 },
            grid: { color: "rgba(255,255,255,0.08)" },
          },
          y: {
            min: -axisY,
             max: axisY,
            title: {
              display: !isMobile(),
              text: "OEWR_Z (z-score vs attesa)  ← sotto attesa | sopra attesa →",
              color: "#aab3d3",
            },
            ticks: { color: "#aab3d3", maxTicksLimit: isMobile() ? 5 : 7 },
            grid: { color: "rgba(255,255,255,0.08)" },
          },
        },
        plugins: {
          legend: {
            display: true,
            position: isMobile() ? "bottom" : "right",
            align: "start",
            maxHeight: isMobile() ? 72 : undefined,
            labels: {
              color: "#e9ecf7",
              boxWidth: isMobile() ? 10 : 12,
              boxHeight: isMobile() ? 10 : 12,
              padding: isMobile() ? 8 : 10,
              usePointStyle: true,
              font: { size: isMobile() ? 10 : 12, weight: "600" },
            },
          },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const x = ctx.raw.x;           // normalized (when bracketInfo is available)
                const y = ctx.raw.y;
                const mag = Math.sqrt(x * x + y * y);

                const mdiRaw = ctx.raw.mdi_raw;
                const mdiRawTxt = (typeof mdiRaw === "number" && Number.isFinite(mdiRaw)) ? mdiRaw.toFixed(2) : "n/a";

                const oewr = ctx.raw.oewr;
                const oewrPP = (oewr === null || oewr === undefined) ? null : (100.0 * oewr);
                const oewrTxt = (oewrPP === null) ? "n/a" : `${oewrPP.toFixed(1)}pp`;

                return `${ctx.dataset.label}: MDI_norm ${x.toFixed(2)} (raw ${mdiRawTxt}), OEWR_Z ${y.toFixed(2)}, OEWR ${oewrTxt}, |v| ${mag.toFixed(2)}`;
              },
            },
          },
        },
      },
    });

    setupFullscreenButton(document.getElementById("meta-profile-card"), chart);


// Aggiorna posizione legenda su resize (mobile/desktop)
window.addEventListener("resize", () => {
  if (!chart) return;
  const pos = isMobile() ? "bottom" : "right";
  if (chart.options?.plugins?.legend) {
    chart.options.plugins.legend.position = pos;
    chart.options.plugins.legend.labels.boxWidth = isMobile() ? 10 : 12;
    chart.options.plugins.legend.labels.font = { size: isMobile() ? 11 : 12 };
    chart.update("none");
  }
});
  }

  async function init() {
    try {
      const res = await fetch("../data/stats.v1.json", { cache: "no-cache" });
      stats = await res.json();

      
if (elMeta) {
  const games = stats?.counts?.games;
  const entries = stats?.counts?.entries;
  const period = getPeriodLabel(stats?.games);
  const gen = stats?.generated_utc;
  const parts = [];
  if (period) parts.push(`Periodo: ${period}`);
  if (Number.isFinite(games)) parts.push(`Partite: ${games}`);
  if (Number.isFinite(entries)) parts.push(`Entries: ${entries}`);
  if (gen) parts.push(`Gen: ${String(gen).replace("T", " ").replace("Z", " UTC")}`);
  elMeta.textContent = parts.join(" · ");
}

      const points = stats.meta_profile_by_player || [];
      const bracketInfo = getBracketRange(stats);
      render(points, bracketInfo);
} catch (e) {
      console.error("Errore caricamento profilo:", e);
    }
  }

  window.addEventListener("DOMContentLoaded", init);
})();