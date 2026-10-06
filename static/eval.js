/* Results page: per-config curve (saved kWh vs false/room-week) + table
with CIs and labelled hours behind every figure (FR-065/066). */
let U = null;
document.getElementById("token").value = cemToken();
document.getElementById("runs").onclick = listRuns;
document.getElementById("run").onchange = show;

async function listRuns() {
  localStorage.setItem("cem_token", document.getElementById("token").value.trim());
  const d = await cemGet("/api/v1/eval/runs");
  const sel = document.getElementById("run");
  sel.innerHTML = "";
  for (const r of d.runs) sel.add(new Option(r.id + " " + r.status, r.id));
  if (d.runs.length) show();
}

async function show() {
  const err = document.getElementById("err");
  err.textContent = "";
  try {
    const id = document.getElementById("run").value;
    if (!id) return;
    const {run} = await cemGet("/api/v1/eval/runs/" + id);
    document.getElementById("meta").textContent =
      "code " + run.code_version + " · rules v" + run.rule_version +
      " · data " + run.data_hash.slice(0, 12) + " · weak timetable h " + run.weak_timetable_hours;
    const tb = document.querySelector("#tbl tbody");
    tb.innerHTML = "";
    const series = {};
    for (const [room, cfgs] of Object.entries(run.results)) {
      for (const [cfg, holds] of Object.entries(cfgs)) {
        const xs = [], ys = [];
        for (const [h, m] of Object.entries(holds)) {
          xs.push(m.false_per_room_week == null ? 0 : m.false_per_room_week);
          ys.push(m.energy_saved_kwh);
          const tr = document.createElement("tr");
          tr.innerHTML = "<td>" + esc(room) + "</td><td>" + esc(cfg) + "</td><td>" + esc(h) + "</td>" +
            "<td>" + esc(m.energy_saved_kwh) + "</td>" +
            "<td>" + esc(m.ci_energy_saved_kwh.ci_low) + "–" + esc(m.ci_energy_saved_kwh.ci_high) + "</td>" +
            "<td>" + esc(m.false_per_room_week) + "</td><td>" + esc(m.disruption_min) + "</td>" +
            "<td>" + esc(m.wasted_min) + "</td><td>" + esc(m.labelled_hours) + "</td>";
          tb.appendChild(tr);
        }
        series[cfg + "@" + room] = {x: xs, y: ys};
      }
    }
    if (U) U.remove();
    U = drawScatter(document.getElementById("ch_eval"), series);
  } catch (e) { err.textContent = String(e); }
}

/* Minimal SVG scatter: one polyline per config (independent x grids). */
function drawScatter(el, series) {
  const W = 1000, H = 320, P = 46;
  let x1 = 0, y1 = 0;
  for (const s of Object.values(series))
    for (let i = 0; i < s.x.length; i++) { x1 = Math.max(x1, s.x[i]); y1 = Math.max(y1, s.y[i]); }
  x1 = x1 || 1; y1 = y1 || 1;
  const X = v => P + (v / x1) * (W - 2 * P), Y = v => H - P - (v / y1) * (H - 2 * P);
  const colors = ["blue", "green", "red", "orange", "purple"];
  let s = `<svg width="${W}" height="${H}" role="img" aria-label="saved energy vs false cut-offs">`;
  s += `<line x1="${P}" y1="${H - P}" x2="${W - P}" y2="${H - P}" stroke="#888"/>`;
  s += `<line x1="${P}" y1="${P}" x2="${P}" y2="${H - P}" stroke="#888"/>`;
  s += `<text x="${W - P}" y="${H - 8}" text-anchor="end">false-vacant per room-week</text>`;
  s += `<text x="8" y="${P - 8}">saved kWh</text>`;
  let i = 0;
  for (const [name, d] of Object.entries(series)) {
    const c = colors[i++ % colors.length];
    const pts = d.x.map((x, k) => [X(x), Y(d.y[k])]).sort((a, b) => a[0] - b[0]);
    s += `<polyline fill="none" stroke="${c}" points="${pts.map(p => p.join(",")).join(" ")}"/>`;
    for (const [px, py] of pts) s += `<circle cx="${px}" cy="${py}" r="3" fill="${c}"/>`;
    s += `<text x="${W - P}" y="${P + 16 * i}" text-anchor="end" fill="${c}">${name}</text>`;
  }
  el.innerHTML = s + "</svg>";
  return {remove() { el.innerHTML = ""; }};
}
