(async function () {
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
})();