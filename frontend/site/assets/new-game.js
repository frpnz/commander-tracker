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
  const downloadBtn = $("downloadBtn");

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

  // Autocomplete menus (custom dropdowns; <datalist> is not reliable cross-browser).
  const playerMenu = $("playerMenu");
  const commanderMenu = $("commanderMenu");

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

  // --- Shared autocomplete helpers ---
  function renderMenu(menuEl, items, onSelect) {
    if (!menuEl) return;
    menuEl.innerHTML = "";
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "ac-empty";
      empty.textContent = "Nessun suggerimento";
      menuEl.appendChild(empty);
    } else {
      for (let i = 0; i < items.length; i++) {
        const it = items[i];
        const div = document.createElement("div");
        div.className = "ac-item";
        div.textContent = it;
        div.dataset.idx = String(i);
        div.addEventListener("mousedown", (e) => {
          // mousedown (not click) so we can select before input loses focus.
          e.preventDefault();
          onSelect(it);
        });
        menuEl.appendChild(div);
      }
    }
    menuEl.hidden = false;
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

  function getAllPlayers() {
    const merged = new Set([...(basePlayers || []), ...entries.map(e => e.player)]);
    return Array.from(merged).filter(Boolean).sort((a, b) => a.localeCompare(b, "it"));
  }

  function syncPlayersUI() {
    // Update player suggestions only when relevant.
    if (document.activeElement === inPlayer) updatePlayerMenu();
  }

  // --- Player autocomplete (custom dropdown) ---
  let playerOpen = false;
  let playerActive = -1;
  /** @type {string[]} */
  let playerCurrentItems = [];

  function closePlayerMenu() {
    if (!playerMenu) return;
    playerMenu.hidden = true;
    playerOpen = false;
    playerActive = -1;
    playerCurrentItems = [];
  }

  function setPlayerActive(idx) {
    if (!playerMenu) return;
    const children = Array.from(playerMenu.querySelectorAll(".ac-item"));
    for (const el of children) el.classList.remove("active");
    if (idx < 0 || idx >= children.length) {
      playerActive = -1;
      return;
    }
    playerActive = idx;
    const el = children[idx];
    el.classList.add("active");
    try { el.scrollIntoView({ block: "nearest" }); } catch (_e) {}
  }

  function selectPlayer(name) {
    inPlayer.value = String(name || "");
    closePlayerMenu();
    // Player selection affects commander suggestions + bracket auto.
    closeCommanderMenu();
    updateCommanderMenu();
    updateBracketAuto();
  }

  function updatePlayerMenu() {
    const list = getAllPlayers();
    const ranked = rankSuggestions(list, inPlayer.value);
    playerCurrentItems = ranked;
    playerActive = -1;
    renderMenu(playerMenu, ranked, selectPlayer);
    playerOpen = true;
  }

  // --- Commander autocomplete (custom dropdown) ---
  let commanderOpen = false;
  let commanderActive = -1;
  /** @type {string[]} */
  let commanderCurrentItems = [];

  function getCommandersForPlayer(playerName) {
    const p = normalizeName(playerName);
    const fromStats = (p && playerToCommanders.has(p)) ? (playerToCommanders.get(p) || []) : (baseCommanders || []);
    const fromEntries = entries.filter(e => e.player === p).map(e => e.commander);
    return Array.from(new Set([...(fromStats || []), ...(fromEntries || [])]))
      .filter(Boolean)
      .sort((a, b) => a.localeCompare(b, "it"));
  }

  function rankSuggestions(items, qRaw) {
    const q = normalizeName(qRaw).toLocaleLowerCase("it");
    if (!q) return items.slice(0, 50);
    const starts = [];
    const contains = [];
    for (const it of items) {
      const s = String(it);
      const sl = s.toLocaleLowerCase("it");
      if (sl.startsWith(q)) starts.push(s);
      else if (sl.includes(q)) contains.push(s);
    }
    return [...starts, ...contains].slice(0, 50);
  }

  function closeCommanderMenu() {
    if (!commanderMenu) return;
    commanderMenu.hidden = true;
    commanderOpen = false;
    commanderActive = -1;
    commanderCurrentItems = [];
  }

  function renderCommanderMenu(items) {
    if (!commanderMenu) return;
    commanderMenu.innerHTML = "";
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "ac-empty";
      empty.textContent = "Nessun suggerimento";
      commanderMenu.appendChild(empty);
      commanderCurrentItems = [];
      commanderActive = -1;
    } else {
      commanderCurrentItems = items;
      commanderActive = -1;
      for (let i = 0; i < items.length; i++) {
        const it = items[i];
        const div = document.createElement("div");
        div.className = "ac-item";
        div.textContent = it;
        div.dataset.idx = String(i);
        div.addEventListener("mousedown", (e) => {
          // mousedown (not click) so we can select before input loses focus.
          e.preventDefault();
          selectCommander(it);
        });
        commanderMenu.appendChild(div);
      }
    }
    commanderMenu.hidden = false;
    commanderOpen = true;
  }

  function setCommanderActive(idx) {
    if (!commanderMenu) return;
    const children = Array.from(commanderMenu.querySelectorAll(".ac-item"));
    for (const el of children) el.classList.remove("active");
    if (idx < 0 || idx >= children.length) {
      commanderActive = -1;
      return;
    }
    commanderActive = idx;
    const el = children[idx];
    el.classList.add("active");
    // Ensure visible
    try { el.scrollIntoView({ block: "nearest" }); } catch (_e) {}
  }

  function selectCommander(name) {
    inCommander.value = String(name || "");
    closeCommanderMenu();
    updateBracketAuto();
  }

  function updateCommanderMenu() {
    const list = getCommandersForPlayer(inPlayer.value);
    const ranked = rankSuggestions(list, inCommander.value);
    renderCommanderMenu(ranked);
  }

  function setWinner(name) {
    winnerPlayer = name ? String(name) : null;
    winnerNameEl.textContent = winnerPlayer || "—";
    // Export is allowed even without a winner. Validation happens on import
    // (admin) or when the user later updates the winner.
    if (downloadBtn) downloadBtn.disabled = false;
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
    closeCommanderMenu();
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

    // Allow the same player to appear multiple times (e.g., multiple commanders).
    // Winner selection is by player name, so all rows for that player will show 🏆.

    if (editingIndex != null) {
      entries[editingIndex] = entry;
    } else {
      entries.push(entry);
    }

    // If winner not set yet, keep badge as-is.
    clearWinnerIfMissing();
    syncPlayersUI();
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
      syncPlayersUI();
      renderEntriesTable();
      return;
    }
    if (btn.classList.contains("editBtn")) {
      const entry = entries[idx];
      editingIndex = idx;
      inPlayer.value = entry.player;
      // Refresh commander suggestions for the selected player.
      closeCommanderMenu();
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
    // Winner is optional. If provided, it must exist among the players.
    if (winnerPlayer && !entries.some(e => e.player === winnerPlayer)) {
      throw new Error("Il vincitore deve essere uno dei player inseriti.");
    }

    // Duplicates are allowed (same player can appear multiple times with different commanders).

    return {
      version: "game.v1",
      played_at: playedAt,
      winner_player: winnerPlayer || null,
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

      syncPlayersUI();
      closePlayerMenu();
      closeCommanderMenu();
    } catch (_e) {
      // silent: user can still type freely
      basePlayers = [];
      baseCommanders = [];
      syncPlayersUI();
      closePlayerMenu();
      closeCommanderMenu();
    }
  }

  function onPlayerChanged() {
    // Keep player suggestions in sync with typed query.
    if (document.activeElement === inPlayer) updatePlayerMenu();
    // Player change affects commander suggestions.
    if (document.activeElement === inCommander) updateCommanderMenu();
    // Changing player may enable better bracket auto for the current commander.
    updateBracketAuto();
  }

  function onPlayerFocus() {
    updatePlayerMenu();
  }

  function onPlayerBlur() {
    // Delay so mousedown selection can run.
    setTimeout(() => {
      if (document.activeElement !== inPlayer) closePlayerMenu();
    }, 80);
  }

  function onPlayerKeyDown(e) {
    if (e.key === "ArrowDown") {
      if (!playerOpen) updatePlayerMenu();
      e.preventDefault();
      const next = Math.min((playerActive < 0 ? -1 : playerActive) + 1, playerCurrentItems.length - 1);
      setPlayerActive(next);
      return;
    }
    if (e.key === "ArrowUp") {
      if (!playerOpen) updatePlayerMenu();
      e.preventDefault();
      const prev = Math.max((playerActive < 0 ? playerCurrentItems.length : playerActive) - 1, 0);
      setPlayerActive(prev);
      return;
    }
    if (e.key === "Escape") {
      if (playerOpen) {
        e.preventDefault();
        closePlayerMenu();
      }
      return;
    }
    if (e.key === "Enter") {
      // If a suggestion is highlighted, select it.
      if (playerOpen && playerActive >= 0 && playerActive < playerCurrentItems.length) {
        e.preventDefault();
        selectPlayer(playerCurrentItems[playerActive]);
        return;
      }
      // Otherwise, go to commander (don't try to add the entry yet).
      e.preventDefault();
      closePlayerMenu();
      focusNext(inPlayer);
      return;
    }
  }

  function onCommanderChanged() {
    // Keep menu in sync with typed query.
    if (document.activeElement === inCommander) updateCommanderMenu();
    updateBracketAuto();
  }

  function onCommanderFocus() {
    updateCommanderMenu();
  }

  function onCommanderBlur() {
    // Delay so mousedown selection can run.
    setTimeout(() => {
      if (document.activeElement !== inCommander) closeCommanderMenu();
    }, 80);
  }

  function onCommanderKeyDown(e) {
    if (e.key === "ArrowDown") {
      if (!commanderOpen) updateCommanderMenu();
      e.preventDefault();
      const next = Math.min((commanderActive < 0 ? -1 : commanderActive) + 1, commanderCurrentItems.length - 1);
      setCommanderActive(next);
      return;
    }
    if (e.key === "ArrowUp") {
      if (!commanderOpen) updateCommanderMenu();
      e.preventDefault();
      const prev = Math.max((commanderActive < 0 ? commanderCurrentItems.length : commanderActive) - 1, 0);
      setCommanderActive(prev);
      return;
    }
    if (e.key === "Escape") {
      if (commanderOpen) {
        e.preventDefault();
        closeCommanderMenu();
      }
      return;
    }
    if (e.key === "Enter") {
      if (commanderOpen && commanderActive >= 0 && commanderActive < commanderCurrentItems.length) {
        e.preventDefault();
        selectCommander(commanderCurrentItems[commanderActive]);
        return;
      }
      // Otherwise, Enter adds the entry (handled here to avoid conflicts).
      e.preventDefault();
      try { upsertEntry(); } catch (err) { setStatus(err.message || String(err), "error"); }
      return;
    }
  }

  function onKeyDownAdd(e) {
    if (e.key === "Enter") {
      // Enter adds the entry instead of submitting the whole form.
      e.preventDefault();
      try { upsertEntry(); } catch (err) { setStatus(err.message || String(err), "error"); }
    }
  }

  function setupKeyboardAvoidance() {
    // Mobile Firefox may overlay the virtual keyboard without resizing layout,
    // which can hide the bottom action buttons. If supported, VisualViewport
    // lets us measure the "covered" area and expose it to CSS.
    const vv = window.visualViewport;
    if (!vv) return;

    const root = document.documentElement;
    function updateInset() {
      // Covered area = full layout viewport height - visual viewport height - offset
      // (clamped to >= 0). Add a small cushion.
      const covered = Math.max(0, window.innerHeight - (vv.height + vv.offsetTop));
      root.style.setProperty("--keyboard-inset", (covered ? (covered + 12) : 0) + "px");
    }

    vv.addEventListener("resize", updateInset);
    vv.addEventListener("scroll", updateInset);
    updateInset();

    // Also, on focus, gently scroll the focused field into view.
    function onFocus(e) {
      const el = e.target;
      if (!el || !el.scrollIntoView) return;
      // Delay one frame so the keyboard/viewport has applied.
      requestAnimationFrame(() => {
        try { el.scrollIntoView({ block: "center", behavior: "smooth" }); } catch (_e) { el.scrollIntoView(); }
      });
    }
    form.addEventListener("focusin", onFocus);
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
    inPlayer.addEventListener("focus", onPlayerFocus);
    inPlayer.addEventListener("blur", onPlayerBlur);
    inPlayer.addEventListener("keydown", onPlayerKeyDown);
    inCommander.addEventListener("input", onCommanderChanged);
    inCommander.addEventListener("change", onCommanderChanged);
    inCommander.addEventListener("focus", onCommanderFocus);
    inCommander.addEventListener("blur", onCommanderBlur);
    inCommander.addEventListener("keydown", onCommanderKeyDown);

    // Enter handling
    // Commander uses its own key handling (Arrow/Enter/Esc + add entry).
    inBracket.addEventListener("keydown", onKeyDownAdd);

    clearWinnerBtn.addEventListener("click", () => setWinner(null));
    form.addEventListener("submit", onSubmit);

    setupKeyboardAvoidance();

    loadSuggestions();
  }

  init();
})();
