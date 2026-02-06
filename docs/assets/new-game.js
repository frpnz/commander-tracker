/* New game JSON generator (static site).
 * Produces a single-game payload that can be imported by admin_stdlib.py.
 */
(function () {
  const $ = (id) => document.getElementById(id);

  const form = $("gameForm");
  const entriesEl = $("entries");
  const addRowBtn = $("addRow");
  const statusEl = $("status");
  const copyBtn = $("copyBtn");

  const playersList = $("playersList");
  const commandersList = $("commandersList");

  // commander -> sorted unique bracket list (integers)
  const commanderBrackets = new Map();

  // Base suggestions loaded from stats.v1.json (players/commanders)
  let basePlayers = [];

  const DEFAULT_ROWS = 4;

  function pad2(n){ return String(n).padStart(2, "0"); }

  function toSqliteDatetime(dtLocalValue){
    // dtLocalValue: "YYYY-MM-DDTHH:MM" or "YYYY-MM-DDTHH:MM:SS"
    if (!dtLocalValue) return "";
    const [d, tRaw] = dtLocalValue.split("T");
    const t = (tRaw || "00:00").split(":");
    const hh = pad2(t[0] || 0);
    const mm = pad2(t[1] || 0);
    const ss = pad2(t[2] || 0);
    return `${d} ${hh}:${mm}:${ss}`;
  }

  function setStatus(msg, kind){
    statusEl.style.display = "block";
    statusEl.textContent = msg;
    statusEl.style.color = kind === "error" ? "rgba(255,120,120,.95)" : "rgba(180,255,200,.95)";
  }

  function clearStatus(){
    statusEl.style.display = "none";
    statusEl.textContent = "";
  }

  function makeRow(i){
    const row = document.createElement("div");
    row.className = "grid3";
    row.dataset.row = String(i);

    row.innerHTML = `
      <label>Player
        <input class="player" list="playersList" placeholder="Nome player" required/>
      </label>
      <label>Commander
        <input class="commander" list="commandersList" placeholder="Nome commander" required/>
      </label>
      <label>Bracket
        <select class="bracket">
          <option value="">—</option>
          <option value="1">1</option>
          <option value="2">2</option>
          <option value="3">3</option>
          <option value="4">4</option>
          <option value="5">5</option>
        </select>
      </label>
    `;

    const del = document.createElement("button");
    del.type = "button";
    del.className = "pill";
    del.textContent = "Rimuovi";
    del.style.justifySelf = "end";
    del.style.marginTop = "22px";
    del.addEventListener("click", () => {
      wrap.remove();
      syncWinnerSuggestions();
    });

    // On narrow screens grid3 will wrap; keep delete button after row
    const wrap = document.createElement("div");
    wrap.style.display = "grid";
    wrap.style.gridTemplateColumns = "1fr";
    wrap.style.gap = "8px";
    wrap.appendChild(row);
    wrap.appendChild(del);

    // bracket suggestions based on commander (from stats.v1.json)
    const commanderInput = wrap.querySelector(".commander");
    const bracketSelect = wrap.querySelector(".bracket");
    commanderInput?.addEventListener("change", () => {
      setBracketOptionsForCommander(bracketSelect, commanderInput.value);
    });
    commanderInput?.addEventListener("blur", () => {
      setBracketOptionsForCommander(bracketSelect, commanderInput.value);
    });

    // update winner suggestions as you type
    wrap.addEventListener("input", (e) => {
      if (e.target && e.target.classList && e.target.classList.contains("player")) {
        syncWinnerSuggestions();
      }
    });

    return wrap;
  }

  function syncWinnerSuggestions(){
    // Winner is free text but we can help: keep the datalist updated with
    // (a) players seen in historical stats and (b) players currently typed in entries.
    const entryPlayers = Array.from(entriesEl.querySelectorAll("input.player"))
      .map((el) => (el.value || "").trim())
      .filter((v) => v.length > 0);

    const set = new Set([...(basePlayers || []), ...entryPlayers]);
    const merged = Array.from(set).sort((a,b) => a.localeCompare(b, "it"));

    playersList.innerHTML = merged.map((p) => `<option value="${escapeHtml(p)}"></option>`).join("");
  }

  function addRow(){
    const w = makeRow(Date.now());
    entriesEl.appendChild(w);
    syncWinnerSuggestions();
    // initialize bracket options (blank until commander chosen)
    const commanderInput = w.querySelector('.commander');
    const bracketSelect = w.querySelector('.bracket');
    setBracketOptionsForCommander(bracketSelect, commanderInput?.value || "");
  }

  function collect(){
    clearStatus();
    const playedAt = toSqliteDatetime($("playedAt").value);
    const winner = ($("winner").value || "").trim();
    const notes = ($("notes").value || "").trim();

    const entryWraps = Array.from(entriesEl.children);
    const entries = [];
    for (const w of entryWraps){
      const player = (w.querySelector(".player")?.value || "").trim();
      const commander = (w.querySelector(".commander")?.value || "").trim();
      const bracketRaw = (w.querySelector(".bracket")?.value || "").trim();
      const bracket = bracketRaw === "" ? null : Number.parseInt(bracketRaw, 10);

      // Allow unused empty rows (both empty)
      if (!player && !commander && bracketRaw === "") continue;

      // Partial row => error
      if (!player || !commander){
        throw new Error("Completa Player e Commander per ogni entry (o lascia la riga completamente vuota).");
      }

      if (bracket !== null && (!Number.isFinite(bracket) || bracket < 1 || bracket > 5)){
        throw new Error("Bracket deve essere vuoto oppure un numero tra 1 e 5.");
      }

      entries.push({ player, commander, bracket });
    }

    if (entries.length < 2) throw new Error("Inserisci almeno 2 entries (player/commander).");

    if (!playedAt) throw new Error("Inserisci data e ora.");
    if (!winner) throw new Error("Inserisci il vincitore.");

    // Basic sanity: winner should be one of players (helps avoid typos)
    const players = new Set(entries.map(e => e.player));
    if (!players.has(winner)){
      throw new Error("Il vincitore deve essere uno dei player inseriti nelle entries (controlla spelling).");
    }

    // Avoid duplicate players
    if (players.size !== entries.length){
      throw new Error("Ogni player deve comparire una sola volta nelle entries.");
    }

    return {
      version: "game.v1",
      played_at: playedAt,
      winner_player: winner,
      notes: notes || null,
      entries,
    };
  }

  function filenameFrom(payload){
    // game_YYYYMMDD_HHMM.json
    const dt = (payload.played_at || "").replace(/[-:]/g, "").replace(" ", "_").slice(0, 13); // YYYYMMDD_HHMM
    return `game_${dt}.json`;
  }

  async function copyToClipboard(text){
    if (navigator.clipboard && navigator.clipboard.writeText){
      await navigator.clipboard.writeText(text);
      return;
    }
    // fallback
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }

  async function onCopy(){
    try{
      const payload = collect();
      const text = JSON.stringify(payload, null, 2);
      await copyToClipboard(text);
      setStatus("JSON copiato negli appunti.", "ok");
    }catch(err){
      setStatus(err.message || String(err), "error");
    }
  }

  function onSubmit(e){
    e.preventDefault();
    try{
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
    }catch(err){
      setStatus(err.message || String(err), "error");
    }
  }

  async function loadSuggestions(){
    try{
      const root = new URL("..", window.location.href);
      const url = new URL("data/stats.v1.json", root).toString();
      const r = await fetch(url, { cache: "no-store" });
      if (!r.ok) throw new Error("stats.v1.json non disponibile");
      const data = await r.json();

      // Build commander -> bracket(s) map from stats data
      commanderBrackets.clear();
      const byPc = Array.isArray(data?.by_player_commander) ? data.by_player_commander : [];
      for (const row of byPc){
        const c = (row?.commander || "").trim();
        const b = row?.bracket;
        if (!c || b == null) continue;
        const bi = Number.isFinite(b) ? b : Number.parseInt(String(b), 10);
        if (!Number.isFinite(bi)) continue;
        if (bi < 1 || bi > 5) continue;
        const arr = commanderBrackets.get(c) || [];
        if (!arr.includes(bi)) arr.push(bi);
        commanderBrackets.set(c, arr);
      }
      for (const [k, arr] of commanderBrackets.entries()){
        arr.sort((a,b)=>a-b);
        commanderBrackets.set(k, arr);
      }

      const filters = data?.filters || {};
      const players = Array.isArray(filters.players) ? filters.players : [];
      const commanders = Array.isArray(filters.commanders) ? filters.commanders : [];

      basePlayers = players.slice();
      // playersList is also used by the Winner input, so we merge base + current entries.
      commandersList.innerHTML = commanders.map((c) => `<option value="${escapeHtml(c)}"></option>`).join("");
      syncWinnerSuggestions();
    }catch(_e){
      // silent: user can still type freely
    }
  }

  
  function setBracketOptionsForCommander(selectEl, commanderName){
    if (!selectEl) return;
    const name = (commanderName || "").trim();
    const brackets = commanderBrackets.get(name);
    const current = selectEl.value;
    const baseOpts = ["", "1","2","3","4","5"];

    let opts = baseOpts;
    if (Array.isArray(brackets) && brackets.length > 0){
      // keep blank + known brackets
      opts = ["", ...brackets.map((b) => String(b))];
    }

    selectEl.innerHTML = opts.map((v) => {
      const label = v === "" ? "—" : v;
      return `<option value="${v}">${label}</option>`;
    }).join("");

    // Default selection:
    if (Array.isArray(brackets) && brackets.length === 1){
      selectEl.value = String(brackets[0]);
    } else if (opts.includes(current)){
      selectEl.value = current;
    } else {
      selectEl.value = "";
    }
  }

  function escapeHtml(s){
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function init(){
    // set datetime default to now
    const now = new Date();
    const y = now.getFullYear();
    const m = pad2(now.getMonth()+1);
    const d = pad2(now.getDate());
    const hh = pad2(now.getHours());
    const mm = pad2(now.getMinutes());
    $("playedAt").value = `${y}-${m}-${d}T${hh}:${mm}`;

    entriesEl.innerHTML = "";
    for (let i=0;i<DEFAULT_ROWS;i++) addRow();

    addRowBtn.addEventListener("click", addRow);
    copyBtn.addEventListener("click", onCopy);
    form.addEventListener("submit", onSubmit);

    loadSuggestions();
  }

  init();
})();
