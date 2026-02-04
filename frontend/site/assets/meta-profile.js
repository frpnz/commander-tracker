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



  function clamp(x, lo, hi) {
    return x < lo ? lo : x > hi ? hi : x;
  }


  function isMobile() {
    return window.matchMedia && window.matchMedia("(max-width: 640px)").matches;
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

  function render(points) {
    if (!canvas) return;
    if (chart) chart.destroy();

    const axis = computeAxisLimit(points);
    const datasets = (points || [])
      .filter((p) => typeof p.mdi === "number" && typeof p.oewr_z === "number")
      .map((p) => {
        const col = getPlayerColor(p.player);
        const games = Number(p.games_total || 0);
        const r = Math.max(5, Math.sqrt(Math.max(1, games)) * 2);
        return {
          label: p.player,
          data: [{ x: p.mdi, y: p.oewr_z, r, oewr: p.oewr }],
          backgroundColor: withAlpha(col, 0.25),
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
        scales: {
          x: {
            min: -axis,
            max: axis,
            title: {
              display: true,
              text: "MDI (power relativo)  ← sotto tavolo | sopra tavolo →",
              color: "#aab3d3",
            },
            ticks: { color: "#aab3d3" },
            grid: { color: "rgba(255,255,255,0.08)" },
          },
          y: {
            min: -axis,
            max: axis,
            title: {
              display: true,
              text: "OEWR_Z (z-score vs attesa)  ← sotto attesa | sopra attesa →",
              color: "#aab3d3",
            },
            ticks: { color: "#aab3d3" },
            grid: { color: "rgba(255,255,255,0.08)" },
          },
        },
        plugins: {
          legend: {
            position: isMobile() ? "bottom" : "right",
            align: "center",
            labels: { color: "#e9ecf7", boxWidth: isMobile() ? 10 : 12, usePointStyle: true, font: { size: isMobile() ? 11 : 12 } },
          },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const x = ctx.raw.x;
                const y = ctx.raw.y;
                const mag = Math.sqrt(x * x + y * y);
                const oewr = ctx.raw.oewr;
                const oewrPP = (oewr === null || oewr === undefined) ? null : (100.0 * oewr);
                const oewrTxt = (oewrPP === null) ? "n/a" : `${oewrPP.toFixed(1)}pp`;
                return `${ctx.dataset.label}: MDI ${x.toFixed(2)}, OEWR_Z ${y.toFixed(2)}, OEWR ${oewrTxt}, |v| ${mag.toFixed(2)}`;
              },
            },
          },
        },
      },
    });

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

      if (elMeta) elMeta.textContent = `Generato il: ${stats.generated_utc}`;

      const points = stats.meta_profile_by_player || [];
      render(points);
    } catch (e) {
      console.error("Errore caricamento profilo:", e);
    }
  }

  window.addEventListener("DOMContentLoaded", init);
})();