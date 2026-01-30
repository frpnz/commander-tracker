async function main(){
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
main();