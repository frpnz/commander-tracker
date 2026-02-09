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

  
  // --- Uncertainty categorization (relative / percentile-based) ---
  // We categorize posterior uncertainty using b_post_sd *relative* to other commanders.
  // This avoids ending up with "Alta" for most rows when the posterior remains wide.
  //
  // We compute cutoffs once on the *full* calibration dataset (not just filtered rows)
  // so categories don't "switch" when changing the "Min partite" filter.
  //
  // Cutoffs:
  //   - p33 and p66 percentiles of b_post_sd across commanders with finite sd
  //   - sd <= p33 -> "Bassa"
  //   - p33 < sd <= p66 -> "Media"
  //   - sd > p66 -> "Alta"

  function quantileSorted(arr, q) {
    if (!arr || arr.length === 0) return null;
    const n = arr.length;
    if (n === 1) return arr[0];
    const pos = (n - 1) * q;
    const lo = Math.floor(pos);
    const hi = Math.ceil(pos);
    if (lo === hi) return arr[lo];
    const t = pos - lo;
    return arr[lo] + (arr[hi] - arr[lo]) * t;
  }

  function computeUncertaintyCutoffs(rows) {
    const sds = [];
    for (const r of rows || []) {
      const s = Number(r.b_post_sd);
      if (Number.isFinite(s)) sds.push(s);
    }
    sds.sort((a, b) => a - b);
    // If we don't have enough samples, return null so we can gracefully fall back.
    if (sds.length < 6) return { p33: null, p66: null, n: sds.length };
    return {
      p33: quantileSorted(sds, 1 / 3),
      p66: quantileSorted(sds, 2 / 3),
      n: sds.length,
    };
  }

  function uncertaintyCat(sd, cutoffs) {
    const s = Number(sd);
    if (!Number.isFinite(s)) return { label: "—", title: "" };

    const p33 = cutoffs?.p33;
    const p66 = cutoffs?.p66;

    // Fallback (absolute-ish) if we cannot compute reliable percentiles.
    if (!Number.isFinite(p33) || !Number.isFinite(p66) || p33 >= p66) {
      // Soft fallback tuned for typical posteriors in this app.
      if (s <= 0.55) return { label: "Bassa", title: `σ_post = ${s.toFixed(2)}` };
      if (s <= 0.85) return { label: "Media", title: `σ_post = ${s.toFixed(2)}` };
      return { label: "Alta", title: `σ_post = ${s.toFixed(2)}` };
    }

    const title = `σ_post = ${s.toFixed(2)} · p33=${p33.toFixed(2)} p66=${p66.toFixed(2)} (n=${cutoffs?.n || 0})`;
    if (s <= p33) return { label: "Bassa", title };
    if (s <= p66) return { label: "Media", title };
    return { label: "Alta", title };
  }

  function renderTable(stats, minGames, focusPlayer, playerToCmd) {
    const tbody = document.querySelector("#calTable tbody");
    if (!tbody) return;
    tbody.innerHTML = "";

    const focusSet = (focusPlayer && playerToCmd.get(focusPlayer)) ? playerToCmd.get(focusPlayer) : null;

    let rows = (stats?.commander_calibration || []).slice();
    rows = rows.filter(r => Number(r.games || 0) >= minGames);
    if (focusSet) rows = rows.filter(r => focusSet.has(String(r.commander || "")));

    // Sort: most played first, then commander name
    rows.sort((a,b) => {
      const gb = Number(b.games || 0), ga = Number(a.games || 0);
      if (gb !== ga) return gb - ga;
      return String(a.commander || "").localeCompare(String(b.commander || ""));
    });

    // Compute percentile cutoffs on the *full* calibration dataset (not filtered),
    // so categories stay stable when changing the "Min partite" filter.
    const cutoffs = computeUncertaintyCutoffs(stats?.commander_calibration || []);

    for (const r of rows) {
      const tr = document.createElement("tr");

      const commander = r.commander || "";
      const bPrior = r.bracket_prior;

      // Use MAP estimate for posterior (frontend-only switch).
      // Fallback to mean if older exports don't have b_post_map.
      const bPost = (r.b_post_map === null || r.b_post_map === undefined) ? r.b_post : r.b_post_map;

      const games = Number(r.games || 0);
      const wins = Number(r.wins || 0);

      const u = uncertaintyCat(r.b_post_sd, cutoffs);

      const isFocus = focusSet ? focusSet.has(commander) : true;
      if (focusSet && !isFocus) tr.classList.add("row-dim");

      const rowTip = `Partite: ${games} · Vittorie: ${wins}`;

      tr.innerHTML = `
        <td class="commander-cell">
          <span class="commander-name">${escapeHtml(commander)}</span>
          <button type="button" class="info-btn" aria-label="Dettagli partite e vittorie" data-tip="${escapeHtml(rowTip)}">ℹ️</button>
        </td>
        <td class="num">${fmtB(bPrior)}</td>
        <td class="num"><b>${escapeHtml(fmtB(bPost))}</b></td>
        <td title="${escapeHtml(u.title)}">${escapeHtml(u.label)}</td>
      `;

      tbody.appendChild(tr);
    }
  }


function escapeHtml(s) {
    return String(s || "").replace(/[&<>"']/g, (c) => ({
      "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
    }[c]));
  }

  
  // Touch-friendly popover for row details (games/wins). Uses event delegation.
  function setupInfoPopovers() {
    const tbody = document.querySelector("#calTable tbody");
    if (!tbody) return;

    let pop = null;
    let lastBtn = null;

    function close() {
      if (pop) pop.remove();
      pop = null;
      if (lastBtn) lastBtn.setAttribute("aria-expanded", "false");
      lastBtn = null;
    }

    function openFor(btn) {
      const tip = btn.getAttribute("data-tip") || "";
      if (!tip) return;

      if (lastBtn === btn && pop) { close(); return; }
      close();

      const r = btn.getBoundingClientRect();

      pop = document.createElement("div");
      pop.className = "tip-popover";
      pop.setAttribute("role", "dialog");
      pop.innerHTML = `
        <div class="tip-popover__inner">
          <div class="tip-popover__title">Dettagli</div>
          <div class="tip-popover__body">${escapeHtml(tip)}</div>
        </div>
      `;

      document.body.appendChild(pop);

      // Position near the button; keep inside viewport.
      const pr = pop.getBoundingClientRect();
      let left = r.left + r.width/2 - pr.width/2;
      let top = r.bottom + 8;

      const pad = 8;
      left = Math.max(pad, Math.min(left, window.innerWidth - pr.width - pad));
      if (top + pr.height + pad > window.innerHeight) {
        top = r.top - pr.height - 8;
      }
      top = Math.max(pad, Math.min(top, window.innerHeight - pr.height - pad));

      pop.style.left = left + "px";
      pop.style.top = top + "px";

      lastBtn = btn;
      btn.setAttribute("aria-expanded", "true");
      // prevent click inside popover from closing
      pop.addEventListener("click", (e) => e.stopPropagation());
    }

    tbody.addEventListener("click", (e) => {
      const btn = e.target && e.target.closest ? e.target.closest(".info-btn") : null;
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();
      openFor(btn);
    });

    // Keyboard accessibility
    tbody.addEventListener("keydown", (e) => {
      const btn = e.target && e.target.closest ? e.target.closest(".info-btn") : null;
      if (!btn) return;
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        e.stopPropagation();
        openFor(btn);
      }
    });

    document.addEventListener("click", close);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
    window.addEventListener("resize", close);
    window.addEventListener("scroll", close, { passive: true });
  }

async function init() {
    const minSel = document.getElementById("minGames");
    const playerSel = document.getElementById("playerPick");
    let stats = null;
    setupInfoPopovers();

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
      tr.innerHTML = `<td colspan="4" style="padding:14px; color:${COL_TEXT_MUTED};">Errore nel caricamento dati.</td>`;
      tbody.appendChild(tr);
    }
  });
})();
