from __future__ import annotations

import argparse
import json
from pathlib import Path

from core import session_from
from stats_data import build_stats_dataset


HTML_STATS = """<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Stats</title>
  <link rel="stylesheet" href="../assets/style.css" />
</head>
<body>
  <header class="topbar">
    <a href="../index.html">Home</a>
    <span>›</span>
    <strong>Stats</strong>
  </header>

  <main class="container">
    <h1>Stats</h1>
    <p class="muted">
      Nota: se apri questo file con <code>file://</code> il browser può bloccare il <code>fetch()</code>.
      Per vedere i dati, aprilo tramite un server (GitHub Pages o <code>python -m http.server</code>).
    </p>

    <div id="app" class="card">
      <div class="row gap">
        <input id="q" placeholder="Filtra (player/commander/bracket)..." />
        <select id="size"></select>
      </div>

      <div id="status" class="muted" style="margin-top: 8px;"></div>
      <div id="content" style="margin-top: 12px;"></div>
    </div>
  </main>

  <script src="../assets/stats.js"></script>
</body>
</html>
"""

HTML_HOME = """<!doctype html>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Home</title>
<link rel="stylesheet" href="assets/style.css" />
<div class="container">
  <h1>Commander Tracker</h1>
  <ul>
    <li><a href="stats/">Stats</a></li>
  </ul>
</div>
"""

JS_STATS = r"""(async function () {
  const elQ = document.getElementById('q');
  const elSize = document.getElementById('size');
  const elStatus = document.getElementById('status');
  const elContent = document.getElementById('content');

  function h(tag, attrs = {}, children = []) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === 'class') e.className = v;
      else if (k === 'text') e.textContent = v;
      else e.setAttribute(k, v);
    }
    for (const c of children) e.appendChild(c);
    return e;
  }

  function fmt(n) {
    if (n === null || n === undefined) return '';
    if (typeof n === 'number') {
      if (Number.isInteger(n)) return String(n);
      return (Math.round(n * 100) / 100).toString();
    }
    return String(n);
  }

  function table(rows, cols) {
    const t = h('table', { class: 'table' });
    const thead = h('thead');
    const trh = h('tr');
    cols.forEach(c => trh.appendChild(h('th', { text: c })));
    thead.appendChild(trh);
    t.appendChild(thead);

    const tb = h('tbody');
    rows.forEach(r => {
      const tr = h('tr');
      cols.forEach(c => tr.appendChild(h('td', { text: fmt(r[c]) })));
      tb.appendChild(tr);
    });
    t.appendChild(tb);
    return t;
  }

  async function load() {
    const url = new URL('../data/stats.v1.json', window.location.href);
    const r = await fetch(url.toString(), { cache: 'no-store' });
    if (!r.ok) throw new Error(`HTTP ${r.status} caricando ${url.pathname}`);
    return r.json();
  }

  let data;
  try {
    elStatus.textContent = 'Caricamento dati...';
    data = await load();
    elStatus.textContent = '';
  } catch (err) {
    elStatus.innerHTML = '';
    elStatus.appendChild(h('div', { class: 'error', text: 'Impossibile caricare stats.v1.json.' }));
    elStatus.appendChild(h('div', { class: 'muted', text: String(err) }));
    return;
  }

  const sizes = ['(tutti)'].concat((data.sizes || []).map(String));
  sizes.forEach(s => elSize.appendChild(h('option', { value: s, text: s })));

  function matchTerm(r, term) {
    if (!term) return true;
    const hay = [r.player, r.commander, r.bracket].filter(Boolean).join(' ').toLowerCase();
    return hay.includes(term);
  }

  function render() {
    const term = (elQ.value || '').trim().toLowerCase();
    const size = elSize.value;

    elContent.innerHTML = '';

    const players = (data.player_rows || [])
      .filter(r => matchTerm(r, term))
      .slice()
      .sort((a, b) => (b.games - a.games) || a.player.localeCompare(b.player));
    elContent.appendChild(h('h2', { text: 'Players' }));
    elContent.appendChild(table(players, ['player','games','wins','winrate','unique_commanders','top_commander','top_commander_games']));

    const pairs = (data.pair_rows || []).filter(r => matchTerm(r, term));
    elContent.appendChild(h('h2', { text: 'Player + Commander' }));
    elContent.appendChild(h('div', { class: 'muted', text: `Mostrati ${Math.min(200, pairs.length)} / ${pairs.length}` }));
    elContent.appendChild(table(pairs.slice(0, 200), ['player','commander','games','wins','winrate']));

    const brackets = (data.bracket_rows || []).slice().sort((a, b) => (b.games - a.games));
    elContent.appendChild(h('h2', { text: 'Bracket (overall)' }));
    elContent.appendChild(table(brackets, ['bracket','games','wins','winrate']));

    if (size !== '(tutti)') {
      const prow = (data.player_by_size_tables || {})[size] || [];
      const crow = (data.pair_by_size_tables || {})[size] || [];
      elContent.appendChild(h('h2', { text: `Per pod-size = ${size}` }));
      elContent.appendChild(h('h3', { text: 'Players' }));
      elContent.appendChild(table(prow, ['player','games','wins','winrate']));
      elContent.appendChild(h('h3', { text: 'Player + Commander' }));
      elContent.appendChild(table(crow.slice(0, 200), ['player','commander','games','wins','winrate']));
    }

    const triples = (data.triple_rows || []).filter(r => matchTerm(r, term));
    elContent.appendChild(h('h2', { text: `Triples (top ${data.limits?.top_triples ?? ''})` }));
    elContent.appendChild(table(triples, ['player','commander','bracket','games','wins','winrate','weighted_wr','bpi_label','avg_table_bracket']));
  }

  elQ.addEventListener('input', render);
  elSize.addEventListener('change', render);
  render();
})();"""

CSS = """:root{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Cantarell,Noto Sans,sans-serif;line-height:1.4}
body{margin:0}
.container{max-width:1100px;margin:0 auto;padding:16px}
.topbar{display:flex;gap:8px;align-items:center;padding:12px 16px;border-bottom:1px solid #eee}
.card{border:1px solid #eee;border-radius:12px;padding:12px}
.row{display:flex;align-items:center}
.gap{gap:8px}
input,select{padding:8px 10px;border:1px solid #ddd;border-radius:10px;min-width:220px}
.table{border-collapse:collapse;width:100%;margin:8px 0 16px}
.table th,.table td{border-bottom:1px solid #eee;text-align:left;padding:6px 8px;font-size:14px;vertical-align:top}
h1{margin:0 0 12px}
h2{margin:16px 0 8px}
h3{margin:12px 0 6px}
.muted{color:#666;font-size:14px}
.error{color:#b00020;font-weight:600}
code{background:#f6f6f6;padding:2px 4px;border-radius:6px}
"""


def write_output(out_dir: Path, payload: dict) -> None:
    docs = out_dir / "docs"
    (docs / "assets").mkdir(parents=True, exist_ok=True)
    (docs / "data").mkdir(parents=True, exist_ok=True)
    (docs / "stats").mkdir(parents=True, exist_ok=True)

    (docs / "index.html").write_text(HTML_HOME, encoding="utf-8")
    (docs / "stats" / "index.html").write_text(HTML_STATS, encoding="utf-8")
    (docs / "assets" / "stats.js").write_text(JS_STATS, encoding="utf-8")
    (docs / "assets" / "style.css").write_text(CSS, encoding="utf-8")
    (docs / "data" / "stats.v1.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Export Stats (JSON + static page) for GitHub Pages.")
    ap.add_argument("--db", required=True, help="Path to commander_tracker.sqlite")
    ap.add_argument("--out", default=".", help="Output directory (default: current dir)")
    ap.add_argument("--top-triples", type=int, default=50)
    ap.add_argument("--max-unique", type=int, default=200)
    args = ap.parse_args()

    out_dir = Path(args.out).resolve()

    with session_from(args.db) as session:
        payload = build_stats_dataset(session, top_triples=args.top_triples, max_unique=args.max_unique)

    write_output(out_dir, payload)
    print(f"OK: wrote {out_dir / 'docs'}")
    print("Tip: preview locally with:  python -m http.server -d docs 8000")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
