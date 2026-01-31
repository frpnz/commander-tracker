/* Meta Wins page
   - Riquadro 1: diverging horizontal bar chart of WBD by player
   - Riquadro 2: heatmap table of WBD by commander for selected player

   Data source: ../data/stats.v1.json
   Fields:
     stats.meta_wins_by_player: [{player, wins_total, wins_used, wbd}]
     stats.meta_wins_by_player_commander: [{player, commander, wins_total, wins_used, wbd}]
*/

(function () {
  "use strict";

  const SAT_MIN = -1.0;
  const SAT_MAX = 1.0;

  const elMeta = document.getElementById("meta");
  const elP1Info = document.getElementById("p1info");
  const elP2Info = document.getElementById("p2info");
  const elPlayer = document.getElementById("fPlayer");
  const elMinWins = document.getElementById("fMinWins");
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

  function colorForWbd(wbd, alpha = 0.9) {
    if (wbd === null || wbd === undefined || Number.isNaN(wbd)) return "rgba(156,163,175,0.25)";
    const x = clamp(wbd, SAT_MIN, SAT_MAX);
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

  function fmt1(x) {
    if (x === null || x === undefined || Number.isNaN(x)) return "—";
    return (Math.round(x * 100) / 100).toFixed(2);
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

  function renderPlayersChart(rows) {
    const clean = rows
      .filter((r) => r && typeof r.player === "string")
      .map((r) => ({
        player: r.player,
        wbd: r.wbd,
        wins_used: Number(r.wins_used ?? 0),
        wins_total: Number(r.wins_total ?? 0),
      }))
      .sort((a, b) => {
        // Show most extreme first (abs), tie-break by wins_used
        const aa = Math.abs(a.wbd ?? 0);
        const bb = Math.abs(b.wbd ?? 0);
        if (bb !== aa) return bb - aa;
        return (b.wins_used ?? 0) - (a.wins_used ?? 0);
      });

    const labels = clean.map((r) => r.player);
    const values = clean.map((r) => (r.wbd === null || r.wbd === undefined ? 0 : Number(r.wbd)));
    const colors = clean.map((r) => colorForWbd(r.wbd, 0.9));

    if (elP1Info) {
      elP1Info.textContent = `Scala colori saturata su ±1.0 · ${labels.length} player`;
    }

    const ctx = document.getElementById("wbdPlayers").getContext("2d");
    if (chart) {
      chart.destroy();
      chart = null;
    }

    chart = new Chart(ctx, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "WBD",
            data: values,
            backgroundColor: colors,
            borderWidth: 0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: "y",
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const r = clean[ctx.dataIndex];
                return `WBD: ${fmt1(r.wbd)} · wins usate: ${r.wins_used} · wins totali: ${r.wins_total}`;
              },
            },
          },
        },
        scales: {
          x: {
            suggestedMin: SAT_MIN,
            suggestedMax: SAT_MAX,
            grid: { display: true, drawTicks: false },
            ticks: { display: true },
          },
          y: {
            grid: { display: false, drawTicks: false },
            ticks: { display: true },
          },
        },
      },
    });
  }

  function renderCommanderTable(player, minWins) {
    const rows = (stats.meta_wins_by_player_commander || [])
      .filter((r) => r && r.player === player)
      .map((r) => ({
        commander: r.commander || "",
        wins_used: Number(r.wins_used ?? 0),
        wins_total: Number(r.wins_total ?? 0),
        wbd: r.wbd,
      }))
      .filter((r) => r.wins_used >= minWins)
      .sort((a, b) => {
        // Default: wins_used desc, then abs(wbd) desc
        if (b.wins_used !== a.wins_used) return b.wins_used - a.wins_used;
        const aa = Math.abs(a.wbd ?? 0);
        const bb = Math.abs(b.wbd ?? 0);
        if (bb !== aa) return bb - aa;
        return a.commander.localeCompare(b.commander);
      });

    tBody.innerHTML = "";
    for (const r of rows) {
      const tr = document.createElement("tr");
      const tdC = document.createElement("td");
      tdC.textContent = r.commander;
      const tdW = document.createElement("td");
      tdW.className = "num";
      tdW.textContent = `${r.wins_used}`;
      tdW.title = `Wins totali con bracket: ${r.wins_total}`;
      const tdD = document.createElement("td");
      tdD.className = "num heatcell";
      tdD.textContent = fmt1(r.wbd);
      tdD.style.background = colorForWbd(r.wbd, 0.85);
      tdD.style.color = "rgba(255,255,255,0.95)";
      tdD.title = `WBD: ${fmt1(r.wbd)} (saturazione ±1.0)`;
      tr.appendChild(tdC);
      tr.appendChild(tdW);
      tr.appendChild(tdD);
      tBody.appendChild(tr);
    }

    if (elP2Info) {
      elP2Info.textContent = `${rows.length} commander · min wins ${minWins}`;
    }
  }

  function bind() {
    elPlayer.addEventListener("change", () => {
      renderCommanderTable(elPlayer.value, Number(elMinWins.value));
    });
    elMinWins.addEventListener("change", () => {
      renderCommanderTable(elPlayer.value, Number(elMinWins.value));
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

    const rows = stats.meta_wins_by_player || [];
    renderPlayersChart(rows);
    renderCommanderTable(elPlayer.value, Number(elMinWins.value));
  }

  bind();
  load().catch((err) => {
    console.error(err);
    if (elP1Info) elP1Info.textContent = "Errore nel caricamento dei dati (vedi console).";
  });
})();
