/* Archivio - Player/Commander/Bracket drilldown + ultime partite
 *
 * Data source: ../data/stats.v1.json (generated offline).
 */

const $ = (sel) => document.querySelector(sel);

// Compute a stable URL to the exported JSON regardless of trailing slashes
// and whether the site is hosted at domain root or under a subpath
// (e.g., GitHub Pages project sites).
function statsJsonUrl() {
  // Root = directory that contains the site's index.html
  // If we're at /archive/ -> root is ../
  // If we're at /stats/ or / -> still resolves correctly.
  const root = new URL("./", new URL("../", document.baseURI));
  return new URL("data/stats.v1.json", root).toString();
}

function setOptions(sel, values, { keepValue = true } = {}) {
  if (!sel) return;
  const prev = sel.value;
  // keep first option (Tutti)
  while (sel.options.length > 1) sel.remove(1);
  for (const v of values) {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    sel.appendChild(opt);
  }
  if (keepValue && prev) sel.value = prev;
  // If previous is no longer available, fall back to "Tutti"
  if (keepValue && prev && sel.value !== prev) sel.value = "";
}

function fmtDate(s) {
  if (!s) return "";
  // If it's ISO-like, keep it readable; otherwise return as-is.
  return String(s).replace("T", " ").replace("Z", " UTC");
}


function _dateKey(s) {
  return (s || "").replace("T", " ").replace("Z", "").trim().slice(0, 10);
}

function getPeriodLabel(games) {
  if (!Array.isArray(games) || games.length === 0) return "";
  let min = null, max = null;
  for (const g of games) {
    const d = _dateKey(g && g.played_at);
    if (!d) continue;
    if (min === null || d < min) min = d;
    if (max === null || d > max) max = d;
  }
  return (min && max) ? `${min} → ${max}` : "";
}

function uniqSorted(arr) {
  return Array.from(new Set(arr.filter((x) => x !== null && x !== undefined && String(x).trim() !== "").map(String)))
    .sort((a, b) => a.localeCompare(b, "it"));
}

function buildCommanderOptions(data, player) {
  const rows = data.by_player_commander || [];
  const commanders = uniqSorted(
    rows
      .filter((r) => !player || r.player === player)
      .map((r) => r.commander)
  );
  setOptions($("#fCommander"), commanders);
}

function buildBracketOptions(data, player, commander) {
  const rows = data.by_player_commander || [];
  const brackets = uniqSorted(
    rows
      .filter((r) => !player || r.player === player)
      .filter((r) => !commander || r.commander === commander)
      .map((r) => r.bracket)
  );
  setOptions($("#fBracket"), brackets);
}

function renderListTable(data, state) {
  const gate = $("#listGate");
  const tableWrap = $("#listTableWrap");
  const tbody = $("#tList tbody");
  tbody.innerHTML = "";
  const hasSelection = Boolean(state.player || state.commander || state.bracket);
  if (!hasSelection) {
    if (gate) {
      gate.style.display = "";
      gate.textContent = "Seleziona almeno un filtro (Player, Commander o Bracket) per visualizzare l’elenco.";
    }
    if (tableWrap) tableWrap.style.display = "none";
    const pill = $("#countList");
    if (pill) pill.textContent = "";
    return;
  }
  if (gate) gate.style.display = "none";
  if (tableWrap) tableWrap.style.display = "";
  const rows = (data.by_player_commander || [])
    .filter((r) => !state.player || r.player === state.player)
    .filter((r) => !state.commander || r.commander === state.commander)
    .filter((r) => !state.bracket || String(r.bracket || "") === String(state.bracket))
    .slice()
    .sort((a, b) => {
      // player -> commander -> bracket -> games desc
      const pa = String(a.player || "");
      const pb = String(b.player || "");
      if (pa !== pb) return pa.localeCompare(pb, "it");
      const ca = String(a.commander || "");
      const cb = String(b.commander || "");
      if (ca !== cb) return ca.localeCompare(cb, "it");
      const ba = String(a.bracket || "");
      const bb = String(b.bracket || "");
      if (ba !== bb) return ba.localeCompare(bb, "it", { numeric: true });
      return Number(b.games || 0) - Number(a.games || 0);
    });

  for (const r of rows) {
    const tr = document.createElement("tr");
    const tdP = document.createElement("td");
    tdP.textContent = r.player || "";
    tdP.setAttribute("data-label", "Player");
    const tdC = document.createElement("td");
    tdC.textContent = r.commander || "";
    tdC.setAttribute("data-label", "Commander");
    const tdB = document.createElement("td");
    tdB.textContent = (r.bracket === null || r.bracket === undefined) ? "" : String(r.bracket);
    tdB.setAttribute("data-label", "Bracket");
    const tdG = document.createElement("td");
    tdG.className = "num";
    tdG.textContent = String((r.games === null || r.games === undefined) ? 0 : r.games);
    tdG.setAttribute("data-label", "Partite");
    tr.appendChild(tdP);
    tr.appendChild(tdC);
    tr.appendChild(tdB);
    tr.appendChild(tdG);
    tbody.appendChild(tr);
  }

  $("#countList").textContent = `${rows.length} righe`;
  const hintParts = [];
  if (state.player) hintParts.push(`player: ${state.player}`);
  if (state.commander) hintParts.push(`commander: ${state.commander}`);
  if (state.bracket) hintParts.push(`bracket: ${state.bracket}`);
  $("#hint").textContent = hintParts.length ? `Filtro attivo → ${hintParts.join(" · ")}` : "";
}

function gameMatchesFilters(g, state) {
  if (!g) return false;
  const entries = Array.isArray(g.entries) ? g.entries : [];
  if (state.player) {
    if (!entries.some((e) => e && e.player === state.player)) return false;
  }
  if (state.commander) {
    if (!entries.some((e) => e && e.commander === state.commander)) return false;
  }
  if (state.bracket) {
    if (!entries.some((e) => String(e && e.bracket || "") === String(state.bracket))) return false;
  }
  return true;
}

function renderRecentGames(data, state) {
  const wrap = $("#recentWrap");
  wrap.innerHTML = "";

  const all = Array.isArray(data.games) ? data.games : [];
  const filtered = all.filter((g) => gameMatchesFilters(g, state));

  const sel = $("#fRecentN");
  const nRaw = sel ? sel.value : "10";
  const n = (nRaw === "all") ? Infinity : Number(nRaw || 10);
  const slice = filtered.slice(0, n);

  $("#countRecent").textContent = `${slice.length} / ${filtered.length}`;

  for (const g of slice) {
    const card = document.createElement("div");
    card.className = "recent-game";

    const head = document.createElement("div");
    head.className = "recent-head";

    const left = document.createElement("div");
    left.className = "recent-title";
    const when = fmtDate(g.played_at);
    left.textContent = `#${g.id}${when ? " · " + when : ""}`;

    const right = document.createElement("div");
    right.className = "recent-winner";
    // Avoid injecting untrusted data via innerHTML (XSS hardening)
    right.textContent = "";
    const badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent = "Winner";
    right.appendChild(badge);
    right.append(" " + (g.winner_player || ""));

    head.appendChild(left);
    head.appendChild(right);

    const tableWrap = document.createElement("div");
    tableWrap.className = "recent-table-wrap";
    const table = document.createElement("table");
    table.className = "recent-table";
    table.innerHTML = `
      <thead>
        <tr>
          <th>Player</th>
          <th>Commander</th>
          <th>Bracket</th>
        </tr>
      </thead>
      <tbody></tbody>
    `;
    const tbody = table.querySelector("tbody");
    const entries = Array.isArray(g.entries) ? g.entries : [];
    for (const e of entries) {
      const tr = document.createElement("tr");
      const tdP = document.createElement("td");
      tdP.textContent = e.player || "";
      tdP.setAttribute("data-label", "Player");
      const tdC = document.createElement("td");
      tdC.textContent = e.commander || "";
      tdC.setAttribute("data-label", "Commander");
      const tdB = document.createElement("td");
      tdB.textContent = (e.bracket === null || e.bracket === undefined) ? "" : String(e.bracket);
      tdB.setAttribute("data-label", "Bracket");
      tr.appendChild(tdP);
      tr.appendChild(tdC);
      tr.appendChild(tdB);
      tbody.appendChild(tr);
    }
    tableWrap.appendChild(table);

    card.appendChild(head);
    if (g.notes) {
      const notes = document.createElement("div");
      notes.className = "recent-notes";
      notes.textContent = String(g.notes);
      card.appendChild(notes);
    }
    card.appendChild(tableWrap);
    wrap.appendChild(card);
  }
}

function buildState() {
  return {
    player: $("#fPlayer") && $("#fPlayer").value ? $("#fPlayer").value : "",
    commander: $("#fCommander") && $("#fCommander").value ? $("#fCommander").value : "",
    bracket: $("#fBracket") && $("#fBracket").value ? $("#fBracket").value : "",
  };
}

async function main() {
  const res = await fetch(statsJsonUrl(), { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status} (${res.statusText})`);
  const data = await res.json();

  const games = (data.counts && data.counts.games !== undefined && data.counts.games !== null) ? data.counts.games : 0;
  const entries = (data.counts && data.counts.entries !== undefined && data.counts.entries !== null) ? data.counts.entries : 0;
  const gen = data.generated_utc ? data.generated_utc : "";
  const period = getPeriodLabel(data?.games);
  const parts = [];
  if (Number.isFinite(games)) parts.push(`${games} partite`);
  if (Number.isFinite(entries)) parts.push(`${entries} entries`);
  if (period) parts.push(`periodo ${period}`);
  if (gen) parts.push(`gen ${gen}`);
  $("#meta").textContent = parts.join(" · ");

  setOptions($("#fPlayer"), (data.filters && data.filters.players) ? data.filters.players : []);
  buildCommanderOptions(data, "");
  buildBracketOptions(data, "", "");

  const rerender = () => {
    const state = buildState();
    renderListTable(data, state);
    renderRecentGames(data, state);
  };

  $("#fPlayer").addEventListener("change", () => {
    buildCommanderOptions(data, $("#fPlayer").value);
    // Commander selection may become invalid after changing player
    buildBracketOptions(data, $("#fPlayer").value, $("#fCommander").value);
    rerender();
  });

  $("#fCommander").addEventListener("change", () => {
    buildBracketOptions(data, $("#fPlayer").value, $("#fCommander").value);
    rerender();
  });

  $("#fBracket").addEventListener("change", rerender);
  $("#fRecentN").addEventListener("change", rerender);

  $("#btnReset").addEventListener("click", () => {
    $("#fPlayer").value = "";
    buildCommanderOptions(data, "");
    $("#fCommander").value = "";
    buildBracketOptions(data, "", "");
    $("#fBracket").value = "";
    $("#fRecentN").value = "3";
    rerender();
  });

  rerender();
}

main().catch((err) => {
  console.error(err);
  const meta = $("#meta");
  if (meta) meta.textContent = "Errore caricando dati";
  const hint = $("#hint");
  if (hint) hint.textContent = `Errore: ${err.message || err}`;
  const wrap = $("#recentWrap");
  if (wrap) wrap.textContent = `Errore: ${err.message || err}`;
});
