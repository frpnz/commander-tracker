/* Draft page
 * Reads /data/draft.v1.json exported from the separate Draft DB.
 */

// --- Plugin: print value labels on horizontal bars (same style as Stats) ---
const barValueLabels = {
  id: "barValueLabels",
  afterDatasetsDraw(chart, args, opts) {
    const { ctx } = chart;
    const meta = chart.getDatasetMeta(0);
    const data = chart.data.datasets[0].data || [];

    ctx.save();
    ctx.font = (opts && opts.font) || "600 11px system-ui, -apple-system, Segoe UI, Roboto, Arial";
    ctx.fillStyle = (opts && opts.color) || "rgba(255,255,255,0.9)";

    meta.data.forEach((bar, i) => {
      const v = data[i];
      if (v == null || Number.isNaN(v)) return;

      const p = bar.tooltipPosition();
      const txt = `${Number(v).toFixed(1)}%`;

      const areaRight = chart.chartArea.right;
      const w = ctx.measureText(txt).width;
      let x = p.x + 8;
      if (x + w > areaRight - 2) x = areaRight - w - 2;

      ctx.fillText(txt, x, p.y + 4);
    });

    ctx.restore();
  }
};

(function () {
  const $ = (sel) => document.querySelector(sel);
  const fmtPct = (x) => (x == null || Number.isNaN(x)) ? "—" : (x * 100).toFixed(1) + "%";
  const fmtVia = (x) => (x == null || Number.isNaN(x)) ? "—" : Number(x).toFixed(2) + "%";

  const metaEl = $("#meta");
  const hintEl = $("#hint");
  const fTournament = $("#fTournament");
  const fMinMatches = $("#fMinMatches");
  const fAggSort = $("#fAggSort");
  const chartTitle = $("#chartTitle");
  const tableTitle = $("#tableTitle");
  const playoffCard = $("#playoffCard");
  const playoffBody = $("#playoffBody");
  const podiumTitle = $("#podiumTitle");
  const podiumTblBody = $("#podiumTbl tbody");
  const tblBody = $("#tbl tbody");

  let DATA = null;
  let BAR = null;

  function setMeta(text) {
    if (!metaEl) return;
    metaEl.textContent = text;
  }

  function byPlayerFromTournament(t) {
    // t.standings already contains match_win_pct.
    return t.standings.map((s) => {
      return {
        player: s.player,
        matches: s.matches,
        wins: s.record.w,
        losses: s.record.l,
        draws: s.record.d,
        match_win_pct: s.match_win_pct,
        via_avg: s.via_pct,
        tournaments: 1,
        best_rank: s.rank,
      };
    });
  }

  function getAggregatePlayers(minMatches, sortKey) {
    const rows = (DATA && DATA.by_player) ? DATA.by_player.slice() : [];

    const cleaned = rows.filter((r) => (r.matches || 0) >= minMatches);
    const key = (sortKey || "match_win_pct").trim();

    if (key === "best_rank") {
      return cleaned.sort((a, b) => {
        const ra = (a.best_rank == null) ? 1e9 : Number(a.best_rank);
        const rb = (b.best_rank == null) ? 1e9 : Number(b.best_rank);
        if (ra !== rb) return ra - rb; // lower is better
        const da = (a.match_win_pct == null) ? -1 : a.match_win_pct;
        const db = (b.match_win_pct == null) ? -1 : b.match_win_pct;
        if (db !== da) return db - da;
        return (a.player || "").localeCompare(b.player || "", "it", { sensitivity: "base" });
      });
    }

    // default: match win %
    return cleaned.sort((a, b) => {
      const da = (a.match_win_pct == null) ? -1 : a.match_win_pct;
      const db = (b.match_win_pct == null) ? -1 : b.match_win_pct;
      if (db !== da) return db - da;
      const ra = (a.best_rank == null) ? 1e9 : Number(a.best_rank);
      const rb = (b.best_rank == null) ? 1e9 : Number(b.best_rank);
      if (ra !== rb) return ra - rb;
      return (a.player || "").localeCompare(b.player || "", "it", { sensitivity: "base" });
    });
  }

  function renderTournamentOptions() {
    const list = (DATA && DATA.tournaments) ? DATA.tournaments.slice() : [];
    for (const t of list) {
      const opt = document.createElement("option");
      opt.value = String(t.id);
      const when = (t.played_at || "").slice(0, 16);
      opt.textContent = `${when} — ${t.name}`;
      fTournament.appendChild(opt);
    }
  }

  function getSelectedTournament() {
    const id = (fTournament.value || "").trim();
    if (!id) return null;
    const tid = Number(id);
    return (DATA.tournaments || []).find((t) => Number(t.id) === tid) || null;
  }

  function getRowsForView() {
    // Draft page: by default we want "min >= 3" and we also enforce it
    // to keep the aggregate view meaningful.
    const minMatches = Math.max(3, Number(fMinMatches.value || 3));
    const t = getSelectedTournament();

    if (t) {
      // tournament view: keep Companion-style order: wins desc, draws desc, via desc.
      const rows = byPlayerFromTournament(t)
        .filter((r) => (r.matches || 0) >= minMatches);
      return { mode: "tournament", tournament: t, rows };
    }

    const sortKey = fAggSort ? (fAggSort.value || "match_win_pct") : "match_win_pct";
    const rows = getAggregatePlayers(minMatches, sortKey);
    return { mode: "all", tournament: null, rows };
  }

  function renderHint(view) {
    const minMatches = Number(fMinMatches.value || 3);
    const countT = (DATA && DATA.counts) ? DATA.counts.tournaments : 0;
    const countP = (DATA && DATA.counts) ? DATA.counts.players : 0;

    if (view.mode === "tournament") {
      hintEl.textContent = `Torneo selezionato · min match: ${minMatches}`;
    } else {
      hintEl.textContent = `${countT} tornei · ${countP} player · min match: ${minMatches}`;
    }
  }

  function renderPlayoffs(view) {
    if (!playoffCard || !playoffBody) return;

    if (view.mode !== "tournament" || !view.tournament) {
      playoffCard.style.display = "none";
      playoffBody.innerHTML = "";
      return;
    }

    const po = view.tournament.playoffs;
    const matches = po && po.matches ? po.matches : [];
    if (!matches.length) {
      playoffCard.style.display = "none";
      playoffBody.innerHTML = "";
      return;
    }

    playoffCard.style.display = "block";
    const champ = po && po.champion ? String(po.champion) : "";

    const lines = matches.map((m) => {
      const stage = (m.stage || "").toUpperCase();
      const label = stage === "SF" ? "SF" : stage === "F" ? "Finale" : stage;
      const a = String(m.player_a || "");
      const b = String(m.player_b || "");
      const w = String(m.winner || "");
      return `<li><strong>${label}</strong>: ${a} vs ${b} → <strong>${w}</strong></li>`;
    });

    playoffBody.innerHTML =
      (champ ? `<div style="margin-bottom:8px">🏆 Campione: <strong>${champ}</strong></div>` : "") +
      `<ul style="margin:0 0 0 18px">${lines.join("")}</ul>`;
  }

  function renderChart(view) {
    const labels = view.rows.map((r) => r.player);
    const values = view.rows.map((r) => (r.match_win_pct == null ? null : r.match_win_pct * 100));

    // Draft color strategy:
    // - Use the same palette used across the app (PlayerColors.palette).
    // - If a player doesn't have a pre-assigned color (or collisions happen), assign an
    //   available (unused) color from the same colormap.
    // - If the palette is exhausted, wrap from the first color and alternate opacity so
    //   repeated colors remain distinguishable and visible.
    const getColor = (name) => (window.PlayerColors && window.PlayerColors.get)
      ? window.PlayerColors.get(name)
      : "#9CA3AF";
    const withAlpha = (color, alpha) => (window.PlayerColors && window.PlayerColors.withAlpha)
      ? window.PlayerColors.withAlpha(color, alpha)
      : color;
    const palette = (window.PlayerColors && Array.isArray(window.PlayerColors.palette) && window.PlayerColors.palette.length)
      ? window.PlayerColors.palette.slice()
      : ["#56B4E9", "#E69F00", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7", "#00BFC4"];

    function assignColors(names) {
      // IMPORTANT: keep the "static mapping" when present.
      // The static mapping in this app is provided via window.PLAYER_COLOR_OVERRIDES
      // (generated by the exporter). Those players must keep the exact same color
      // used in the Commander pages.
      const overrides = (window.PLAYER_COLOR_OVERRIDES && typeof window.PLAYER_COLOR_OVERRIDES === "object")
        ? window.PLAYER_COLOR_OVERRIDES
        : null;
      const norm = (s) => String(s || "").trim().toLowerCase();
      const hasStatic = (name) => {
        if (!overrides) return false;
        const k = norm(name);
        return k && Object.prototype.hasOwnProperty.call(overrides, k);
      };

      const used = new Set();
      const reuseCount = Object.create(null);
      const out = new Array(names.length);

      // 1) First pass: assign statically-mapped players EXACTLY as-is.
      for (let i = 0; i < names.length; i++) {
        const n = names[i];
        if (!hasStatic(n)) continue;
        const c = getColor(n);
        out[i] = { color: c || "#9CA3AF", variant: 0, isStatic: true };
        if (c) {
          used.add(c);
          reuseCount[c] = (reuseCount[c] || 0) + 1;
        }
      }

      // 2) Second pass: assign remaining players trying to avoid collisions.
      for (let i = 0; i < names.length; i++) {
        if (out[i]) continue;
        const n = names[i];
        const base = getColor(n);

        // Prefer their deterministic base color if it's free.
        if (base && base !== "#9CA3AF" && !used.has(base)) {
          used.add(base);
          reuseCount[base] = (reuseCount[base] || 0) + 1;
          out[i] = { color: base, variant: 0, isStatic: false };
          continue;
        }

        // Otherwise pick an unused color from the same palette.
        let alt = null;
        for (const c of palette) {
          if (!used.has(c)) { alt = c; break; }
        }
        if (alt) {
          used.add(alt);
          reuseCount[alt] = (reuseCount[alt] || 0) + 1;
          out[i] = { color: alt, variant: 0, isStatic: false };
          continue;
        }

        // Palette exhausted: cycle and alternate opacity.
        const cyc = palette[i % palette.length];
        const v = (reuseCount[cyc] || 0);
        reuseCount[cyc] = v + 1;
        out[i] = { color: cyc, variant: v, isStatic: false };
      }

      return out;
    }

    const assigned = assignColors(labels);
    const border = assigned.map((x) => x.color);
    const bg = assigned.map((x) => {
      // Keep static-mapped players fully readable; only alternate alpha for recycled colors.
      if (x.isStatic) return withAlpha(x.color, 0.78);
      return withAlpha(x.color, (x.variant % 2 === 0) ? 0.75 : 0.45);
    });

    chartTitle.textContent = (view.mode === "tournament")
      ? `Match Win % — ${view.tournament.name}`
      : "Match Win % per player";

    const ctx = $("#mwpBar").getContext("2d");

    // Dynamic height for mobile/readability (works with maintainAspectRatio:false)
    const wrap = $("#mwpBar")?.closest?.(".chart-wrap");
    if (wrap) {
      const n = Math.max(4, labels.length || 0);
      wrap.style.height = Math.min(520, 120 + n * 28) + "px";
    }

    if (BAR) {
      BAR.data.labels = labels;
      BAR.data.datasets[0].data = values;
      BAR.data.datasets[0].backgroundColor = bg;
      BAR.data.datasets[0].borderColor = border;
      BAR.update();
      return;
    }

    BAR = new Chart(ctx, {
      type: "bar",
      data: {
        labels,
        datasets: [{
          label: "Match Win %",
          data: values,
          backgroundColor: bg,
          borderColor: border,
          borderWidth: 1,
        }]
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: {
            beginAtZero: true,
            max: 100,
            ticks: {
              callback: (v) => v + "%"
            }
          },
          y: {
            ticks: {
              autoSkip: false,
            }
          }
        },
        plugins: {
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const v = ctx.raw;
                return v == null ? "—" : v.toFixed(1) + "%";
              }
            }
          },
          legend: { display: false }
        }
      }
    ,
      plugins: [barValueLabels]
    });
  }

  function _podiumCountsFromTournament(t) {
    const p = t && t.podium ? t.podium : null;
    if (!p) return [];
    const map = new Map();
    const add = (name, k) => {
      if (!name) return;
      const cur = map.get(name) || { player: name, gold: 0, silver: 0, bronze: 0, total: 0 };
      if (k === "gold") cur.gold += 1;
      if (k === "silver") cur.silver += 1;
      if (k === "bronze") cur.bronze += 1;
      cur.total = cur.gold + cur.silver + cur.bronze;
      map.set(name, cur);
    };
    add(p.gold, "gold");
    add(p.silver, "silver");
    add(p.bronze, "bronze");
    return Array.from(map.values());
  }

  function _podiumCountsAggregate(minMatches) {
    const rows = (DATA && DATA.by_player) ? DATA.by_player.slice() : [];
    return rows
      .filter((r) => (r.matches || 0) >= minMatches)
      .map((r) => {
        return {
          player: r.player,
          gold: Number(r.podium_gold || 0),
          silver: Number(r.podium_silver || 0),
          bronze: Number(r.podium_bronze || 0),
          total: Number(r.podium_total || 0),
        };
      })
      .filter((r) => r.total > 0)
      .sort((a, b) => {
        if (b.total !== a.total) return b.total - a.total;
        if (b.gold !== a.gold) return b.gold - a.gold;
        return (a.player || "").localeCompare(b.player || "", "it", { sensitivity: "base" });
      });
  }

  function renderPodium(view) {
    if (!podiumTitle || !podiumTblBody) return;

    const minMatches = Math.max(0, Number(fMinMatches.value || 0));
    const isTournament = view.mode === "tournament" && view.tournament;

    const rows = isTournament
      ? _podiumCountsFromTournament(view.tournament)
      : _podiumCountsAggregate(minMatches);

    podiumTitle.textContent = isTournament
      ? `Podi — ${view.tournament.name}`
      : "Podi (tutti i tornei)";

    // Table
    podiumTblBody.innerHTML = "";
    if (!rows.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 5;
      td.className = "muted";
      td.textContent = isTournament
        ? "Nessun podio calcolabile per questo torneo (mancano standings)."
        : "Nessun torneo con podio ancora disponibile.";
      tr.appendChild(td);
      podiumTblBody.appendChild(tr);
    } else {
      for (const r of rows) {
        const tr = document.createElement("tr");
        const cells = [
          { label: "Player", value: r.player },
          { label: "🥇", value: String(r.gold) },
          { label: "🥈", value: String(r.silver) },
          { label: "🥉", value: String(r.bronze) },
          { label: "Tot", value: String(r.total) },
        ];
        for (const c of cells) {
          const td = document.createElement("td");
          td.setAttribute("data-label", c.label);
          td.textContent = c.value;
          tr.appendChild(td);
        }
        podiumTblBody.appendChild(tr);
      }
    }
  }

  function renderTable(view) {
    const isTournament = view.mode === "tournament";
    const champion = (isTournament && view.tournament && view.tournament.playoffs && view.tournament.playoffs.champion)
      ? String(view.tournament.playoffs.champion)
      : "";
    tableTitle.textContent = isTournament ? "Standings" : "Aggregato";

    tblBody.innerHTML = "";

    view.rows.forEach((r, idx) => {
      const tr = document.createElement("tr");

      const rank = isTournament ? (idx + 1) : "";
      const rec = `${r.wins}-${r.losses}-${r.draws}`;
      const mwp = fmtPct(r.match_win_pct);
      const via = fmtVia(r.via_avg);
      const tournaments = isTournament ? "1" : String(r.tournaments || 0);
      const bestRank = isTournament ? String(idx + 1) : (r.best_rank == null ? "—" : String(r.best_rank));

      const cells = [
        { label: "#", value: rank },
        { label: "Player", value: (champion && String(r.player) === champion) ? `${r.player} 🏆` : r.player },
        { label: "Record", value: rec },
        { label: "Match", value: String(r.matches || 0) },
        { label: "Match Win %", value: mwp },
        { label: "VIA%", value: via },
        { label: "Tornei", value: tournaments },
        { label: "Best rank", value: bestRank },
      ];

      for (const c of cells) {
        const td = document.createElement("td");
        td.setAttribute("data-label", c.label);
        td.textContent = c.value;
        tr.appendChild(td);
      }

      tblBody.appendChild(tr);
    });

    if (!view.rows.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 8;
      td.className = "muted";
      td.textContent = "Nessun dato (prova a ridurre Min match, oppure importa un torneo).";
      tr.appendChild(td);
      tblBody.appendChild(tr);
    }
  }

  function render() {
    const view = getRowsForView();
    renderHint(view);
    renderPlayoffs(view);
    renderChart(view);
    renderPodium(view);
    renderTable(view);
  }

  async function load() {
    const res = await fetch("../data/draft.v1.json", { cache: "no-store" });
    if (!res.ok) throw new Error("Impossibile caricare draft.v1.json");
    DATA = await res.json();

    const gen = (DATA.generated_utc || "").replace("Z", "");
    setMeta(`Dati: ${DATA.counts.tournaments} tornei · gen: ${gen}`);

    renderTournamentOptions();

    fTournament.addEventListener("change", render);
    fMinMatches.addEventListener("input", render);
    if (fAggSort) fAggSort.addEventListener("change", render);

    render();
  }

  load().catch((e) => {
    console.error(e);
    setMeta("Errore caricamento dati");
    if (hintEl) hintEl.textContent = String(e && e.message ? e.message : e);
  });
})();
