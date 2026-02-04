const tbody = document.querySelector("#entries tbody");
const out = document.querySelector("#out");

function addRow(player="", commander="", bracket=""){
  const tr = document.createElement("tr");
  tr.innerHTML = `
    <td><input value="${player}"></td>
    <td><input value="${commander}"></td>
    <td><input type="number" min="1" max="5" value="${bracket}"></td>`;
  tbody.appendChild(tr);
}

for(let i=0;i<4;i++) addRow();
document.querySelector("#add").onclick = () => addRow();

function buildPayload(){
  const played = document.querySelector("#played_at").value;
  const winner = document.querySelector("#winner").value.trim();
  const notes = document.querySelector("#notes").value.trim();
  const entries = [...tbody.querySelectorAll("tr")].map(tr => {
    const i = tr.querySelectorAll("input");
    return {
      player: i[0].value.trim(),
      commander: i[1].value.trim(),
      bracket: i[2].value ? parseInt(i[2].value,10) : null
    };
  }).filter(e => e.player && e.commander);

  return {
    version: "game.v1",
    played_at: played.replace("T"," ") + ":00",
    winner_player: winner || null,
    notes: notes || null,
    entries
  };
}

document.querySelector("#download").onclick = () => {
  const data = buildPayload();
  const blob = new Blob([JSON.stringify(data,null,2)], {type:"application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "game.json";
  a.click();
};

document.querySelector("#copy").onclick = async () => {
  const data = JSON.stringify(buildPayload(), null, 2);
  await navigator.clipboard.writeText(data);
  out.textContent = data;
};
