/* Shared fetch helper. Token lives in localStorage (dev ergonomics);
production Firebase flow stores the ID token the same way. */
function cemToken() { return localStorage.getItem("cem_token") || ""; }

async function cemGet(path) {
  const r = await fetch(path, {headers: {"Authorization": "Bearer " + cemToken()}});
  if (!r.ok) throw new Error("HTTP " + r.status + " " + (await r.text()));
  return r.json();
}

async function cemPost(path, body) {
  const r = await fetch(path, {method: "POST",
    headers: {"Authorization": "Bearer " + cemToken(), "Content-Type": "application/json"},
    body: JSON.stringify(body)});
  if (!r.ok) throw new Error("HTTP " + r.status + " " + (await r.text()));
  return r.json();
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c =>
    ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
}

function fmtTs(ms) {
  if (ms == null) return "—";
  return new Date(ms).toLocaleString("en-IN", {timeZone: "Asia/Kolkata", hour12: false});
}
