"""M1 contract+unit tests: ingest/poll. IDs map to docs/09_TEST_PLAN.md."""
from __future__ import annotations

import pytest

from cem_gw.config import Config
from cem_gw.ingest import apply_batch, validate_batch
from tests.conftest import NODE, batch, node_hdr


def post(client, b, node=NODE):
    return client.post("/api/v1/ingest", json=b, headers=node_hdr(node))


def test_tc_ing_01_valid_batch(client, db):
    """TC-ING-01: valid batch stored; response counts correct (FR-001/005)."""
    r = post(client, batch())
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["accepted"] == 3 and body["duplicates"] == 0
    assert body["last_seq"] == 3 and "server_time" in body
    assert len(db.read_samples(NODE)) == 3


def test_tc_ing_02_duplicate_batch(client, db):
    """TC-ING-02: same batch twice -> duplicates counted, rows unchanged."""
    b = batch()
    assert post(client, b).get_json()["accepted"] == 3
    r2 = post(client, b).get_json()
    assert r2["accepted"] == 0 and r2["duplicates"] == 3
    assert len(db.read_samples(NODE)) == 3


def test_tc_ing_03_mixed_new_and_dup(client, db):
    """TC-ING-03: mix of new and duplicate seqs."""
    post(client, batch(seqs=(1, 2, 3)))
    body = post(client, batch(seqs=(2, 3, 4, 5))).get_json()
    assert body["accepted"] == 2 and body["duplicates"] == 2
    assert body["last_seq"] == 5


def test_tc_ing_04_invalid_stores_nothing(client, db):
    """TC-ING-04: invalid batch -> 400 with details, nothing stored (FR-003)."""
    b = batch()
    b["samples"][0]["current_a"] = "lots"
    b["samples"][1].pop("ts")
    r = post(client, b)
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid_batch"
    assert len(r.get_json()["details"]) >= 2
    assert db.read_samples(NODE) == []
    # node_id mismatch is also a 400
    b2 = batch(node="cem-evil")
    assert post(client, b2).status_code == 400


def test_tc_ing_05_fault_mid_write_no_partial(db):
    """TC-ING-05: exception during write leaves no partial batch (FR-003)."""
    calls = {"n": 0}

    class Boom(dict):
        def __setitem__(self, k, v):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("injected fault")
            super().__setitem__(k, v)

    db.samples[NODE] = Boom()
    samples, events, errs = validate_batch(batch(seqs=(1, 2, 3)), NODE)
    assert errs == []
    with pytest.raises(RuntimeError):
        apply_batch(db, db.get_node(NODE), samples, events, 1_760_000_000_000, 1_760_000_000_001)
    assert dict(db.samples.get(NODE, {})) == {}, "partial batch must roll back"
    db.samples.pop(NODE, None)


def test_tc_ing_06_backfill_boundary(db):
    """TC-ING-06: backfill iff recv-ts > 300 s (FR-004)."""
    node = db.get_node(NODE)
    ts = 1_760_000_000_000
    r1 = apply_batch(db, node, [{"seq": 1, "ts": ts}], [], ts + 300_000, ts + 300_000)
    assert r1["accepted"] == 1
    assert db.read_samples(NODE)[0]["backfill"] is False
    r2 = apply_batch(db, node, [{"seq": 2, "ts": ts}], [], ts, ts + 300_001)
    assert r2["accepted"] == 1
    got = {x["seq"]: x["backfill"] for x in db.read_samples(NODE)}
    assert got == {1: False, 2: True}


def test_tc_ing_07_size_and_rate(client):
    """TC-ING-07: oversize -> 413; schema over-limit -> 400 (FR-006)."""
    big = batch()
    big["samples"] = big["samples"] * 100  # > 200 sample limit -> 400 (schema)
    assert post(client, big).status_code == 400
    # body-size cap via tiny limit app
    from cem_gw import create_app
    from cem_gw.db import MemoryDB

    tiny_cfg = Config.from_env(
        {
            "CEM_DB_MODE": "memory",
            "CEM_AUTH_MODE": "dev",
            "CEM_DEV_SECRET": "test-secret",
            "CEM_MAX_BODY_KB": "1",
            "CEM_INGEST_RATE_PER_MIN": "1000",
        }
    )
    tdb = MemoryDB()
    tdb.put_node(
        {"node_id": NODE, "room_id": "r", "status": "enabled", "sample_period_s": 5,
         "batch_interval_s": 30, "created_ts": 1, "mode": "shadow"}
    )
    tclient = create_app(tiny_cfg, tdb).test_client()
    over_1k = batch(seqs=tuple(range(40)))  # ~6 KB: over body cap, within schema limits
    assert tclient.post("/api/v1/ingest", json=over_1k, headers=node_hdr()).status_code == 413


def test_tc_ing_07_rate_limit(client, cfg, db):
    """TC-ING-07b: excess rate -> 429 with Retry-After."""
    from cem_gw import create_app

    strict = Config.from_env(
        {
            "CEM_DB_MODE": "memory",
            "CEM_AUTH_MODE": "dev",
            "CEM_DEV_SECRET": "test-secret",
            "CEM_INGEST_RATE_PER_MIN": "1",
        }
    )
    tclient = create_app(strict, db).test_client()
    assert tclient.post("/api/v1/ingest", json=batch(), headers=node_hdr()).status_code == 200
    r = tclient.post("/api/v1/ingest", json=batch(), headers=node_hdr())
    assert r.status_code == 429
    assert r.headers.get("Retry-After") == "60"


def test_tc_ing_08_poll_empty_commands(client, db):
    """TC-ING-08: /poll returns empty commands + updates last-seen (FR-007)."""
    r = client.get("/api/v1/poll?node_id=" + NODE, headers=node_hdr())
    assert r.status_code == 200
    body = r.get_json()
    assert body["commands"] == []
    assert body["config"]["mode"] == "shadow"
    assert "server_time" in body
    assert db.get_node(NODE)["last_seen_ts"] == body["server_time"]


def test_tc_ing_09_control_flag_refuses_start():
    """TC-ING-09/FR-008: CEM_CONTROL_ENABLED=true refuses to start (SEC-12)."""
    with pytest.raises(RuntimeError):
        Config.from_env({"CEM_CONTROL_ENABLED": "true"})


def test_tc_ing_10_idempotent_retry_after_failure(client, db):
    """TC-ING-10 proxy (unit half): failed-then-retried batch stores exactly
    once. Kill -9 survival is proven on prod backend at M7 (AC-03)."""
    b = batch(seqs=(1, 2))
    assert post(client, b).get_json()["accepted"] == 2
    # node retries the same batch after a crash: all duplicates, no loss, no dup rows
    again = post(client, b).get_json()
    assert again["accepted"] == 0 and again["duplicates"] == 2
    assert [s["seq"] for s in db.read_samples(NODE)] == [1, 2]


def test_tc_op_01_healthz_open(client):
    """TC-OP-01/FR-090: /healthz unauthenticated and minimal."""
    r = client.get("/healthz")
    assert r.status_code == 200 and r.get_json() == {"status": "ok"}


def test_tc_sec_01_anon_rejected(client):
    """TC-SEC-01: non-public routes 401 without credentials (SEC-01)."""
    assert client.post("/api/v1/ingest", json=batch()).status_code == 401
    assert client.get("/api/v1/poll").status_code == 401
