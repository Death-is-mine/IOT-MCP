/* Node page: uPlot charts (vendored) + flag bands + would_cut markers.
X axis is minutes since range start (tz-free); tables show Asia/Kolkata. */
let HOURS = 24, U1 = null, U2 = null;

document.getElementById("token").value = cemToken();
document.querySelectorAll("#ranges button").forEach(b => {
  b.onclick = () => { HOURS = +b.dataset.h; load(); };
});
document.getElementById("refresh").onclick = load;

async function nodeList() {
  const sel = document.getElementById("node");
  if (sel.options.length) return sel.value;
  const d = await cemGet("/api/v1/fleet");
  for (const n of d.nodes) sel.add(new Option(n.node_id + " (" + n.room_id + ")", n.node_id));
  return sel.value;
}

function band(u, flags, el) {
  el.querySelectorAll(".band").forEach(e => e.remove());
  const plot = el.querySelector(".uplot");
  if (!plot) return;
  for (const f of flags) {
    const x0 = u.valToPos(f.ts_start, "x", true), x1 = u.valToPos(f.ts_end, "x", true);
    const d = document.createElement("div");
    d.className = "band " + (f.severity === "error" ? "err" : "warn");
    d.style.left = Math.max(0, x0) + "px";
    d.style.width = Math.max(2, x1 - x0) + "px";
    d.title = f.type + " " + f.severity;
    plot.appendChild(d);
  }
}

async function load() {
  const err = document.getElementById("err");
  err.textContent = "";
  try {
    localStorage.setItem("cem_token", document.getElementById("token").value.trim());
    const node = await nodeList();
    const to = Date.now(), from = to - HOURS * 3600_000;
    const min = ts => (ts - from) / 60000;
    const d = await cemGet(`/api/v1/nodes/${node}/readings?from=${from}&to=${to}&max_points=2000`);
    const S = d.series;
    const X = S.power_w.map(p => min(p[0]));
    const col = a => a.map(p => p[1]);
    const flags = d.flags.map(f => ({...f, ts_start: min(f.ts_start), ts_end: min(f.ts_end)}));
    const mk = (el, series, data, h) => new uPlot(
      {width: 1000, height: h, series: [{label: "min"}, ...series], axes: [{label: "min since start"}, {}]},
      [X, ...data], document.getElementById(el));
    if (U1) U1.destroy();
    U1 = mk("ch_power", [{label: "power_w", stroke: "blue"}, {label: "current_a", stroke: "green"}],
            [col(S.power_w), col(S.current_a)], 260);
    if (U2) U2.destroy();
    U2 = mk("ch_pres", [{label: "pir", stroke: "red"}, {label: "load", stroke: "orange"},
                        {label: "mmwave", stroke: "purple"}],
            [col(S.pir), col(S.load_state), col(S.mmwave)], 180);
    band(U1, flags, document.getElementById("ch_power"));
    band(U2, flags, document.getElementById("ch_pres"));
    const tb = document.querySelector("#flags tbody");
    tb.innerHTML = "";
    for (const f of d.flags) {
      const tr = document.createElement("tr");
      tr.innerHTML = "<td>" + esc(fmtTs(f.ts_start)) + "</td><td>" + esc(fmtTs(f.ts_end)) +
        "</td><td>" + esc(f.type) + "</td><td>" + esc(f.severity) + "</td>";
      tb.appendChild(tr);
    }
    for (const e of d.events.filter(x => x.type === "would_cut")) {
      const tr = document.createElement("tr");
      tr.innerHTML = "<td>" + esc(fmtTs(e.ts)) + "</td><td>—</td><td>would_cut</td><td>marker</td>";
      tb.appendChild(tr);
    }
  } catch (e) { err.textContent = String(e); }
}
load();
