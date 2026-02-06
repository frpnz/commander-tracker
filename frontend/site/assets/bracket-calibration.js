/* Bracket Calibration (table-first, mobile friendly)
   Data source: ../data/stats.v1.json

   Shows commander calibration:
     - bracket_prior (DB)
     - b_post (estimated posterior bracket, quarter steps)
     - games, wins
   Row color encodes signed deviation (cpr_z), clamped to +/- 2 for punch.
   Player focus highlights commanders played by that player (derived from by_player_commander).
*/
(function () {
  const COL_TEXT_MUTED = "rgba(255,255,255,0.75)";

  function clamp(x, a, b) { return Math.max(a, Math.min(b, x)); }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function mixRGB(c1, c2, t) {
    return [
      Math.round(lerp(c1[0], c2[0], t)),
      Math.round(lerp(c1[1], c2[1], t)),
      Math.round(lerp(c1[2], c2[2], t)),
    ];
  }

  // Diverging coolwarm-ish palette tuned for dark background.
  const COOL = [59, 130, 246];  // blue
  const MID  = [17, 24, 39];    // slate-900-ish
  const WARM = [239, 68, 68];   // red

  function rowBgForDelta(delta) {
  if (delta === null || delta === undefined || Number.isNaN(delta)) return "transparent";
  // clamp to +/-2 brackets for punch (though delta will rarely exceed this)
  const dd = clamp(Number(delta), -2, 2);
  const t = (dd + 2) / 4; // 0..1
  let rgb;
  if (t < 0.5) rgb = mixRGB(COOL, MID, t / 0.5);
  else rgb = mixRGB(MID, WARM, (t - 0.5) / 0.5);
  return `rgba(${rgb[0]},${rgb[1]},${rgb[2]},0.22)`;
}


  function fmtB(v) {
    if (v === null || v === undefined) return "—";
    const n = Number(v);
    if (!Number.isFinite(n)) return "—";
    // show quarters nicely (2 decimals)
    return n.toFixed(2).replace(/\.00$/, "");
  }


function fmtSigned(v) {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  const s = (n > 0) ? "+" : "";
  return s + n.toFixed(2);
}

// Emoji + color class for delta.
// Neutral if |Δ| < 0.25.
function formatDelta(delta) {
  if (delta === null || delta === undefined) {
    return { html: "—", cls: "delta-neutral", title: "" };
  }
  const d = Number(delta);
  if (!Number.isFinite(d)) {
    return { html: "—", cls: "delta-neutral", title: "" };
  }

  const abs = Math.abs(d);
  if (abs < 0.25) {
    return {
      html: `⏺️ ${fmtSigned(d)}`,
      cls: "delta-neutral",
      title: "In linea con il bracket dichiarato"
    };
  }
  if (d > 0) {
    return {
      html: `⬆️ ${fmtSigned(d)}`,
      cls: "delta-up",
      title: "Performance sopra il bracket dichiarato"
    };
  }
  return {
    html: `⬇️ ${fmtSigned(d)}`,
    cls: "delta-down",
    title: "Performance sotto il bracket dichiarato"
  };
}

  function buildPlayerToCommanders(stats) {
    const map = new Map();
    const rows = stats?.by_player_commander || [];
    for (const r of rows) {
      const p = r.player || "";
      const c = r.commander || "";
      const g = Number(r.games || 0);
      if (!p || !c || g <= 0) continue;
      if (!map.has(p)) map.set(p, new Set());
      map.get(p).add(c);
    }
    return map;
  }

  function populatePlayerPick(players) {
    const sel = document.getElementById("playerPick");
    if (!sel) return;
    for (const p of players) {
      const opt = document.createElement("option");
      opt.value = p;
      opt.textContent = p;
      sel.appendChild(opt);
    }
  }

  function renderTable(stats, minGames, focusPlayer, playerToCmd) {
    const tbody = document.querySelector("#calTable tbody");
    if (!tbody) return;
    tbody.innerHTML = "";

    const focusSet = (focusPlayer && playerToCmd.get(focusPlayer)) ? playerToCmd.get(focusPlayer) : null;

    let rows = (stats?.commander_calibration || []).slice();
    rows = rows.filter(r => Number(r.games || 0) >= minGames);
    if (focusSet) rows = rows.filter(r => focusSet.has(String(r.commander || "")));

    // sort by absolute deviation strongest first, then games
    rows.sort((a,b) => {
      const za = (a.cpr_z === null || a.cpr_z === undefined) ? null : Number(a.cpr_z);
      const zb = (b.cpr_z === null || b.cpr_z === undefined) ? null : Number(b.cpr_z);
      const aa = (za === null || Number.isNaN(za)) ? -1 : Math.abs(za);
      const ab = (zb === null || Number.isNaN(zb)) ? -1 : Math.abs(zb);
      if (ab !== aa) return ab - aa;
      const gb = Number(b.games || 0), ga = Number(a.games || 0);
      if (gb !== ga) return gb - ga;
      return String(a.commander || "").localeCompare(String(b.commander || ""));
    });

    for (const r of rows) {
      const tr = document.createElement("tr");
      const deltaB = (r.b_post === null || r.b_post === undefined || r.bracket_prior === null || r.bracket_prior === undefined) ? null : (Number(r.b_post) - Number(r.bracket_prior));
      const commander = r.commander || "";
      const bPrior = r.bracket_prior;
      const bPost = r.b_post;
      const games = Number(r.games || 0);
      const wins = Number(r.wins || 0);

      const isFocus = focusSet ? focusSet.has(commander) : true;
      if (focusSet && !isFocus) tr.classList.add("row-dim");


      const fd = formatDelta(deltaB);

      tr.innerHTML = `
        <td class="desktop-only"><span class="delta ${fd.cls}" title="${escapeHtml(fd.title)}">${fd.html}</span></td>
        <td class="desktop-only">${escapeHtml(commander)}</td>
        <td class="num desktop-only">${fmtB(bPrior)}</td>
        <td class="num desktop-only"><b>${fmtB(bPost)}</b></td>
        <td class="num desktop-only">${games}</td>
        <td class="num desktop-only">${wins}</td>
        <td class="mobile-only compact">
          <span class="delta ${fd.cls}" title="${escapeHtml(fd.title)}">${fd.html}</span>
          <span style="opacity:.75;"> · B ${escapeHtml(fmtB(bPrior))}→${escapeHtml(fmtB(bPost))} · ${games}g ${wins}w</span>
        </td>
      `;
tbody.appendChild(tr);
    }
  }

  function escapeHtml(s) {
    return String(s || "").replace(/[&<>"']/g, (c) => ({
      "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
    }[c]));
  }

  async function init() {
    const minSel = document.getElementById("minGames");
    const playerSel = document.getElementById("playerPick");
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

    const res = await fetch("../data/stats.v1.json", { cache: "no-cache" });
    stats = await res.json();


    const elMeta = document.getElementById("meta");
    if (elMeta) {
      const games = stats?.counts?.games;
      const period = getPeriodLabel(stats?.games);
      const gen = stats?.generated_utc;
      const parts = [];
      if (period) parts.push(`Periodo: ${period}`);
      if (Number.isFinite(games)) parts.push(`Partite: ${games}`);
      if (gen) parts.push(`Gen: ${gen}`);
      elMeta.textContent = parts.join(" · ");
    }

    const players = (stats?.filters?.players || []).slice().sort((a,b)=>String(a).localeCompare(String(b)));
    populatePlayerPick(players);

    const playerToCmd = buildPlayerToCommanders(stats);

    function rerender() {
      const minGames = Number(minSel?.value || 3);
      const focusPlayer = playerSel?.value || "";
      renderTable(stats, minGames, focusPlayer, playerToCmd);
    }

    if (minSel) minSel.addEventListener("change", rerender);
    if (playerSel) playerSel.addEventListener("change", rerender);

    rerender();
  }

  init().catch((e) => {
    console.error("Bracket calibration init failed:", e);
    const tbody = document.querySelector("#calTable tbody");
    if (tbody) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="7" style="padding:14px; color:${COL_TEXT_MUTED};">Errore nel caricamento dati.</td>`;
      tbody.appendChild(tr);
    }
  });
})();
