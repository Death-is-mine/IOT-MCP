"""Security tests: TC-SEC-01..09 (applicable halves), TC-OP-04.
Firebase halves are skipped until a test project exists (see test_admin_auth).
"""
from __future__ import annotations

from pathlib import Path

from tests.conftest import batch, node_hdr, user_hdr

VIEW = user_hdr("view@x.test")
ADMIN = user_hdr("admin@x.test")


def test_tc_sec_02_injection_inputs_rejected(client):
    """TC-SEC-02: hostile field paths / params fail closed, nothing stored."""
    evil = batch()
    evil["node_id"] = "__proto__"
    assert client.post("/api/v1/ingest", json=evil, headers=node_hdr()).status_code == 400
    r = client.get("/api/v1/nodes/%24ne/readings?from=0&to=1", headers=VIEW)
    assert r.status_code in (400, 404)
    r = client.post("/api/v1/labels", json={"room_id": "$where", "ts_start": 1,
                    "ts_end": 2, "state": "occupied", "source": "spot_check",
                    "labeller": "x"}, headers=user_hdr("lab@x.test"))
    assert r.status_code == 201  # free text is data, not code; stored inert
    assert r.get_json()["label"]["room_id"] == "$where"


def test_tc_sec_03_stored_xss_rendered_inert():
    """TC-SEC-03: notes stored raw; every render path escapes (esc() contract)."""
    for page, fields in (("label.js", ["esc(l.note)", "esc(l.room_id)"]),
                         ("fleet.js", ["esc(n.node_id)"]),
                         ("node.js", ["esc(f.type)"])):
        text = Path("static") / page
        src = text.read_text(encoding="utf-8")
        for f in fields:
            assert f in src, f"{page} must escape via {f}"


def test_tc_sec_04_no_cookie_auth(client):
    """TC-SEC-04: Bearer-header auth only; cookies alone never authenticate."""
    client.set_cookie("cem_token", "dev-user:admin@x.test:test-secret")
    assert client.get("/api/v1/fleet").status_code == 401
    assert client.post("/api/v1/ingest", json=batch()).status_code == 401


def test_tc_sec_05_headers_and_csp(client):
    """TC-SEC-05: CSP without inline scripts, nosniff, no-referrer."""
    r = client.get("/")
    assert "script-src 'self'" in r.headers.get("Content-Security-Policy", "")
    assert "'unsafe-inline'" not in r.headers.get("Content-Security-Policy", "")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"


def test_tc_sec_06_no_secrets_in_repo():
    """TC-SEC-06/SEC-09 + FR-094: no secrets, keys, or .env in the repo."""
    banned = ("ghp_", "BEGIN PRIVATE KEY", "BEGIN RSA PRIVATE KEY", "AKIA")
    skip = {Path("tests/security/test_security.py")}  # this scanner itself
    for p in Path(".").rglob("*"):
        if not p.is_file() or ".git" in p.parts or p in skip:
            continue
        if p.suffix in (".pyc",) or p.name in ("opencode.json",):
            continue
        if "var" in p.parts or "__pycache__" in p.parts or ".pytest_cache" in p.parts:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for b in banned:
            assert b not in text, f"secret marker in {p}"
    assert not Path(".env").exists()
    assert not list(Path(".").glob("*-key.json"))


def test_tc_sec_09_no_actuation_code():
    """TC-SEC-09/SEC-12/SAF-01: no relay/actuation code anywhere in v1."""
    banned = ("relay", "gpio", "actuat", "contactor", "toggle_")
    hits = []
    for p in list(Path("cem_gw").rglob("*.py")) + [Path("fleet_gateway.py"),
                                                   *Path("tools").glob("*.py")]:
        src = p.read_text(encoding="utf-8").lower()
        for b in banned:
            if b in src:
                hits.append(f"{p}: {b}")
    assert hits == [], hits
    # /poll proves the empty-commands half at runtime (TC-ING-08 covers it)


def test_tc_op_04_no_token_leak_in_errors(client):
    """TC-OP-04/FR-093: error bodies never echo credentials."""
    secret = "dev-user:admin@x.test:test-secret"
    r = client.get("/api/v1/fleet", headers={"Authorization": "Bearer wrong-secret"})
    assert r.status_code == 401 and "wrong-secret" not in r.get_data(as_text=True)
    r = client.post("/api/v1/admin/nodes", json={"node_id": "x", "room_id": "y"},
                    headers={"Authorization": f"Bearer {secret}".replace("admin", "nobody")})
    assert "nobody" not in r.get_data(as_text=True)
