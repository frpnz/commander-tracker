/* Shared player color mapping (<=12 players)
   - Very distinct palette for dark UI
   - Stable across pages via localStorage
   - Adding new players does NOT change existing players' colors
*/

(function () {
  "use strict";

  const STORAGE_KEY = "commanderTracker.playerColors.v1";

  // 12 highly distinguishable colors (chosen to be visually far apart)
  // and still readable on a dark background.
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
  ];

  function safeParse(json, fallback) {
    try {
      const v = JSON.parse(json);
      return v && typeof v === "object" ? v : fallback;
    } catch {
      return fallback;
    }
  }

  function loadMap() {
    const raw = window.localStorage ? window.localStorage.getItem(STORAGE_KEY) : null;
    return raw ? safeParse(raw, {}) : {};
  }

  function saveMap(map) {
    if (!window.localStorage) return;
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
    } catch {
      // ignore quota / private-mode errors
    }
  }

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

  function pickFirstFreeIndex(map) {
    const used = new Set(Object.values(map).map((x) => Number(x)));
    for (let i = 0; i < PALETTE.length; i++) {
      if (!used.has(i)) return i;
    }
    return null;
  }

  function getColorForPlayer(playerName) {
    const key = normalizeName(playerName);
    if (!key) return "#9CA3AF";

    const map = loadMap();
    if (Object.prototype.hasOwnProperty.call(map, key)) {
      const idx = Number(map[key]);
      return PALETTE[(idx % PALETTE.length + PALETTE.length) % PALETTE.length];
    }

    // Assign a free color if available (keeps colors unique up to 12 players)
    let idx = pickFirstFreeIndex(map);
    if (idx === null) {
      // Fallback: deterministic hash (collisions possible only if >12 players)
      idx = djb2(key) % PALETTE.length;
    }

    map[key] = idx;
    saveMap(map);
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
