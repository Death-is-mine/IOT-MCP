"""M2 contract tests: fleet/readings/flags/events routes (TC-UI-01, TC-AU-03 partial)."""
from __future__ import annotations

from cem_gw.util import now_ms
from tests.conftest import NODE, batch, node_hdr, user_hdr


def seed(client):
    assert client.post("/api/v1/ingest", json=batch(seqs=(1, 2, 3)),
                       headers=node_hdr()).status_code == 200


def test_tc_ui_01_fleet_columns(client):
    """TC-UI-01/FR-030: fleet lists every required column."""
    seed(client)
    r = client.get("/api/v1/fleet", headers=user_hdr("view@x.test"))
    assert r.status_code == 200
    rows = r.get_json()["nodes"]
    assert len(rows) == 1
    n = rows[0]
    for col in ("node_id", "room_id", "status", "last_seen_ts", "fw_version", "mode",
                "completeness_24h", "clock_offset_ms", "calib_age_days", "active_flags"):
        assert col in n, col
    assert n["status"] in ("ONLINE", "DEGRADED", "OFFLINE")


def test_tc_au_role_matrix_reads(client):
    """TC-AU-03 (reads): viewer/labeller/admin allowed, node token + anon denied."""
    seed(client)
    for email in ("view@x.test", "lab@x.test", "admin@x.test"):
        assert client.get("/api/v1/fleet", headers=user_hdr(email)).status_code == 200
    assert client.get("/api/v1/fleet").status_code == 401
    assert client.get("/api/v1/fleet", headers=node_hdr()).status_code == 403


def test_readings_flags_events(client, db):
    seed(client)
    now = now_ms()
    h = user_hdr("view@x.test")
    r = client.get(f"/api/v1/nodes/{NODE}/readings?from=0&to={now}", headers=h)
    assert r.status_code == 200 and r.get_json()["count"] == 3
    r = client.get(f"/api/v1/nodes/{NODE}/flags?from=0&to={now}", headers=h)
    assert r.status_code == 200 and isinstance(r.get_json()["flags"], list)
    r = client.get(f"/api/v1/nodes/{NODE}/events?from=0&to={now}", headers=h)
    assert r.status_code == 200 and r.get_json()["events"] == []
    assert client.get("/api/v1/nodes/nope/readings?from=0&to=1", headers=h).status_code == 404
    assert client.get("/api/v1/nodes/x/flags?from=a&to=1", headers=h).status_code == 400


def test_engine_end_to_end_no_dup(db):
    """Engine writes gap flags once across repeated runs (FR-020 dedup)."""
    from cem_gw.flags import engine
    from cem_gw.flags.rules import DEFAULTS

    node = db.get_node(NODE)
    t0 = 1_760_000_000_000
    from cem_gw.ingest import apply_batch

    apply_batch(db, node, [{"seq": 1, "ts": t0}, {"seq": 5, "ts": t0 + 30_000}],
                [], t0 + 30_000, t0 + 31_000)
    rv = dict(DEFAULTS, rule_version=1)
    engine.run_node(db, db.get_node(NODE), rv, t0 + 31_000)
    n1 = len(db.read_flags(NODE))
    assert n1 >= 1
    engine.run_node(db, db.get_node(NODE), rv, t0 + 60_000)
    assert len(db.read_flags(NODE)) == n1
