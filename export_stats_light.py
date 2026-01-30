from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import SQLModel

from commander_tracker_light.db import Game, GameEntry, get_session, make_engine, migrate_schema
from commander_tracker_light.stats_data import build_stats_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description='Export /stats as JSON + minimal static page')
    parser.add_argument('--db', required=True, help='Path to commander_tracker.sqlite')
    parser.add_argument('--out', default='docs', help='Output directory (default: docs)')
    parser.add_argument('--top-triples', type=int, default=50)
    parser.add_argument('--max-unique', type=int, default=200)
    args = parser.parse_args()

    out_dir = Path(args.out)
    data_dir = out_dir / 'data'
    stats_dir = out_dir / 'stats'
    assets_dir = out_dir / 'assets'

    engine = make_engine(args.db)
    migrate_schema(engine)
    SQLModel.metadata.create_all(engine)

    with get_session(engine) as session:
        payload = build_stats_dataset(session, top_triples=args.top_triples, max_unique=args.max_unique)

    payload['generated_at'] = datetime.now(timezone.utc).isoformat()

    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / 'stats.v1.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    # Minimal static shell (GitHub Pages friendly)
    stats_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / 'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Stats</title><a href="stats/">Vai a Stats</a>', encoding='utf-8')

    (stats_dir / 'index.html').write_text(
        '<!doctype html><meta charset="utf-8"><title>Stats</title>'
        '<link rel="stylesheet" href="../assets/style.css">'
        '<h1>Stats</h1><div id="app"></div>'
        '<script src="../assets/stats.js"></script>',
        encoding='utf-8'
    )

    (assets_dir / 'style.css').write_text('body{font-family:system-ui,Arial,sans-serif;margin:16px}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:6px}th{background:#f6f6f6}input{padding:6px;margin:6px 0;width:320px;max-width:100%}', encoding='utf-8')

    (assets_dir / 'stats.js').write_text(
        """async function main(){
  const root=document.getElementById('app');
  const q=document.createElement('input');
  q.placeholder='Filtra (player/commander)...';
  root.appendChild(q);
  const wrap=document.createElement('div');
  root.appendChild(wrap);
  const data=await (await fetch('../data/stats.v1.json')).json();
  function table(rows, cols){
    const t=document.createElement('table');
    const thead=document.createElement('thead');
    const tr=document.createElement('tr');
    cols.forEach(c=>{const th=document.createElement('th');th.textContent=c;tr.appendChild(th)});
    thead.appendChild(tr);t.appendChild(thead);
    const tb=document.createElement('tbody');
    rows.forEach(r=>{const tr=document.createElement('tr');cols.forEach(c=>{const td=document.createElement('td');td.textContent=(r[c]??'');tr.appendChild(td)});tb.appendChild(tr)});
    t.appendChild(tb);return t;
  }
  function render(){
    const term=(q.value||'').toLowerCase();
    wrap.innerHTML='';
    const p=data.player_rows.filter(r=>!term||r.player.toLowerCase().includes(term));
    wrap.appendChild(document.createElement('h2')).textContent='Players';
    wrap.appendChild(table(p, ['player','games','wins','winrate','unique_commanders','top_commander','top_commander_games']));
    const pairs=data.pair_rows.filter(r=>!term||r.player.toLowerCase().includes(term)||r.commander.toLowerCase().includes(term));
    wrap.appendChild(document.createElement('h2')).textContent='Player + Commander';
    wrap.appendChild(table(pairs.slice(0,200), ['player','commander','games','wins','winrate']));
    wrap.appendChild(document.createElement('p')).textContent='(Mostrati max 200 pair per performance)';
  }
  q.addEventListener('input', render);
  render();
}
main();""",
        encoding='utf-8'
    )

    print(f"OK: wrote {(data_dir/'stats.v1.json').as_posix()} and {(stats_dir/'index.html').as_posix()}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
