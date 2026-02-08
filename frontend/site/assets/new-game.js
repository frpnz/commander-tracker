/* New game JSON generator (static site).
 * Produces a single-game payload that can be imported by admin_stdlib.py.
 *
 * UX: single input row (Player / Commander / Bracket) -> Enter to append.
 * Autocomplete is suggestive (never blocking): user can create new players
 * and new commanders (including new commander for existing player).
 */
(function () {
  const $ = (id) => document.getElementById(id);

  const form = $("gameForm");
  const statusEl = $("status");
  const copyBtn = $("copyBtn");

  // Single-row inputs
  const inPlayer = $("inPlayer");
  const inCommander = $("inCommander");
  const inBracket = $("inBracket");
  const addEntryBtn = $("addEntry");

  // Winner UI
  const winnerNameEl = $("winnerName");
  const clearWinnerBtn = $("clearWinner");

  // Table
  const entriesBody = $("entriesBody");

  // Datalists
  const playersList = $("playersList");
  const commandersList = $("commandersList");

  // Suggestions
  let basePlayers = [];
  let baseCommanders = [];

  // player -> [commanders]
  const playerToCommanders = new Map();
  // (player||commander) -> bracket mode
  const playerCommanderBracket = new Map();
  // commander -> bracket mode
  const commanderBracketMode = new Map();

  // State
  /** @type {{player:string, commander:string, bracket:(number|null)}[]} */
  let entries = [];
  /** @type {string|null} */
  let winnerPlayer = null;
  /** @type {number|null} */
  let editingIndex = null;

  function pad2(n) { return String(n).padStart(2, "0"); }

  function toSqliteDatetime(dtLocalValue) {
    // dtLocalValue: "YYYY-MM-DDTHH:MM" or "YYYY-MM-DDTHH:MM:SS"
    if (!dtLocalValue) return "";
    const [d, tRaw] = dtLocalValue.split("T");
    const t = (tRaw || "00:00").split(":");
    const hh = pad2(t[0] || 0);
    const mm = pad2(t[1] || 0);
    const ss = pad2(t[2] || 0);
    return `${d} ${hh}:${mm}:${ss}`;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function setStatus(msg, kind) {
    statusEl.style.display = "block";
    statusEl.textContent = msg;
    statusEl.style.color = kind === "error" ? "rgba(255,120,120,.95)" : "rgba(180,255,200,.95)";
  }

  function clearStatus() {
    statusEl.style.display = "none";
    statusEl.textContent = "";
  }

  function normalizeName(s) {
    return (s || "").trim();
  }

  function syncPlayersDatalist() {
    const merged = new Set([...(basePlayers || []), ...entries.map(e => e.player)]);
    const arr = Array.from(merged).filter(Boolean).sort((a, b) => a.localeCompare(b, "it"));
    playersList.innerHTML = arr.map(p => `<option value="${escapeHtml(p)}"></option>`).join("");
  }

  function setCommandersDatalistForPlayer(playerName) {
    const p = normalizeName(playerName);
    const arr = (p && playerToCommanders.has(p))
      ? (playerToCommanders.get(p) || [])
      : (baseCommanders || []);
    const merged = Array.from(new Set([...(arr || []), ...entries.filter(e => e.player === p).map(e => e.commander)]))
      .filter(Boolean)
      .sort((a, b) => a.localeCompare(b, "it"));
    commandersList.innerHTML = merged.map(c => `<option value="${escapeHtml(c)}"></option>`).join("");
  }

  function setWinner(name) {
    winnerPlayer = name ? String(name) : null;
    winnerNameEl.textContent = winnerPlayer || "—";
    renderEntriesTable();
  }

  function clearWinnerIfMissing() {
    if (!winnerPlayer) return;
    const has = entries.some(e => e.player === winnerPlayer);
    if (!has) setWinner(null);
  }

  function bracketModeFromCounts(counts) {
    let bestB = null;
    let bestN = -1;
    for (const [bStr, n] of counts.entries()) {
      const b = Number.parseInt(bStr, 10);
      if (!Number.isFinite(b)) continue;
      if (n > bestN) { bestN = n; bestB = b; }
    }
    return bestB;
  }

  function updateBracketAuto() {
    // Only auto-fill if currently blank.
    if (!inBracket || inBracket.value !== "") return;
    const p = normalizeName(inPlayer.value);
    const c = normalizeName(inCommander.value);
    if (!c) return;

    const key = `${p}||${c}`;
    const bPc = playerCommanderBracket.get(key);
    const bC = commanderBracketMode.get(c);
    const b = (bPc != null) ? bPc : (bC != null ? bC : null);
    if (b != null && b >= 1 && b <= 5) inBracket.value = String(b);
  }

  function focusNext(from) {
    if (from === inPlayer) { inCommander.focus(); inCommander.select?.(); return; }
    if (from === inCommander) { inBracket.focus(); return; }
    inPlayer.focus();
  }

  function resetInputRow() {
    inPlayer.value = "";
    inCommander.value = "";
    inBracket.value = "";
    editingIndex = null;
    addEntryBtn.textContent = "Aggiungi";
    setCommandersDatalistForPlayer("");
    inPlayer.focus();
  }

  function validateEntry(player, commander, bracketRaw) {
    const p = normalizeName(player);
    const c = normalizeName(commander);
    if (!p) throw new Error("Inserisci il nome del player.");
    if (!c) throw new Error("Inserisci il nome del commander.");
    let bracket = null;
    if ((bracketRaw || "").trim() !== "") {
      const bi = Number.parseInt(String(bracketRaw).trim(), 10);
      if (!Number.isFinite(bi) || bi < 1 || bi > 5) {
        throw new Error("Bracket deve essere vuoto oppure un numero tra 1 e 5.");
      }
      bracket = bi;
    }
    return { player: p, commander: c, bracket };
  }

  function upsertEntry() {
    clearStatus();
    const entry = validateEntry(inPlayer.value, inCommander.value, inBracket.value);

    // Unique players constraint (same as before). If editing, allow replacing self.
    const duplicateIndex = entries.findIndex((e, idx) => e.player === entry.player && idx !== (editingIndex ?? -1));
    if (duplicateIndex !== -1) {
      throw new Error("Ogni player deve comparire una sola volta nelle entries.");
    }

    if (editingIndex != null) {
      entries[editingIndex] = entry;
    } else {
      entries.push(entry);
    }

    // If winner not set yet, keep badge as-is.
    clearWinnerIfMissing();
    syncPlayersDatalist();
    renderEntriesTable();
    resetInputRow();
  }

  function renderEntriesTable() {
    if (!entriesBody) return;
    const rows = entries.map((e, idx) => {
      const isWin = winnerPlayer && e.player === winnerPlayer;
      const bracketLabel = e.bracket == null ? "—" : String(e.bracket);
      return `
        <tr data-idx="${idx}">
          <td>${escapeHtml(e.player)}</td>
          <td>${escapeHtml(e.commander)}</td>
          <td class="num">${escapeHtml(bracketLabel)}</td>
          <td class="num">
            <button class="pill winBtn" type="button" title="Imposta vincitore" style="padding:6px 10px; ${isWin ? "border-color: rgba(110,231,255,.55); background: rgba(110,231,255,.16);" : ""}">
              ${isWin ? "🏆" : "—"}
            </button>
          </td>
          <td class="num">
            <button class="pill editBtn" type="button" style="padding:6px 10px;">Modifica</button>
            <button class="pill delBtn" type="button" style="padding:6px 10px; margin-left:6px;">Rimuovi</button>
          </td>
        </tr>`;
    }).join("");
    entriesBody.innerHTML = rows || "";
  }

  function onTableClick(e) {
    const btn = e.target;
    if (!btn || !btn.closest) return;
    const tr = btn.closest("tr");
    if (!tr) return;
    const idx = Number.parseInt(tr.dataset.idx || "-1", 10);
    if (!Number.isFinite(idx) || idx < 0 || idx >= entries.length) return;

    if (btn.classList.contains("winBtn")) {
      setWinner(entries[idx].player);
      return;
    }
    if (btn.classList.contains("delBtn")) {
      const removed = entries.splice(idx, 1)[0];
      if (removed && removed.player === winnerPlayer) setWinner(null);
      syncPlayersDatalist();
      renderEntriesTable();
      return;
    }
    if (btn.classList.contains("editBtn")) {
      const entry = entries[idx];
      editingIndex = idx;
      inPlayer.value = entry.player;
      setCommandersDatalistForPlayer(entry.player);
      inCommander.value = entry.commander;
      inBracket.value = entry.bracket == null ? "" : String(entry.bracket);
      addEntryBtn.textContent = "Salva";
      inPlayer.focus();
      return;
    }
  }

  function collect() {
    clearStatus();
    const playedAt = toSqliteDatetime($("playedAt").value);
    const notes = (($("notes")?.value) || "").trim();

    if (!playedAt) throw new Error("Inserisci data e ora.");
    if (entries.length < 2) throw new Error("Inserisci almeno 2 entries (player/commander).");
    if (!winnerPlayer) throw new Error("Seleziona il vincitore (🏆) nella lista dei giocatori.");

    // winner must exist
    if (!entries.some(e => e.player === winnerPlayer)) {
      throw new Error("Il vincitore deve essere uno dei player inseriti.");
    }

    // Ensure players unique (should be enforced at insert)
    const players = new Set(entries.map(e => e.player));
    if (players.size !== entries.length) {
      throw new Error("Ogni player deve comparire una sola volta nelle entries.");
    }

    return {
      version: "game.v1",
      played_at: playedAt,
      winner_player: winnerPlayer,
      notes: notes || null,
      entries: entries.map(e => ({
        player: e.player,
        commander: e.commander,
        bracket: e.bracket,
      })),
    };
  }

  function filenameFrom(payload) {
    // game_YYYYMMDD_HHMM.json
    const dt = (payload.played_at || "").replace(/[-:]/g, "").replace(" ", "_").slice(0, 13);
    return `game_${dt}.json`;
  }

  async function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }

  async function onCopy() {
    try {
      const payload = collect();
      const text = JSON.stringify(payload, null, 2);
      await copyToClipboard(text);
      setStatus("JSON copiato negli appunti.", "ok");
    } catch (err) {
      setStatus(err.message || String(err), "error");
    }
  }

  function onSubmit(e) {
    e.preventDefault();
    try {
      const payload = collect();
      const text = JSON.stringify(payload, null, 2);
      const blob = new Blob([text], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = filenameFrom(payload);
      document.body.appendChild(a);
      a.click();
      a.remove();
      setStatus("File generato. Importalo in admin (Importa JSON).", "ok");
    } catch (err) {
      setStatus(err.message || String(err), "error");
    }
  }

  function quantizeBracket(b) {
    const bi = Number.isFinite(b) ? b : Number.parseInt(String(b), 10);
    if (!Number.isFinite(bi)) return null;
    if (bi < 1 || bi > 5) return null;
    return bi;
  }

  async function loadSuggestions() {
    try {
      const root = new URL("..", window.location.href);
      const url = new URL("data/stats.v1.json", root).toString();
      const r = await fetch(url, { cache: "no-store" });
      if (!r.ok) throw new Error("stats.v1.json non disponibile");
      const data = await r.json();

      const filters = data?.filters || {};
      basePlayers = Array.isArray(filters.players) ? filters.players.slice() : [];
      baseCommanders = Array.isArray(filters.commanders) ? filters.commanders.slice() : [];

      // Build player -> commanders and bracket modes
      playerToCommanders.clear();
      playerCommanderBracket.clear();
      commanderBracketMode.clear();

      const byPc = Array.isArray(data?.by_player_commander) ? data.by_player_commander : [];

      // Count brackets
      const pcCounts = new Map(); // key -> Map(bracket -> n)
      const cCounts = new Map();  // commander -> Map(bracket -> n)

      for (const row of byPc) {
        const p = normalizeName(row?.player);
        const c = normalizeName(row?.commander);
        const b = quantizeBracket(row?.bracket);
        if (!p || !c) continue;

        // player -> commanders
        const arr = playerToCommanders.get(p) || [];
        if (!arr.includes(c)) arr.push(c);
        playerToCommanders.set(p, arr);

        if (b != null) {
          const key = `${p}||${c}`;
          if (!pcCounts.has(key)) pcCounts.set(key, new Map());
          const m1 = pcCounts.get(key);
          m1.set(String(b), (m1.get(String(b)) || 0) + (Number(row?.games) || 1));

          if (!cCounts.has(c)) cCounts.set(c, new Map());
          const m2 = cCounts.get(c);
          m2.set(String(b), (m2.get(String(b)) || 0) + (Number(row?.games) || 1));
        }
      }

      // Sort commanders lists per player
      for (const [p, arr] of playerToCommanders.entries()) {
        arr.sort((a, b) => a.localeCompare(b, "it"));
        playerToCommanders.set(p, arr);
      }

      // Convert counts to modes
      for (const [key, counts] of pcCounts.entries()) {
        const b = bracketModeFromCounts(counts);
        if (b != null) playerCommanderBracket.set(key, b);
      }
      for (const [c, counts] of cCounts.entries()) {
        const b = bracketModeFromCounts(counts);
        if (b != null) commanderBracketMode.set(c, b);
      }

      syncPlayersDatalist();
      setCommandersDatalistForPlayer("");
    } catch (_e) {
      // silent: user can still type freely
      basePlayers = [];
      baseCommanders = [];
      syncPlayersDatalist();
      setCommandersDatalistForPlayer("");
    }
  }

  function onPlayerChanged() {
    setCommandersDatalistForPlayer(inPlayer.value);
    // Changing player may enable better bracket auto for the current commander.
    updateBracketAuto();
  }

  function onCommanderChanged() {
    updateBracketAuto();
  }

  function onKeyDownAdd(e) {
    if (e.key === "Enter") {
      // Enter adds the entry instead of submitting the whole form.
      e.preventDefault();
      try { upsertEntry(); } catch (err) { setStatus(err.message || String(err), "error"); }
    }
  }

  function init() {
    // set datetime default to now
    const now = new Date();
    const y = now.getFullYear();
    const m = pad2(now.getMonth() + 1);
    const d = pad2(now.getDate());
    const hh = pad2(now.getHours());
    const mm = pad2(now.getMinutes());
    $("playedAt").value = `${y}-${m}-${d}T${hh}:${mm}`;

    entries = [];
    winnerPlayer = null;
    editingIndex = null;
    setWinner(null);
    renderEntriesTable();

    addEntryBtn.addEventListener("click", () => {
      try { upsertEntry(); } catch (err) { setStatus(err.message || String(err), "error"); }
    });

    entriesBody.addEventListener("click", onTableClick);

    inPlayer.addEventListener("input", onPlayerChanged);
    inPlayer.addEventListener("change", onPlayerChanged);
    inCommander.addEventListener("input", onCommanderChanged);
    inCommander.addEventListener("change", onCommanderChanged);

    // Enter handling
    inPlayer.addEventListener("keydown", onKeyDownAdd);
    inCommander.addEventListener("keydown", onKeyDownAdd);
    inBracket.addEventListener("keydown", onKeyDownAdd);

    clearWinnerBtn.addEventListener("click", () => setWinner(null));

    copyBtn.addEventListener("click", onCopy);
    form.addEventListener("submit", onSubmit);

    loadSuggestions();
  }

  init();
})();
