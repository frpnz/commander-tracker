/* Shared player color mapping
   - Deterministic across pages AND across runs (no localStorage / no order-dependence)
   - Same player name => same color everywhere
   - If you want manual overrides, define window.PLAYER_COLOR_OVERRIDES before this script.
*/

(function () {
  "use strict";

  // 24 distinguishable colors (readable on a dark background).
  // More colors => fewer collisions when using hashing.
  const PALETTE = [
    "#56B4E9", // sky blue
    "#E69F00", // orange
    "#009E73", // bluish green
    "#F0E442", // yellow
    "#0072B2", // blue
    "#D55E00", // vermillion
    "#CC79A7", // reddish purple
    "#00BFC4", // cyan
    "#F8766D", // salmon
    "#7CAE00", // green
    "#C77CFF", // violet
    "#A3A500", // olive

    "#8DD3C7", // teal
    "#FFFFB3", // pale yellow
    "#BEBADA", // lavender
    "#FB8072", // coral
    "#80B1D3", // light blue
    "#FDB462", // light orange
    "#B3DE69", // lime
    "#FCCDE5", // pink
    "#BC80BD", // purple
    "#CCEBC5", // mint
    "#FFED6F", // sand
    "#9AD0F5", // soft azure
  ];

  function normalizeName(name) {
    return String(name || "").trim().toLowerCase();
  }

  function djb2(str) {
    let h = 5381;
    for (let i = 0; i < str.length; i++) {
      h = ((h << 5) + h) + str.charCodeAt(i);
      h >>>= 0;
    }
    return h >>> 0;
  }

  function getColorForPlayer(playerName) {
    const key = normalizeName(playerName);
    if (!key) return "#9CA3AF";

    // Optional manual overrides
    const overrides = (window.PLAYER_COLOR_OVERRIDES && typeof window.PLAYER_COLOR_OVERRIDES === "object")
      ? window.PLAYER_COLOR_OVERRIDES
      : null;
    if (overrides && Object.prototype.hasOwnProperty.call(overrides, key)) {
      return String(overrides[key]);
    }

    // Fully deterministic: hash(name) -> palette index
    const idx = djb2(key) % PALETTE.length;
    return PALETTE[idx];
  }

  function withAlpha(color, alpha) {
    if (!color) return color;
    if (color.startsWith("#") && color.length === 7) {
      const r = parseInt(color.slice(1, 3), 16);
      const g = parseInt(color.slice(3, 5), 16);
      const b = parseInt(color.slice(5, 7), 16);
      if ([r, g, b].some((v) => !Number.isFinite(v))) return color;
      return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }
    if (color.startsWith("rgb(")) return color.replace(/^rgb\((.*)\)$/, `rgba($1, ${alpha})`);
    if (color.startsWith("hsl(")) return color.replace(/^hsl\((.*)\)$/, `hsla($1, ${alpha})`);
    if (color.startsWith("hsla(")) return color.replace(/hsla\((.*),\s*([0-9.]+)\)$/, `hsla($1, ${alpha})`);
    return color;
  }

  // Expose a tiny namespace
  window.PlayerColors = {
    palette: PALETTE.slice(),
    get: getColorForPlayer,
    withAlpha,
  };
})();
