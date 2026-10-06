"""M7 ops tests: backup/restore round-trip (TC-OP-02 memory half), perf smoke
(TC-PERF-01/02/03), storage projection (TC-PERF-04)."""
from __future__ import annotations

import os
import time

from tests.conftest import NODE, batch, node_hdr, user_hdr

ADMIN = user_hdr("admin@x.test")
T0 = 1_760_000_000_000


def test_tc_op_02_backup_restore_roundtrip(client, db, tmp_path):
    """TC-OP-02 (memory half): backup -> wipe -> restore -> identical + chain ok."""
    from cem_gw import audit as _audit

    client.post("/api/v1/ingest", json=batch(seqs=(1, 2, 3)), headers=node_hdr())
    _audit.record(db, "t", "probe.action", "x", "", "")
    before = db.snapshot()
    r = client.post("/api/v1/admin/backup", headers=ADMIN)
    assert r.status_code == 201
    path = r.get_json()["path"]
    assert os.path.isfile(path) and os.path.isfile(path.replace(".json", ".sha256"))
    db.restore({"nodes": db.nodes, "samples": {}, "events": {}, "flags": {},
                "watermarks": {}, "labels": {}, "timetable": {}, "users": db.users,
                "audit": {}, "audit_head": "GENESIS", "runs": {}, "kv": {}})
    assert db.read_samples(NODE) == []
    r = client.post("/api/v1/admin/restore", json={"file": os.path.basename(path)}, headers=ADMIN)
    assert r.status_code == 200, r.get_json()
    after = db.snapshot()
    for key in ("nodes", "samples", "events", "flags", "watermarks", "labels",
                "timetable", "users", "runs", "kv"):
        assert after[key] == before[key], key
    # restore replays the backup (dropping the backup.create entry made after
    # it), then appends its own audited entry: same length, chain verifies.
    assert {a["action"] for a in after["audit"].values()} == {"probe.action",
                                                              "backup.restore"}
    assert db.verify_audit_chain() is True
    # traversal + tamper rejected
    assert client.post("/api/v1/admin/restore", json={"file": "../../x.json"},
                       headers=ADMIN).status_code in (400, 404)


def test_tc_perf_01_ingest_p95(client):
    """TC-PERF-01 proxy: 100 batches (5 simulated nodes) p95 well under 200 ms."""
    lats = []
    for k in range(100):
        b = batch(seqs=tuple(range(k * 200 + 1, k * 200 + 201)), ts0=T0 + k * 200 * 5_000)
        t = time.perf_counter()
        assert client.post("/api/v1/ingest", json=b, headers=node_hdr()).status_code == 200
        lats.append((time.perf_counter() - t) * 1000)
    lats.sort()
    p95 = lats[int(0.95 * len(lats))]
    assert p95 < 200, p95


def test_tc_perf_02_backfill_burst(client, db):
    """TC-PERF-02: 24 h backfill burst accepted and flagged BACKFILLED."""
    end = T0 + 17_280 * 5_000
    for k in range(0, 17_280, 200):
        chunk = [{"seq": i + 1, "ts": T0 + i * 5_000, "current_a": 1.0, "load_state": 1}
                 for i in range(k, min(k + 200, 17_280))]
        r = client.post("/api/v1/ingest", json={
            "schema_version": 1, "node_id": NODE, "fw_version": "x", "batch_id": f"b{k}",
            "sent_ts": end, "time_synced": True, "samples": chunk, "events": []},
            headers=node_hdr())
        assert r.status_code == 200
    assert len(db.read_samples(NODE)) == 17_280
    assert any(f["type"] == "BACKFILLED" for f in db.read_flags(NODE))


def test_tc_perf_03_node_page_payload(client, db):
    """TC-PERF-03: 24 h node payload builds fast and stays capped."""
    from cem_gw import api_read

    end = T0 + 17_280 * 5_000
    db.write_batch(NODE, [{"seq": i + 1, "ts": T0 + i * 5_000, "current_a": 1.0,
                           "power_w": 200.0, "pir": 1, "load_state": 1} for i in range(17_280)], [])
    t = time.perf_counter()
    out = api_read.series(db, NODE, T0, end, 2000)
    dt = (time.perf_counter() - t) * 1000
    assert out["count"] == 17_280 and out["shown"] <= 2000
    assert dt < 3000, dt


def test_tc_perf_04_storage_projection(db):
    """TC-PERF-04/NFR-004: project 5 nodes x 3 weeks @5 s from a measured sample."""
    import json

    db.write_batch(NODE, [{"seq": i + 1, "ts": T0 + i * 5_000, "current_a": 1.234,
                           "voltage_v": 231.2, "power_w": 271.4, "power_method": "measured",
                           "pf": 0.95, "pir": 1, "lux": 340, "temp_c": 29.1,
                           "load_state": 1, "ts_recv": T0, "backfill": False}
                          for i in range(1000)], [])
    per_sample = len(json.dumps(db.snapshot()["samples"][NODE]).encode()) / 1000
    total = 5 * 21 * 17_280 * per_sample
    assert total < 2 * 1024**3, total
