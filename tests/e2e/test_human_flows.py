"""Human journeys: browser flows over live HTTP (Chromium).

Login (dev-token tab), fleet, node charts, labelling, export download,
eval results, admin, logout, and the auth gate. TC-UI/TC-SEC live half.
"""
from __future__ import annotations

import urllib.request
from datetime import datetime

import pytest
from playwright.sync_api import expect

from tests.conftest import batch
from tests.e2e.conftest import (
    admin_token,
    dev_login,
    ingest,
    register_node,
    uid,
    wait_for_run,
)

pytestmark = pytest.mark.e2e


def _dt(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%dT%H:%M")


def test_pages_require_auth(page, server):
    """TC-SEC-04 live: every UI page without a token lands on /login."""
    for path in ("/fleet", "/node", "/label", "/export", "/eval", "/admin"):
        page.goto(server + path)
        page.wait_for_url("**/login", timeout=10000)


def test_login_page_and_dev_login(page, server, api):
    """TC-UI live: /login offers all four methods; dev-token login lands
    on /fleet with data visible."""
    nid, room = uid("e2e-node"), uid("e2e-room")
    register_node(api, nid, room)
    page.goto(server + "/login")
    for tab in ("Email / Password", "Google", "Phone", "Dev token"):
        expect(page.locator(".auth-tab", has_text=tab)).to_be_visible()
    page.click('.auth-tab[data-tab="dev"]')
    page.fill("#dev-token", admin_token())
    page.click("#btn-dev-save")
    page.wait_for_url("**/fleet", timeout=10000)
    expect(page.locator("#fleet")).to_contain_text("Node")


def test_fleet_lists_ingested_node(page, server, api):
    nid, room = uid("e2e-node"), uid("e2e-room")
    register_node(api, nid, room)
    st, body = ingest(api, nid, batch(node=nid))
    assert st == 200, body
    dev_login(page, server)
    page.click("#refresh")
    expect(page.locator("#fleet")).to_contain_text(nid, timeout=10000)
    expect(page.locator("#fleet")).to_contain_text(room)


def test_node_page_renders_charts(page, server, api):
    nid, room = uid("e2e-node"), uid("e2e-room")
    register_node(api, nid, room)
    st, body = ingest(api, nid, batch(node=nid, seqs=tuple(range(1, 31))))
    assert st == 200, body
    dev_login(page, server)
    page.goto(server + "/node")
    page.wait_for_selector("#node option", state="attached", timeout=10000)
    page.select_option("#node", nid)
    page.click("#refresh")
    page.wait_for_selector("#ch_power .uplot", timeout=15000)
    page.wait_for_selector("#ch_pres .uplot", timeout=15000)


def test_label_create_flow(page, server):
    room = uid("e2e-room")
    dev_login(page, server)
    page.goto(server + "/label")
    page.fill("#room", room)
    page.fill("#start", "2026-10-01T09:00")
    page.fill("#end", "2026-10-01T10:00")
    page.select_option("#state", "occupied")
    page.fill("#labeller", "E2E")
    page.click("#add")
    expect(page.locator("#labels")).to_contain_text(room, timeout=10000)
    expect(page.locator("#coverage")).to_contain_text(room, timeout=10000)


def test_export_download_flow(page, server, api):
    import time

    nid, room = uid("e2e-node"), uid("e2e-room")
    register_node(api, nid, room)
    now = int(time.time() * 1000)
    ts0 = now - 30 * 60_000
    st, body = ingest(api, nid, batch(node=nid, seqs=tuple(range(1, 21)),
                                      ts0=ts0, step=5_000))
    assert st == 200, body
    dev_login(page, server)
    page.goto(server + "/export")
    page.fill("#rooms", room)
    page.fill("#from", _dt(ts0 - 60_000))
    page.fill("#to", _dt(now))
    page.click("#go")
    page.wait_for_selector("#out a", timeout=15000)
    with page.expect_download() as dl_info:
        page.click("#out a")
    dl = dl_info.value
    assert dl.suggested_filename.endswith(".zip")
    with open(dl.path(), "rb") as fh:
        assert fh.read(2) == b"PK"


def test_eval_run_flow(page, server, api):
    import time

    nid, room = uid("e2e-node"), uid("e2e-room")
    register_node(api, nid, room)
    now = int(time.time() * 1000)
    frm, to = now - 10 * 60_000, now
    st, body = ingest(api, nid, batch(node=nid, seqs=tuple(range(1, 61)),
                                      ts0=frm, step=5_000))
    assert st == 200, body
    st, lb = api.post("/api/v1/labels",
                      {"room_id": room, "ts_start": frm, "ts_end": to,
                       "state": "occupied", "source": "spot_check",
                       "labeller": "E2E", "note": ""}, token=admin_token())
    assert st == 201, lb
    st, created = api.post("/api/v1/eval/runs",
                           {"rooms": [room], "from": frm, "to": to,
                            "configs": ["pir_only"], "holds": [5],
                            "seed": 1, "bootstrap_reps": 5},
                           token=admin_token())
    assert st == 202, created
    run = wait_for_run(api, created["run"]["id"])
    assert run["status"] == "done", run
    assert run["results"][room]["pir_only"]["5"], "expected one result row"

    dev_login(page, server)
    page.goto(server + "/eval")
    page.click("#runs")
    page.wait_for_selector("#run option", state="attached", timeout=10000)
    page.select_option("#run", run["id"])
    expect(page.locator("#meta")).to_contain_text("code ", timeout=15000)
    assert page.locator("#tbl tbody tr").count() >= 1


def test_admin_node_user_audit_flow(page, server):
    nid, room = uid("e2e-node"), uid("e2e-room")
    email = uid("e2e-user") + "@x.test"
    dev_login(page, server)
    page.goto(server + "/admin")
    page.fill("#nid", nid)
    page.fill("#room", room)
    page.click("#addnode")
    expect(page.locator("#newtok")).to_contain_text("ONE-TIME TOKEN", timeout=10000)
    expect(page.locator("#nodes")).to_contain_text(nid, timeout=10000)
    page.fill("#email", email)
    page.click("#adduser")
    expect(page.locator("#users")).to_contain_text(email, timeout=10000)
    page.click("#audit")
    expect(page.locator("#auditlog")).to_contain_text("node.register", timeout=10000)


def test_logout_returns_to_login(page, server):
    dev_login(page, server)
    page.click("#btn-logout")
    page.goto(server + "/fleet")
    page.wait_for_url("**/login", timeout=10000)


def test_security_headers_on_pages(server):
    """TC-SEC-05 live: pages carry CSP without inline scripts, nosniff."""
    req = urllib.request.Request(server + "/login")
    with urllib.request.urlopen(req, timeout=10) as r:
        assert r.status == 200
        csp = r.headers.get("Content-Security-Policy", "")
        assert "script-src 'self'" in csp and "'unsafe-inline'" not in csp
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
