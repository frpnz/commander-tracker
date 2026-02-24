/* Draft page
 * Reads /data/draft.v1.json exported from the separate Draft DB.
 */

(function () {
  const $ = (sel) => document.querySelector(sel);
  const fmtPct = (x) => (x == null || Number.isNaN(x)) ? "—" : (x * 100).toFixed(1) + "%";
  const fmtVia = (x) => (x == null || Number.isNaN(x)) ? "—" : Number(x).toFixed(2) + "%";

  const metaEl = $("#meta");
  const hintEl = $("#hint");
  const fTournament = $("#fTournament");
  const fMinMatches = $("#fMinMatches");
  const chartTitle = $("#chartTitle");
  const tableTitle = $("#tableTitle");
  const playoffCard = $("#playoffCard");
  const playoffBody = $("#playoffBody");
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

  function getAggregatePlayers(minMatches) {
    const rows = (DATA && DATA.by_player) ? DATA.by_player.slice() : [];
    return rows
      .filter((r) => (r.matches || 0) >= minMatches)
      .sort((a, b) => {
        const da = (a.match_win_pct == null) ? -1 : a.match_win_pct;
        const db = (b.match_win_pct == null) ? -1 : b.match_win_pct;
        if (db !== da) return db - da;
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

    const rows = getAggregatePlayers(minMatches);
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

    const getColor = (name) => (window.PlayerColors && window.PlayerColors.get)
      ? window.PlayerColors.get(name)
      : "#9CA3AF";
    const withAlpha = (color, alpha) => (window.PlayerColors && window.PlayerColors.withAlpha)
      ? window.PlayerColors.withAlpha(color, alpha)
      : color;

    const bg = labels.map((n) => withAlpha(getColor(n), 0.75));
    const border = labels.map((n) => getColor(n));

    chartTitle.textContent = (view.mode === "tournament")
      ? `Match Win % — ${view.tournament.name}`
      : "Match Win % per player";

    const ctx = $("#mwpBar").getContext("2d");

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
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            beginAtZero: true,
            max: 100,
            ticks: {
              callback: (v) => v + "%"
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
    });
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

    render();
  }

  load().catch((e) => {
    console.error(e);
    setMeta("Errore caricamento dati");
    if (hintEl) hintEl.textContent = String(e && e.message ? e.message : e);
  });
})();
