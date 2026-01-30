/* Commander Stats - client side filtering (GitHub Pages friendly)
 *
 * Data source: ../data/stats.v1.json (generated offline by export_stats.py)
 * This script keeps the UI fully static (no backend) and robust against
 * missing/empty fields.
 */

const $ = (sel) => document.querySelector(sel);

function fmtPct(x) {
  const v = x * 100;
  if (!isFinite(v)) return "0.0%";
  return v.toFixed(1) + "%";
}

function makeRateFragment(wins, games) {
  const span = document.createElement("span");
  const rate = games ? wins / games : 0;
  span.innerHTML = `${wins} / ${games} <span class="badge">${fmtPct(rate)}</span>`;
  return span;
}

function setOptions(selectEl, values, keepValue = "") {
  const el = typeof selectEl === "string" ? $(selectEl) : selectEl;
  const prev = keepValue ?? el.value;

  // keep first option ("Tutti")
  while (el.options.length > 1) el.remove(1);

  (values || []).forEach((v) => {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    el.appendChild(opt);
  });

  // restore if possible
  if ([...el.options].some((o) => o.value === prev)) el.value = prev;
  else el.value = "";
}

function qsGet() {
  const p = new URLSearchParams(location.search);
  return {
    player: p.get("player") || "",
    commander: p.get("commander") || "",
  };
}

function qsSet(state) {
  const p = new URLSearchParams();
  if (state.player) p.set("player", state.player);
  if (state.commander) p.set("commander", state.commander);
  const url = `${location.pathname}${p.toString() ? "?" + p.toString() : ""}`;
  history.replaceState(null, "", url);
  return url;
}

function commandersForPlayer(data, player) {
  if (!player) return (data.filters?.commanders || []).slice();
  const set = new Set();
  for (const r of data.by_player_commander || []) {
    if (r.player === player) set.add(r.commander);
  }
  return Array.from(set).sort((a, b) => a.localeCompare(b));
}

function aggregateBracketsFromPairs(rowsPair) {
  const map = new Map();
  for (const r of rowsPair || []) {
    const key = r.bracket === null || r.bracket === undefined || r.bracket === "" ? "n/a" : String(r.bracket);
    const cur = map.get(key) || { bracket: key, wins: 0, games: 0 };
    cur.wins += Number(r.wins || 0);
    cur.games += Number(r.games || 0);
    map.set(key, cur);
  }
  return Array.from(map.values()).sort((a, b) => b.games - a.games || a.bracket.localeCompare(b.bracket));
}

function sortRows(rows, mode, kind) {
  const arr = (rows || []).slice();
  const safeNum = (v) => Number.isFinite(Number(v)) ? Number(v) : 0;
  const wr = (r) => {
    const g = safeNum(r.games);
    return g ? safeNum(r.wins) / g : 0;
  };

  const cmpStr = (a, b) => String(a || "").localeCompare(String(b || ""));
  const alpha = (a, b) => {
    if (kind === "pair") {
      return (
        cmpStr(a.player, b.player) ||
        cmpStr(a.commander, b.commander) ||
        cmpStr(a.bracket, b.bracket)
      );
    }
    if (kind === "bracket") return cmpStr(a.bracket, b.bracket);
    return cmpStr(a.player, b.player);
  };

  switch (mode) {
    case "wins_desc":
      arr.sort((a, b) => safeNum(b.wins) - safeNum(a.wins) || alpha(a, b));
      break;
    case "games_desc":
      arr.sort((a, b) => safeNum(b.games) - safeNum(a.games) || alpha(a, b));
      break;
    case "wr_desc":
      arr.sort((a, b) => wr(b) - wr(a) || safeNum(b.games) - safeNum(a.games) || alpha(a, b));
      break;
    case "alpha":
    default:
      arr.sort(alpha);
      break;
  }
  return arr;
}

function td(text, className) {
  const cell = document.createElement("td");
  if (className) cell.className = className;
  cell.textContent = text;
  return cell;
}

function renderPlayer(rows) {
  const tb = $("#tPlayer tbody");
  tb.innerHTML = "";

  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.appendChild(td(r.player ?? "", ""));
    tr.appendChild(td(String(r.wins ?? 0), "num"));
    tr.appendChild(td(String(r.games ?? 0), "num"));
    const rateCell = document.createElement("td");
    rateCell.className = "num";
    rateCell.appendChild(makeRateFragment(Number(r.wins || 0), Number(r.games || 0)));
    tr.appendChild(rateCell);
    tb.appendChild(tr);
  }
  $("#countPlayer").textContent = `${rows.length} righe`;
}

function renderPair(rows) {
  const tb = $("#tPair tbody");
  tb.innerHTML = "";
  const cap = 400;

  for (const r of rows.slice(0, cap)) {
    const tr = document.createElement("tr");
    tr.appendChild(td(r.player ?? "", ""));
    tr.appendChild(td(r.commander ?? "", ""));
    tr.appendChild(td(r.bracket === null || r.bracket === undefined ? "n/a" : String(r.bracket), ""));
    tr.appendChild(td(String(r.wins ?? 0), "num"));
    tr.appendChild(td(String(r.games ?? 0), "num"));
    const rateCell = document.createElement("td");
    rateCell.className = "num";
    rateCell.appendChild(makeRateFragment(Number(r.wins || 0), Number(r.games || 0)));
    tr.appendChild(rateCell);
    tb.appendChild(tr);
  }

  $("#countPair").textContent = rows.length > cap ? `${cap}/${rows.length} righe` : `${rows.length} righe`;
}

function renderBracket(rows) {
  const tb = $("#tBracket tbody");
  tb.innerHTML = "";
  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.appendChild(td(r.bracket ?? "n/a", ""));
    tr.appendChild(td(String(r.wins ?? 0), "num"));
    tr.appendChild(td(String(r.games ?? 0), "num"));
    const rateCell = document.createElement("td");
    rateCell.className = "num";
    rateCell.appendChild(makeRateFragment(Number(r.wins || 0), Number(r.games || 0)));
    tr.appendChild(rateCell);
    tb.appendChild(tr);
  }
  $("#countBracket").textContent = `${rows.length} righe`;
}

function updateCommanderOptions(data, player, keepCommanderValue = "") {
  setOptions($("#fCommander"), commandersForPlayer(data, player), keepCommanderValue);
}

function buildTables(data) {
  const state = {
    player: $("#fPlayer").value,
    commander: $("#fCommander").value,
  };
  qsSet(state);

  const parts = [];
  if (state.player) parts.push(`player: ${state.player}`);
  if (state.commander) parts.push(`commander: ${state.commander}`);
  $("#hint").textContent = parts.length ? `Filtri attivi → ${parts.join(" · ")}` : "Nessun filtro attivo.";

  const rowsP = sortRows(
    (data.by_player || []).filter((r) => !state.player || r.player === state.player),
    $("#sPlayer")?.value || "alpha",
    "player"
  );
  renderPlayer(rowsP);

  const rowsPair = sortRows(
    (data.by_player_commander || [])
      .filter((r) => !state.player || r.player === state.player)
      .filter((r) => !state.commander || r.commander === state.commander),
    $("#sPair")?.value || "alpha",
    "pair"
  );
  renderPair(rowsPair);

  const rowsBracket = sortRows(
    aggregateBracketsFromPairs(rowsPair),
    $("#sBracket")?.value || "games_desc",
    "bracket"
  );
  renderBracket(rowsBracket);
}

async function main() {
  const res = await fetch("../data/stats.v1.json", { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status} (${res.statusText})`);
  const data = await res.json();

  const games = data.counts?.games ?? 0;
  const entries = data.counts?.entries ?? 0;
  const gen = data.generated_utc ?? "";
  $("#meta").textContent = `${games} game · ${entries} entries${gen ? " · gen " + gen : ""}`;

  setOptions($("#fPlayer"), data.filters?.players || []);

  // Load state from querystring
  const qs = qsGet();
  $("#fPlayer").value = qs.player;
  updateCommanderOptions(data, qs.player, qs.commander);

  const rerender = () => buildTables(data);

  // Player change → Commander options become nested
  $("#fPlayer").addEventListener("change", () => {
    updateCommanderOptions(data, $("#fPlayer").value, $("#fCommander").value);
    rerender();
  });
  $("#fCommander").addEventListener("change", rerender);

  // Sorting dropdowns
  $("#sPlayer")?.addEventListener("change", rerender);
  $("#sPair")?.addEventListener("change", rerender);
  $("#sBracket")?.addEventListener("change", rerender);

  $("#btnReset").addEventListener("click", () => {
    $("#fPlayer").value = "";
    updateCommanderOptions(data, "", "");
    rerender();
  });

  $("#btnLink").addEventListener("click", async () => {
    const url = qsSet({
      player: $("#fPlayer").value,
      commander: $("#fCommander").value,
    });
    try {
      const full = location.origin ? location.origin + url : url;
      await navigator.clipboard.writeText(full);
      $("#hint").textContent = "Link copiato negli appunti ✅";
      setTimeout(rerender, 900);
    } catch {
      prompt("Copia questo link:", url);
    }
  });

  rerender();
}

main().catch((err) => {
  console.error(err);
  const sub = $("#subtitle");
  if (sub) sub.textContent = "Errore nel caricamento dei dati. Vedi console.";
});
