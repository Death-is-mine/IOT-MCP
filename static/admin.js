document.getElementById("save").onclick = () => {
  localStorage.setItem("cem_token", document.getElementById("token").value.trim());
};
document.getElementById("token").value = cemToken();

async function api(method, path, body) {
  const opt = {method, headers: {"Authorization": "Bearer " + cemToken(),
    "Content-Type": "application/json"}};
  if (body) opt.body = JSON.stringify(body);
  const r = await fetch(path, opt);
  if (!r.ok) throw new Error("HTTP " + r.status + " " + (await r.text()));
  return r.json();
}

document.getElementById("addnode").onclick = async () => {
  try {
    const d = await api("POST", "/api/v1/admin/nodes",
      {node_id: document.getElementById("nid").value.trim(),
       room_id: document.getElementById("room").value.trim()});
    document.getElementById("newtok").textContent =
      "ONE-TIME TOKEN for " + d.node.node_id + ": " + d.token;
    loadNodes();
  } catch (e) { document.getElementById("err").textContent = String(e); }
};

async function loadNodes() {
  const d = await cemGet("/api/v1/admin/nodes");
  const tb = document.querySelector("#nodes tbody");
  tb.innerHTML = "";
  for (const n of d.nodes) {
    const tr = document.createElement("tr");
    tr.innerHTML = "<td>" + esc(n.node_id) + "</td><td>" + esc(n.room_id) + "</td>" +
      "<td>" + esc(n.status) + "</td><td>" + esc(n.fw_version) + "</td><td></td>";
    const td = tr.lastChild;
    for (const [label, path, body] of [
      ["Rotate token", "/api/v1/admin/nodes/" + n.node_id + "/rotate", null],
      [n.status === "disabled" ? "Enable" : "Disable",
       "/api/v1/admin/nodes/" + n.node_id + "/status",
       {status: n.status === "disabled" ? "enabled" : "disabled"}]]) {
      const b = document.createElement("button");
      b.textContent = label;
      b.onclick = async () => {
        try {
          const r = await api("POST", path, body);
          if (r.token) document.getElementById("newtok").textContent = "NEW TOKEN: " + r.token;
          loadNodes();
        } catch (e) { document.getElementById("err").textContent = String(e); }
      };
      td.appendChild(b);
    }
    tb.appendChild(tr);
  }
}

document.getElementById("adduser").onclick = async () => {
  try {
    await api("POST", "/api/v1/admin/users",
      {email: document.getElementById("email").value.trim(),
       role: document.getElementById("role").value});
    loadUsers();
  } catch (e) { document.getElementById("err").textContent = String(e); }
};

async function loadUsers() {
  const d = await cemGet("/api/v1/admin/users");
  const tb = document.querySelector("#users tbody");
  tb.innerHTML = "";
  for (const u of d.users) {
    const tr = document.createElement("tr");
    tr.innerHTML = "<td>" + esc(u.email) + "</td><td>" + esc(u.role) + "</td>" +
      "<td>" + esc(u.active) + "</td><td></td>";
    if (u.active) {
      const b = document.createElement("button");
      b.textContent = "Deactivate";
      b.onclick = async () => {
        await api("POST", "/api/v1/admin/users/" + encodeURIComponent(u.email) + "/deactivate");
        loadUsers();
      };
      tr.lastChild.appendChild(b);
    }
    tb.appendChild(tr);
  }
}

document.getElementById("audit").onclick = async () => {
  const d = await cemGet("/api/v1/admin/audit?limit=200");
  const tb = document.querySelector("#auditlog tbody");
  tb.innerHTML = "";
  for (const a of d.entries) {
    const tr = document.createElement("tr");
    tr.innerHTML = "<td>" + esc(fmtTs(a.ts)) + "</td><td>" + esc(a.actor) + "</td>" +
      "<td>" + esc(a.action) + "</td><td>" + esc(a.target) + "</td><td>" + esc(a.detail) + "</td>";
    tb.appendChild(tr);
  }
};

loadNodes();
loadUsers();
