/* Meta Profile page
   - Riquadro 1: scatter of players (MDI on X, MPI on Y)
   - Riquadro 2: heatmap table of commanders (MDI heat, MPI bar) for selected player

   Data source: ../data/stats.v1.json
   Fields:
     stats.meta_profile_by_player: [{player, games_total, games_used, mdi, mpi}]
     stats.meta_profile_by_player_commander: [{player, commander, games_total, games_used, mdi, mpi}]
*/

(function () {
  "use strict";

  const SAT_MIN = -1.0;
  const SAT_MAX = 1.0;
  const MPI_SAT_MAX = 1.0; // visual saturation for the bar in the table

  const elMeta = document.getElementById("meta");
  const elP1Info = document.getElementById("p1info");
  const elP2Info = document.getElementById("p2info");
  const elPlayer = document.getElementById("fPlayer");
  const elMinGames = document.getElementById("fMinGames");
  const tBody = document.querySelector("#tCmd tbody");

  let chart = null;
  let stats = null;

  function clamp(x, lo, hi) {
    return x < lo ? lo : x > hi ? hi : x;
  }

  function lerp(a, b, t) {
    return a + (b - a) * t;
  }

  function hexToRgb(hex) {
    const h = hex.replace("#", "");
    const n = parseInt(h, 16);
    return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
  }

  function rgbToCss({ r, g, b }, a = 1) {
    return `rgba(${Math.round(r)},${Math.round(g)},${Math.round(b)},${a})`;
  }

  // Diverging palette: blue (neg) -> gray (0) -> red (pos)
  const C_NEG = hexToRgb("#2563eb"); // blue-600
  const C_ZERO = hexToRgb("#9ca3af"); // gray-400
  const C_POS = hexToRgb("#ef4444"); // red-500

  function colorForMdi(mdi, alpha = 0.9) {
    if (mdi === null || mdi === undefined || Number.isNaN(mdi)) return "rgba(156,163,175,0.25)";
    const x = clamp(mdi, SAT_MIN, SAT_MAX);
    if (x === 0) return rgbToCss(C_ZERO, alpha);
    if (x < 0) {
      const t = (x - 0) / (SAT_MIN - 0); // 0..1
      return rgbToCss(
        {
          r: lerp(C_ZERO.r, C_NEG.r, t),
          g: lerp(C_ZERO.g, C_NEG.g, t),
          b: lerp(C_ZERO.b, C_NEG.b, t),
        },
        alpha
      );
    }
    const t = (x - 0) / (SAT_MAX - 0); // 0..1
    return rgbToCss(
      {
        r: lerp(C_ZERO.r, C_POS.r, t),
        g: lerp(C_ZERO.g, C_POS.g, t),
        b: lerp(C_ZERO.b, C_POS.b, t),
      },
      alpha
    );
  }

  function fmt2(x) {
    if (x === null || x === undefined || Number.isNaN(x)) return "—";
    return (Math.round(Number(x) * 100) / 100).toFixed(2);
  }

  function setMeta(stats) {
    const g = stats?.counts?.games ?? 0;
    const e = stats?.counts?.entries ?? 0;
    const ts = stats?.generated_utc ?? "";
    if (elMeta) elMeta.textContent = `${g} games · ${e} entries · ${ts}`;
  }

  function populatePlayers(players) {
    elPlayer.innerHTML = "";
    for (const p of players) {
      const opt = document.createElement("option");
      opt.value = p;
      opt.textContent = p;
      elPlayer.appendChild(opt);
    }
  }

  function renderPlayersScatter(rows) {
    const clean = (rows || [])
      .filter((r) => r && typeof r.player === "string")
      .map((r) => ({
        player: r.player,
        mdi: r.mdi,
        mpi: r.mpi,
        games_used: Number(r.games_used ?? 0),
        games_total: Number(r.games_total ?? 0),
      }))
      .filter((r) => r.games_total > 0)
      .sort((a, b) => (b.games_used || 0) - (a.games_used || 0));

    if (elP1Info) {
      elP1Info.textContent = `Scala colori MDI saturata su ±1.0 · ${clean.length} player`;
    }

    const ctx = document.getElementById("mdiMpiPlayers").getContext("2d");
    if (chart) {
      chart.destroy();
      chart = null;
    }

    // Auto range for MPI, but keep it sensible.
    const mpiMax = Math.max(0.25, ...clean.map((r) => Number(r.mpi ?? 0)));
    const yMax = Math.min(2.0, Math.max(0.75, Math.ceil(mpiMax * 10) / 10 + 0.1));

    chart = new Chart(ctx, {
      type: "scatter",
      data: {
        datasets: [
          {
            label: "Players",
            data: clean.map((r) => ({
              x: r.mdi === null || r.mdi === undefined ? null : Number(r.mdi),
              y: r.mpi === null || r.mpi === undefined ? null : Number(r.mpi),
              player: r.player,
              games_used: r.games_used,
              games_total: r.games_total,
              mdi: r.mdi,
              mpi: r.mpi,
            })),
            parsing: false,
            pointBackgroundColor: (ctx) => colorForMdi(ctx.raw?.mdi, 0.9),
            pointBorderColor: "rgba(255,255,255,0.25)",
            pointBorderWidth: 1,
            pointRadius: (ctx) => {
              const n = Number(ctx.raw?.games_used ?? 0);
              return clamp(4 + Math.sqrt(n) * 1.1, 4, 12);
            },
            pointHoverRadius: (ctx) => {
              const n = Number(ctx.raw?.games_used ?? 0);
              return clamp(6 + Math.sqrt(n) * 1.2, 6, 14);
            },
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const r = ctx.raw;
                return `${r.player} · MDI: ${fmt2(r.mdi)} · MPI: ${fmt2(r.mpi)} · games usate: ${r.games_used}/${r.games_total}`;
              },
            },
          },
        },
        scales: {
          x: {
            title: { display: true, text: "MDI (Δ bracket vs tavolo)" },
            suggestedMin: SAT_MIN,
            suggestedMax: SAT_MAX,
            grid: { display: true, drawTicks: false },
            ticks: { display: true },
          },
          y: {
            title: { display: true, text: "MPI (pressione)" },
            min: 0,
            suggestedMax: yMax,
            grid: { display: true, drawTicks: false },
            ticks: { display: true },
          },
        },
      },
    });
  }

  function renderCommanderTable(player, minGames) {
    const rows = (stats.meta_profile_by_player_commander || [])
      .filter((r) => r && r.player === player)
      .map((r) => ({
        commander: r.commander || "",
        games_used: Number(r.games_used ?? 0),
        games_total: Number(r.games_total ?? 0),
        mdi: r.mdi,
        mpi: r.mpi,
      }))
      .filter((r) => r.games_used >= minGames)
      .sort((a, b) => {
        if (b.games_used !== a.games_used) return b.games_used - a.games_used;
        const am = Number(a.mpi ?? 0);
        const bm = Number(b.mpi ?? 0);
        if (bm !== am) return bm - am;
        return a.commander.localeCompare(b.commander);
      });

    tBody.innerHTML = "";
    for (const r of rows) {
      const tr = document.createElement("tr");

      const tdC = document.createElement("td");
      tdC.textContent = r.commander;

      const tdG = document.createElement("td");
      tdG.className = "num";
      tdG.textContent = `${r.games_used}`;
      tdG.title = `Games totali con bracket: ${r.games_total}`;

      const tdMdi = document.createElement("td");
      tdMdi.className = "num heatcell";
      tdMdi.textContent = fmt2(r.mdi);
      tdMdi.style.background = colorForMdi(r.mdi, 0.85);
      tdMdi.style.color = "rgba(255,255,255,0.95)";
      tdMdi.title = `MDI: ${fmt2(r.mdi)} (saturazione ±1.0)`;

      const tdMpi = document.createElement("td");
      tdMpi.className = "num";
      const wrap = document.createElement("div");
      wrap.className = "mpicell";
      const bar = document.createElement("div");
      bar.className = "mpibar";
      const fill = document.createElement("span");
      const v = Number(r.mpi ?? 0);
      const pct = clamp(v / MPI_SAT_MAX, 0, 1) * 100;
      fill.style.width = `${pct.toFixed(1)}%`;
      bar.appendChild(fill);
      const lab = document.createElement("span");
      lab.className = "mpilabel";
      lab.textContent = fmt2(r.mpi);
      wrap.appendChild(bar);
      wrap.appendChild(lab);
      tdMpi.appendChild(wrap);
      tdMpi.title = `MPI: ${fmt2(r.mpi)} (barra saturata a ${MPI_SAT_MAX.toFixed(1)})`;

      tr.appendChild(tdC);
      tr.appendChild(tdG);
      tr.appendChild(tdMdi);
      tr.appendChild(tdMpi);
      tBody.appendChild(tr);
    }

    if (elP2Info) {
      elP2Info.textContent = `${rows.length} commander · min games ${minGames}`;
    }
  }

  function bind() {
    elPlayer.addEventListener("change", () => {
      renderCommanderTable(elPlayer.value, Number(elMinGames.value));
    });
    elMinGames.addEventListener("change", () => {
      renderCommanderTable(elPlayer.value, Number(elMinGames.value));
    });
  }

  async function load() {
    const res = await fetch("../data/stats.v1.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(`Failed to load stats.v1.json: ${res.status}`);
    stats = await res.json();
    setMeta(stats);

    const players = (stats.filters && stats.filters.players) || [];
    populatePlayers(players);
    if (players.length) elPlayer.value = players[0];

    renderPlayersScatter(stats.meta_profile_by_player || []);
    renderCommanderTable(elPlayer.value, Number(elMinGames.value));
  }

  bind();
  load().catch((err) => {
    // eslint-disable-next-line no-console
    console.error(err);
    if (elP1Info) elP1Info.textContent = "Errore nel caricamento dati";
  });
})();
