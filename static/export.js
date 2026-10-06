document.getElementById("go").onclick = async () => {
  const err = document.getElementById("err"), out = document.getElementById("out");
  err.textContent = "";
  try {
    const rooms = document.getElementById("rooms").value.split(",").map(s => s.trim()).filter(Boolean);
    const d = await cemPost("/api/v1/export", {
      rooms,
      from: new Date(document.getElementById("from").value).getTime(),
      to: new Date(document.getElementById("to").value).getTime(),
    });
    const r = await fetch("/api/v1/export/" + d.export_id,
      {headers: {"Authorization": "Bearer " + cemToken()}});
    if (!r.ok) throw new Error("HTTP " + r.status + " " + (await r.text()));
    out.innerHTML = "";
    const a = document.createElement("a");
    a.href = URL.createObjectURL(await r.blob());
    a.download = "cem-export-" + d.export_id + ".zip";
    a.textContent = "Download cem-export-" + d.export_id + ".zip (" + d.manifest.row_counts.rows + " rows)";
    out.appendChild(a);
  } catch (e) { err.textContent = String(e); }
};
