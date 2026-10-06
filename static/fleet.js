document.getElementById("refresh").onclick = load;

async function load() {
  const err = document.getElementById("err");
  err.textContent = "";
  try {
    const data = await cemGet("/api/v1/fleet");
    const tb = document.querySelector("#fleet tbody");
    tb.innerHTML = "";
    for (const n of data.nodes) {
      const tr = document.createElement("tr");
      const flags = n.active_flags.map(f => esc(f.type + ":" + f.severity)).join("; ");
      tr.innerHTML =
        "<td>" + esc(n.node_id) + "</td><td>" + esc(n.room_id) + "</td>" +
        "<td>" + esc(n.status) + "</td><td>" + esc(fmtTs(n.last_seen_ts)) + "</td>" +
        "<td>" + esc(n.fw_version) + "</td><td>" + esc(n.mode) + "</td>" +
        "<td>" + esc(n.completeness_24h) + "</td>" +
        "<td>" + esc(n.clock_offset_ms == null ? "—" : n.clock_offset_ms + " ms") + "</td>" +
        "<td>" + esc(n.calib_age_days == null ? "missing" : n.calib_age_days + " d") + "</td>" +
        "<td>" + flags + "</td>";
      tb.appendChild(tr);
    }
  } catch (e) { err.textContent = String(e); }
}
load();
