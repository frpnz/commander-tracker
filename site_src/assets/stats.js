/* Stats UI (GitHub Pages) */
const elStatus = document.getElementById('status');
const elFilters = document.getElementById('filters');
const elContent = document.getElementById('content');

function h(tag, attrs = {}, kids = []) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === 'text') el.textContent = v;
    else if (k === 'html') el.innerHTML = v;
    else if (k === 'class') el.className = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, String(v));
  }
  for (const c of (Array.isArray(kids) ? kids : [kids])) {
    if (c == null) continue;
    el.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
  }
  return el;
}

function fmt(n, digits = 3) {
  if (n == null || Number.isNaN(n)) return 'n/a';
  if (typeof n !== 'number') return String(n);
  const abs = Math.abs(n);
  if (abs >= 1000) return n.toFixed(0);
  if (abs >= 10) return n.toFixed(1);
  return n.toFixed(digits).replace(/0+$/,'').replace(/\.$/,'');
}
function pct(x) { return (x == null) ? 'n/a' : (fmt(100 * x, 2) + '%'); }

function uniq(arr) {
  const s = new Set();
  for (const v of arr) if (v != null) s.add(v);
  return [...s].sort((a,b)=>String(a).localeCompare(String(b)));
}

function optionList(values, { allLabel='(tutti)', allValue='' } = {}) {
  return [
    h('option', { value: allValue, text: allLabel }),
    ...values.map(v => h('option', { value: String(v), text: String(v) }))
  ];
}

function normalizeTerm(s) { return (s || '').toString().trim().toLowerCase(); }
function matchTerm(row, term) {
  if (!term) return true;
  for (const v of Object.values(row || {})) {
    if (v == null) continue;
    if (String(v).toLowerCase().includes(term)) return true;
  }
  return false;
}

function filterRows(rows, f) {
  const term = normalizeTerm(f.q);
  const player = f.player || '';
  const commander = f.commander || '';
  const bracket = f.bracket || '';
  const minGames = Math.max(0, Number(f.minGames || 0));

  return (rows || []).filter(r => {
    if (!matchTerm(r, term)) return false;
    if (player && (r.player || '') !== player) return false;
    if (commander && (r.commander || '') !== commander) return false;
    if (bracket && String(r.bracket ?? '') !== bracket) return false;
    if ((r.games ?? 0) < minGames) return false;
    return true;
  });
}

function table(rows, columns, { format = {}, empty = 'Nessun dato', initialSort = null } = {}) {
  const el = h('div', { class: 'table-wrap' });
  if (!rows || rows.length === 0) {
    el.appendChild(h('div', { class: 'muted', text: empty }));
    return el;
  }

  let sort = initialSort || { key: columns[0], dir: 'desc' };

  function sortedRows() {
    const rs = rows.slice();
    const { key, dir } = sort;
    rs.sort((a, b) => {
      const av = a[key], bv = b[key];
      const an = typeof av === 'number' && !Number.isNaN(av);
      const bn = typeof bv === 'number' && !Number.isNaN(bv);
      let cmp = 0;
      if (an && bn) cmp = av - bv;
      else cmp = String(av ?? '').localeCompare(String(bv ?? ''));
      return dir === 'asc' ? cmp : -cmp;
    });
    return rs;
  }

  const thead = h('thead');
  const trh = h('tr');
  for (const col of columns) {
    const th = h('th', { class: 'sortable', text: col });
    th.addEventListener('click', () => {
      if (sort.key === col) sort.dir = (sort.dir === 'asc') ? 'desc' : 'asc';
      else sort = { key: col, dir: 'desc' };
      renderBody();
    });
    trh.appendChild(th);
  }
  thead.appendChild(trh);

  const tbody = h('tbody');
  const t = h('table', {}, [thead, tbody]);

  function renderBody() {
    tbody.innerHTML = '';
    for (const r of sortedRows()) {
      const tr = h('tr');
      for (const col of columns) {
        const v = r[col];
        const f = format[col];
        const txt = (typeof f === 'function') ? f(v, r) : (v == null ? '' : String(v));
        tr.appendChild(h('td', { text: txt }));
      }
      tbody.appendChild(tr);
    }
  }

  renderBody();
  el.appendChild(t);
  return el;
}

function section(title, bodyEl, subtitle = '') {
  const wrap = h('section', { class: 'section' });
  wrap.appendChild(h('h2', { text: title }));
  if (subtitle) wrap.appendChild(h('div', { class: 'muted', text: subtitle }));
  wrap.appendChild(bodyEl);
  return wrap;
}

function kpis(pairs) {
  return h('div', { class: 'kpi' }, pairs.map(([k, v]) => h('span', { class: 'badge', text: `${k}: ${v}` })));
}

function buildFilters(data) {
  const players = uniq((data.player_rows || []).map(r => r.player));
  const commanders = uniq((data.pair_rows || []).map(r => r.commander));
  const brackets = uniq((data.bracket_rows || []).map(r => r.bracket)).filter(x => x !== 'n/a');

  const sizes = (data.sizes || []).map(String);

  const elQ = h('input', { id:'q', placeholder:'Cerca (player, commander, ecc.)…' });
  const elPlayer = h('select', { id:'player' }, optionList(players, { allLabel:'(tutti i player)' }));
  const elCommander = h('select', { id:'commander' }, optionList(commanders, { allLabel:'(tutti i commander)' }));
  const elBracket = h('select', { id:'bracket' }, optionList(brackets, { allLabel:'(tutti i bracket)' }));
  const elSize = h('select', { id:'size' }, optionList(sizes, { allLabel:'(tutti i pod-size)' }));

  const elMinGames = h('input', { id:'minGames', type:'number', min:'0', step:'1', value:'0' });

  const fields = h('div', { class:'filters' }, [
    h('div', { class:'field' }, [h('label', { for:'q', text:'Ricerca' }), elQ]),
    h('div', { class:'field' }, [h('label', { for:'player', text:'Player' }), elPlayer]),
    h('div', { class:'field' }, [h('label', { for:'commander', text:'Commander' }), elCommander]),
    h('div', { class:'field' }, [h('label', { for:'bracket', text:'Bracket' }), elBracket]),
    h('div', { class:'field' }, [h('label', { for:'size', text:'Pod-size' }), elSize]),
    h('div', { class:'field' }, [h('label', { for:'minGames', text:'Min. games' }), elMinGames]),
  ]);

  const btnReset = h('button', { class:'button', type:'button', text:'Reset' });
  const btnCopyLink = h('button', { class:'button', type:'button', text:'Copia link filtri' });

  const actions = h('div', { class:'actions' }, [btnReset, btnCopyLink, h('span', { class:'muted', id:'counts' })]);

  const wrap = h('div', {}, [fields, actions]);

  function readFilters() {
    return {
      q: elQ.value,
      player: elPlayer.value,
      commander: elCommander.value,
      bracket: elBracket.value,
      size: elSize.value,
      minGames: elMinGames.value,
    };
  }

  function writeFilters(f) {
    elQ.value = f.q ?? '';
    elPlayer.value = f.player ?? '';
    elCommander.value = f.commander ?? '';
    elBracket.value = f.bracket ?? '';
    elSize.value = f.size ?? '';
    elMinGames.value = f.minGames ?? '0';
  }

  // load from querystring
  const qs = new URLSearchParams(location.search);
  writeFilters({
    q: qs.get('q') ?? '',
    player: qs.get('player') ?? '',
    commander: qs.get('commander') ?? '',
    bracket: qs.get('bracket') ?? '',
    size: qs.get('size') ?? '',
    minGames: qs.get('minGames') ?? '0',
  });

  btnReset.addEventListener('click', () => {
    writeFilters({ q:'', player:'', commander:'', bracket:'', size:'', minGames:'0' });
    wrap.dispatchEvent(new CustomEvent('filters-changed'));
  });

  btnCopyLink.addEventListener('click', async () => {
    const f = readFilters();
    const u = new URL(location.href);
    u.search = new URLSearchParams(Object.entries(f).filter(([_,v])=>String(v||'')!=='')).toString();
    try {
      await navigator.clipboard.writeText(u.toString());
      elStatus.textContent = 'Link copiato ✅';
      setTimeout(() => (elStatus.textContent=''), 1500);
    } catch {
      prompt('Copia questo link:', u.toString());
    }
  });

  for (const el of [elQ, elPlayer, elCommander, elBracket, elSize, elMinGames]) {
    el.addEventListener('input', () => wrap.dispatchEvent(new CustomEvent('filters-changed')));
    el.addEventListener('change', () => wrap.dispatchEvent(new CustomEvent('filters-changed')));
  }

  return { el: wrap, readFilters, writeFilters, elCounts: actions.querySelector('#counts') };
}

function renderAll(data, ui) {
  const f = ui.readFilters();
  elContent.innerHTML = '';

  // Persist filters to querystring (no reload)
  const u = new URL(location.href);
  u.search = new URLSearchParams(Object.entries(f).filter(([_,v])=>String(v||'')!=='')).toString();
  history.replaceState(null, '', u);

  // Overview
  const entryTotal = Object.values(data.bracket_entry_counts || {}).reduce((a,b)=>a+(b||0),0);
  const winnerTotal = Object.values(data.bracket_winner_counts || {}).reduce((a,b)=>a+(b||0),0);

  const overview = h('div', { class:'card' }, [
    h('div', { class:'muted', text:`Schema: ${data.schema || 'n/a'} · Pod-size disponibili: ${(data.sizes||[]).join(', ') || 'n/a'}`}),
    kpis([
      ['Entries', fmt(entryTotal, 0)],
      ['Winners', fmt(winnerTotal, 0)],
      ['Players', fmt((data.player_rows||[]).length, 0)],
      ['Pairs', fmt((data.pair_rows||[]).length, 0)],
      ['Triples', fmt((data.unique_triples_rows||[]).length, 0)],
    ])
  ]);
  elContent.appendChild(section('Overview', overview));

  // Bracket counts
  const bracketCountRows = uniq(Object.keys(data.bracket_entry_counts || {})).map(b => ({
    bracket: b,
    entries: (data.bracket_entry_counts||{})[b] ?? 0,
    winners: (data.bracket_winner_counts||{})[b] ?? 0,
    winner_rate: ((data.bracket_winner_counts||{})[b] ?? 0) / Math.max(1, (data.bracket_entry_counts||{})[b] ?? 0),
  }));
  elContent.appendChild(section(
    'Bracket – conteggi',
    table(bracketCountRows, ['bracket','entries','winners','winner_rate'], {
      format: { winner_rate: (v)=>pct(v) },
      initialSort: { key:'entries', dir:'desc' }
    }),
    'Conteggi di entries e winners per bracket (basati su GameEntry).'
  ));

  // Players
  const players = filterRows(data.player_rows || [], f)
    .slice()
    .sort((a,b)=>(b.games-a.games) || String(a.player).localeCompare(String(b.player)));
  elContent.appendChild(section(
    'Players',
    table(players, ['player','games','wins','winrate','unique_commanders','top_commander','top_commander_games'], {
      format: { winrate: (v)=>pct(v) },
      initialSort: { key:'games', dir:'desc' },
      empty: 'Nessun player corrispondente ai filtri.'
    }),
    `Mostrati ${players.length} / ${(data.player_rows||[]).length}`
  ));

  // Pairs
  const pairsAll = data.pair_rows || [];
  const pairs = filterRows(pairsAll, f);
  const pairsShown = pairs.slice(0, 300);
  elContent.appendChild(section(
    'Player + Commander',
    h('div', {}, [
      h('div', { class:'muted', text:`Mostrati ${pairsShown.length} / ${pairs.length} (cap 300 per performance)` }),
      table(pairsShown, ['player','commander','games','wins','winrate'], {
        format: { winrate: (v)=>pct(v) },
        initialSort: { key:'games', dir:'desc' }
      })
    ])
  ));

  // Bracket rows (overall winrate by bracket)
  const brackets = (data.bracket_rows || []).slice()
    .sort((a,b)=>(b.games-a.games));
  elContent.appendChild(section(
    'Bracket – winrate (overall)',
    table(brackets, ['bracket','games','wins','winrate'], { format: { winrate: (v)=>pct(v) } })
  ));

  // Per pod-size tables (when selected)
  if (f.size) {
    const prow = (data.player_by_size_tables || {})[f.size] || [];
    const crow = (data.pair_by_size_tables || {})[f.size] || [];
    elContent.appendChild(h('hr', { class:'sep' }));
    elContent.appendChild(section(
      `Per pod-size = ${f.size} – Players`,
      table(filterRows(prow, f), ['player','games','wins','winrate'], { format: { winrate: (v)=>pct(v) } })
    ));
    elContent.appendChild(section(
      `Per pod-size = ${f.size} – Player + Commander`,
      table(filterRows(crow, f).slice(0, 300), ['player','commander','games','wins','winrate'], { format: { winrate: (v)=>pct(v) } })
    ));
  }

  // Triples (top)
  const triples = filterRows(data.triple_rows || [], f);
  elContent.appendChild(section(
    `Triples (top ${data.limits?.top_triples ?? ''})`,
    table(triples, ['player','commander','bracket','games','wins','winrate','weighted_wr','bpi_label','avg_table_bracket'], {
      format: { winrate: (v)=>pct(v), weighted_wr: (v)=>pct(v), avg_table_bracket: (v)=>fmt(v,2) },
      initialSort: { key:'games', dir:'desc' }
    })
  ));

  // Unique triples (full-ish)
  const uniqTriplesAll = data.unique_triples_rows || [];
  const uniqTriples = filterRows(uniqTriplesAll, f).slice(0, 400);
  elContent.appendChild(section(
    `Triples (unique, top ${data.limits?.max_unique ?? ''})`,
    h('div', {}, [
      h('div', { class:'muted', text:`Mostrati ${uniqTriples.length} / ${filterRows(uniqTriplesAll, f).length} (cap 400)` }),
      table(uniqTriples, ['player','commander','bracket','games','wins','winrate','weighted_wr','bpi_label','avg_table_bracket'], {
        format: { winrate: (v)=>pct(v), weighted_wr: (v)=>pct(v), avg_table_bracket: (v)=>fmt(v,2) },
        initialSort: { key:'games', dir:'desc' }
      })
    ])
  ));

  // counts line
  if (ui.elCounts) {
    ui.elCounts.textContent = `Filtri attivi: ${Object.entries(f).filter(([_,v])=>String(v||'')!=='').length}`;
  }
}

async function main() {
  try {
    elStatus.textContent = 'Carico stats…';
    const res = await fetch('../data/stats.v1.json', { cache: 'no-store' });
    const data = await res.json();

    const ui = buildFilters(data);
    elFilters.innerHTML = '';
    elFilters.appendChild(ui.el);

    const rerender = () => renderAll(data, ui);
    ui.el.addEventListener('filters-changed', rerender);

    elStatus.textContent = 'OK';
    setTimeout(() => (elStatus.textContent=''), 1000);

    rerender();
  } catch (e) {
    console.error(e);
    elStatus.textContent = 'Errore nel caricamento.';
    elContent.innerHTML = '<div class="card">Impossibile caricare <code>stats.v1.json</code>.</div>';
  }
}

main();
