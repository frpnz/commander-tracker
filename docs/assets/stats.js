let DATA = null;

const state = {
  podSize: "__all__",
  topTriples: 50,
  maxUnique: 200,
};

function qs(sel){ return document.querySelector(sel); }

function readQuery(){
  const url = new URL(window.location.href);
  const p = url.searchParams;
  if (p.get("pod")) state.podSize = p.get("pod");
  if (p.get("top")) state.topTriples = parseInt(p.get("top"), 10) || state.topTriples;
  if (p.get("max")) state.maxUnique = parseInt(p.get("max"), 10) || state.maxUnique;
  state.topTriples = Math.max(10, Math.min(500, state.topTriples));
  state.maxUnique = Math.max(10, Math.min(5000, state.maxUnique));
}

function writeQuery(){
  const url = new URL(window.location.href);
  url.searchParams.set("pod", state.podSize);
  url.searchParams.set("top", String(state.topTriples));
  url.searchParams.set("max", String(state.maxUnique));
  window.history.replaceState({}, "", url);
}

function escapeHtml(s){
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function fmt(n, digits=1){
  if (n === null || n === undefined) return "";
  const x = Number(n);
  if (Number.isNaN(x)) return String(n);
  return x.toFixed(digits);
}

function table(el, rows, cols){
  // cols: [{key, label, fmt?}]
  if (!rows || rows.length === 0) { el.innerHTML = "<p class='muted'>n/a</p>"; return; }
  const thead = cols.map(c => `<th>${escapeHtml(c.label)}</th>`).join("");
  const tbody = rows.map(r => {
    const tds = cols.map(c => {
      const v = r[c.key];
      const vv = c.fmt ? c.fmt(v) : v;
      return `<td>${escapeHtml(vv)}</td>`;
    }).join("");
    return `<tr>${tds}</tr>`;
  }).join("\n");
  el.innerHTML = `<div class='tablewrap'><table><thead><tr>${thead}</tr></thead><tbody>${tbody}</tbody></table></div>`;
}

function kvTable(el, obj){
  const rows = Object.entries(obj || {}).map(([k,v]) => ({k, v}));
  rows.sort((a,b) => {
    const ak = a.k === "n/a" ? "~" : a.k;
    const bk = b.k === "n/a" ? "~" : b.k;
    return ak.localeCompare(bk);
  });
  table(el, rows, [
    {key: "k", label: "bucket"},
    {key: "v", label: "count", fmt: (x) => String(x)}
  ]);
}

function init(){
  // pod sizes
  const sel = qs("#podSize");
  sel.innerHTML = "";
  const optAll = document.createElement("option");
  optAll.value = "__all__";
  optAll.textContent = "Tutti";
  sel.appendChild(optAll);
  for (const n of (DATA.sizes || [])) {
    const opt = document.createElement("option");
    opt.value = String(n);
    opt.textContent = String(n);
    sel.appendChild(opt);
  }

  // defaults
  sel.value = state.podSize;
  qs("#topTriples").value = state.topTriples;
  qs("#maxUnique").value = state.maxUnique;

  qs("#controls").addEventListener("submit", (ev) => {
    ev.preventDefault();
    state.podSize = qs("#podSize").value || "__all__";
    state.topTriples = parseInt(qs("#topTriples").value, 10) || state.topTriples;
    state.maxUnique = parseInt(qs("#maxUnique").value, 10) || state.maxUnique;
    state.topTriples = Math.max(10, Math.min(500, state.topTriples));
    state.maxUnique = Math.max(10, Math.min(5000, state.maxUnique));
    writeQuery();
    render();
  });
}

function render(){
  if (!DATA) return;

  table(qs("#tblPlayers"), DATA.player_rows, [
    {key: "player", label: "player"},
    {key: "games", label: "games", fmt: (x) => String(x)},
    {key: "wins", label: "wins", fmt: (x) => String(x)},
    {key: "winrate", label: "winrate %", fmt: (x) => fmt(x, 1)},
    {key: "unique_commanders", label: "unique commanders", fmt: (x) => String(x)},
    {key: "top_commander", label: "top commander"},
    {key: "top_commander_games", label: "top cmd games", fmt: (x) => String(x)},
  ]);

  table(qs("#tblPairs"), DATA.pair_rows, [
    {key: "player", label: "player"},
    {key: "commander", label: "commander"},
    {key: "games", label: "games", fmt: (x) => String(x)},
    {key: "wins", label: "wins", fmt: (x) => String(x)},
    {key: "winrate", label: "winrate %", fmt: (x) => fmt(x, 1)},
  ]);

  const psKey = state.podSize;
  const playersBy = (psKey === "__all__") ? null : (DATA.player_by_size_tables || {})[psKey];
  const pairsBy = (psKey === "__all__") ? null : (DATA.pair_by_size_tables || {})[psKey];
  table(qs("#tblPlayersBySize"), playersBy, [
    {key: "player", label: "player"},
    {key: "games", label: "games", fmt: (x) => String(x)},
    {key: "wins", label: "wins", fmt: (x) => String(x)},
    {key: "winrate", label: "winrate %", fmt: (x) => fmt(x, 1)},
  ]);
  table(qs("#tblPairsBySize"), pairsBy, [
    {key: "player", label: "player"},
    {key: "commander", label: "commander"},
    {key: "games", label: "games", fmt: (x) => String(x)},
    {key: "wins", label: "wins", fmt: (x) => String(x)},
    {key: "winrate", label: "winrate %", fmt: (x) => fmt(x, 1)},
  ]);

  kvTable(qs("#tblBracketEntries"), DATA.bracket_entry_counts);
  kvTable(qs("#tblBracketWinners"), DATA.bracket_winner_counts);
  table(qs("#tblBracketWinrate"), DATA.bracket_rows, [
    {key: "bracket", label: "bracket"},
    {key: "games", label: "games", fmt: (x) => String(x)},
    {key: "wins", label: "wins", fmt: (x) => String(x)},
    {key: "winrate", label: "winrate %", fmt: (x) => fmt(x, 1)},
  ]);

  const triples = (DATA.triple_rows || []).slice(0, state.topTriples);
  table(qs("#tblTriples"), triples, [
    {key: "player", label: "player"},
    {key: "commander", label: "commander"},
    {key: "bracket", label: "bracket"},
    {key: "games", label: "games", fmt: (x) => String(x)},
    {key: "wins", label: "wins", fmt: (x) => String(x)},
    {key: "winrate", label: "winrate %", fmt: (x) => fmt(x, 1)},
    {key: "weighted_wr", label: "weighted %", fmt: (x) => fmt(x, 1)},
    {key: "bpi", label: "bpi", fmt: (x) => x === null ? "" : fmt(x, 2)},
    {key: "bpi_label", label: "bpi label"},
    {key: "delta_coverage", label: "coverage %", fmt: (x) => x === null ? "" : fmt(x, 1)},
    {key: "avg_table_bracket", label: "avg table", fmt: (x) => x === null ? "" : fmt(x, 2)},
  ]);

  const uniques = (DATA.unique_triples_rows || []).slice(0, state.maxUnique);
  table(qs("#tblUniqueTriples"), uniques, [
    {key: "commander", label: "commander"},
    {key: "player", label: "player"},
    {key: "bracket", label: "bracket"},
    {key: "entries", label: "entries", fmt: (x) => String(x)},
  ]);

  qs("#buildInfo").textContent = `Build: ${DATA.generated_at || ""}`;
}

readQuery();

fetch("../data/stats.v1.json")
  .then(r => r.json())
  .then(j => { DATA = j; init(); render(); })
  .catch(err => {
    console.error(err);
    qs("#buildInfo").textContent = "Errore nel caricare stats.v1.json";
  });
