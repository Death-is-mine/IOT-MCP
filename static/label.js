const dtLocal = v => new Date(v).getTime();
const pad = n => String(n).padStart(2, "0");
function toInput(ms) {
  const d = new Date(ms);
  return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) +
    "T" + pad(d.getHours()) + ":" + pad(d.getMinutes());
}
document.getElementById("start").value = toInput(Date.now() - 3600_000);
document.getElementById("end").value = toInput(Date.now());

document.getElementById("add").onclick = async () => {
  try {
    await cemPost("/api/v1/labels", {
      room_id: document.getElementById("room").value.trim(),
      ts_start: dtLocal(document.getElementById("start").value),
      ts_end: dtLocal(document.getElementById("end").value),
      state: document.getElementById("state").value,
      source: document.getElementById("source").value,
      labeller: document.getElementById("labeller").value.trim(),
      note: document.getElementById("note").value,
    });
    load();
  } catch (e) { document.getElementById("err").textContent = String(e); }
};
document.getElementById("reload").onclick = load;

async function load() {
  const err = document.getElementById("err");
  err.textContent = "";
  try {
    const lbs = await cemGet("/api/v1/labels");
    const tb = document.querySelector("#labels tbody");
    tb.innerHTML = "";
    for (const l of lbs.labels) {
      const tr = document.createElement("tr");
      tr.innerHTML = "<td>" + esc(l.room_id) + "</td><td>" + esc(fmtTs(l.ts_start)) + "</td>" +
        "<td>" + esc(fmtTs(l.ts_end)) + "</td><td>" + esc(l.state) + "</td>" +
        "<td>" + esc(l.source) + "</td><td>" + esc(l.labeller) + "</td>" +
        "<td>" + esc(l.note) + "</td><td></td>";
      const b = document.createElement("button");
      b.textContent = "Supersede";
      b.onclick = async () => {
        const state = prompt("Corrected state (occupied/vacant/unsure):", l.state);
        if (!state) return;
        await cemPost("/api/v1/labels/" + l.id + "/supersede", {state});
        load();
      };
      tr.lastChild.appendChild(b);
      tb.appendChild(tr);
    }
    const cf = await cemGet("/api/v1/labels/conflicts");
    const tc = document.querySelector("#conflicts tbody");
    tc.innerHTML = "";
    for (const c of cf.conflicts) {
      const tr = document.createElement("tr");
      tr.innerHTML = "<td>" + esc(c.room_id) + "</td><td>" + esc(fmtTs(c.overlap_start)) + "</td>" +
        "<td>" + esc(fmtTs(c.overlap_end)) + "</td><td>" + esc(c.a_id) + "</td><td>" + esc(c.b_id) + "</td>";
      tc.appendChild(tr);
    }
    const cv = await cemGet("/api/v1/labels/coverage");
    const tg = document.querySelector("#coverage tbody");
    tg.innerHTML = "";
    for (const c of cv.coverage) {
      const tr = document.createElement("tr");
      tr.innerHTML = "<td>" + esc(c.room_id) + "</td><td>" + esc(c.state) + "</td><td>" + esc(c.hours) + "</td>";
      tg.appendChild(tr);
    }
  } catch (e) { err.textContent = String(e); }
}
load();
