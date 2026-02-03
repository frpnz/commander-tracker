/* Meta Profile page
   - Riquadro 1: Bubble Plot dei player (MDI su X, MPI su Y, Raggio = volume di gioco)
   - Riquadro 2: Heatmap table dei commander per il player selezionato

   Data source: ../data/stats.v1.json
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

  // Palette divergente: Blu (Underdog) -> Grigio (Neutro) -> Rosso (Pubstomper)
  const C_NEG = hexToRgb("#2563eb"); // blue-600
  const C_ZERO = hexToRgb("#9ca3af"); // gray-400
  const C_POS = hexToRgb("#ef4444"); // red-500

  function colorForMdi(mdi, alpha = 0.9) {
    if (mdi === null || mdi === undefined || Number.isNaN(mdi)) return "rgba(156,163,175,0.25)";
    const x = clamp(mdi, SAT_MIN, SAT_MAX);
    if (x === 0) return rgbToCss(C_ZERO, alpha);

    // Gradiente verso il Blu (negativo)
    if (x < 0) {
      const t = (x - 0) / (SAT_MIN - 0);
      return rgbToCss(
        {
          r: lerp(C_ZERO.r, C_NEG.r, t),
          g: lerp(C_ZERO.g, C_NEG.g, t),
          b: lerp(C_ZERO.b, C_NEG.b, t),
        },
        alpha
      );
    }

    // Gradiente verso il Rosso (positivo)
    const t = (x - 0) / (SAT_MAX - 0);
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

  // --- RENDER BUBBLE CHART ---
  function renderPlayersScatter(rows) {
    const clean = (rows || [])
      .filter((r) => r && typeof r.player === "string")
      .map((r) => ({
        player: r.player,
        mdi: Number(r.mdi),
        mpi: Number(r.mpi),
        games_used: Number(r.games_used ?? 0),
        games_total: Number(r.games_total ?? 0),
      }))
      .filter((r) => r.games_total > 0 && !Number.isNaN(r.mdi) && !Number.isNaN(r.mpi))
      .sort((a, b) => b.games_used - a.games_used);

    if (elP1Info) {
      elP1Info.textContent = `Scala colori MDI saturata su ±1.0 · ${clean.length} player`;
    }

    const ctx = document.getElementById("mdiMpiPlayers").getContext("2d");
    if (chart) {
      chart.destroy();
      chart = null;
    }

    // Calcolo range automatico per asse Y (MPI)
    const mpiMax = Math.max(0.25, ...clean.map((r) => r.mpi));
    const yMax = Math.min(2.0, Math.max(0.75, Math.ceil(mpiMax * 10) / 10 + 0.1));

    chart = new Chart(ctx, {
      type: "bubble", // Usa il tipo nativo Bubble
      data: {
        datasets: [
          {
            label: "Players",
            data: clean.map((r) => ({
              x: r.mdi,
              y: r.mpi,
              // Calcolo raggio (r): minimo 5px, cresce con la radice quadrata dei giochi, max 20px
              r: clamp(5 + Math.sqrt(r.games_used) * 1.5, 5, 20),
              // Salviamo l'intero oggetto per usarlo nel tooltip
              _raw: r
            })),
            backgroundColor: (context) => {
              // Usa la coordinata X (MDI) per il colore
              return colorForMdi(context.raw.x, 0.85);
            },
            borderColor: "rgba(255,255,255,0.3)",
            borderWidth: 1,
            hoverBackgroundColor: (context) => {
               return colorForMdi(context.raw.x, 1.0);
            },
            hoverBorderColor: "#fff",
            hoverBorderWidth: 2,
            hoverRadius: 2, // Espande leggermente al passaggio del mouse
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
              label: (context) => {
                const item = context.raw._raw;
                return `${item.player} · MDI: ${fmt2(item.mdi)} · MPI: ${fmt2(item.mpi)} · Games: ${item.games_used}`;
              },
            },
            backgroundColor: 'rgba(11, 16, 32, 0.95)',
            titleColor: '#aab3d3',
            bodyColor: '#e9ecf7',
            borderColor: 'rgba(255,255,255,0.1)',
            borderWidth: 1,
            padding: 10,
            displayColors: true,
            boxPadding: 4
          },
        },
        scales: {
          x: {
            title: { display: true, text: "MDI (Δ bracket vs tavolo)", color: '#aab3d3' },
            suggestedMin: SAT_MIN,
            suggestedMax: SAT_MAX,
            grid: {
              color: (ctx) => ctx.tick.value === 0 ? "rgba(255,255,255,0.3)" : "rgba(255,255,255,0.05)",
              lineWidth: (ctx) => ctx.tick.value === 0 ? 1 : 1
            },
            ticks: { color: '#aab3d3' },
          },
          y: {
            title: { display: true, text: "MPI (Pressione)", color: '#aab3d3' },
            min: 0,
            suggestedMax: yMax,
            grid: { color: "rgba(255,255,255,0.05)" },
            ticks: { color: '#aab3d3' },
          },
        },
      },
    });
  }

  // --- RENDER TABLE (COMMANDERS) ---
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
      // Colora il nome del commander leggermente per legarlo al visual
      tdC.style.fontWeight = "600";
      tdC.style.color = "#e9ecf7";

      const tdG = document.createElement("td");
      tdG.className = "num";
      tdG.textContent = `${r.games_used}`;
      tdG.title = `Games totali con bracket: ${r.games_total}`;

      const tdMdi = document.createElement("td");
      tdMdi.className = "num heatcell";
      tdMdi.textContent = fmt2(r.mdi);
      tdMdi.style.background = colorForMdi(r.mdi, 0.85);
      tdMdi.style.color = "#fff";
      tdMdi.style.textShadow = "0 1px 2px rgba(0,0,0,0.5)";
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

    // Carica il grafico con i dati aggregati per player
    renderPlayersScatter(stats.meta_profile_by_player || []);

    // Carica la tabella commander
    renderCommanderTable(elPlayer.value, Number(elMinGames.value));
  }

  bind();
  load().catch((err) => {
    // eslint-disable-next-line no-console
    console.error(err);
    if (elP1Info) elP1Info.textContent = "Errore nel caricamento dati";
  });
})();