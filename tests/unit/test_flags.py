"""Golden tests for flag rules QF-01..QF-09 + engine properties.
Hand calculations in tests/golden/README.md. Covers TC-QF-01..12."""
from __future__ import annotations

from datetime import UTC, datetime

from cem_gw.flags import engine, rules
from cem_gw.flags.rules import DEFAULTS
from cem_gw.ingest import apply_batch

T0 = 1_760_000_000_000


def s(seq, ts, **kw):
    d = {"seq": seq, "ts": ts, "pir": 0, "current_a": 1.0, "voltage_v": 230.0,
         "load_state": 1}
    d.update(kw)
    return d


def ctx(**kw):
    c = {"sample_period_s": 5, "timetable_present": True,
         "thresholds": dict(DEFAULTS), "now_ms": 0}
    c.update(kw)
    return c


def sig(flags):
    return sorted((f["type"], f["severity"], f["ts_start"], f["ts_end"]) for f in flags)


def test_tc_qf_01_gap_warn():
    samples = [s(1, T0), s(2, T0 + 5_000), s(3, T0 + 10_000), s(5, T0 + 30_000)]
    _, flags = rules.advance("n", samples, rules.initial_state(), ctx(now_ms=T0 + 31_000))
    assert ("GAP", "warn", T0 + 10_000, T0 + 30_000) in sig(flags)


def test_tc_qf_01_gap_error():
    samples = [s(1, T0), s(2, T0 + 5_000), s(5, T0 + 20 * 60_000)]
    _, flags = rules.advance("n", samples, rules.initial_state(), ctx(now_ms=T0 + 20 * 60_000 + 1))
    assert ("GAP", "error", T0 + 5_000, T0 + 20 * 60_000) in sig(flags)


def test_tc_qf_02_clock_drift_at_ingest(db):
    node = db.get_node("cem-204-a")
    apply_batch(db, node, [s(1, T0)], [], T0, T0 + 6_000)
    flags = db.read_flags("cem-204-a")
    assert any(f["type"] == "CLOCK_DRIFT" and f["severity"] == "warn" for f in flags)


def test_tc_qf_03_stuck_pir():
    samples = [s(i + 1, T0 + i * 300_000, pir=1) for i in range(73)]  # 6 h span
    now = T0 + 72 * 300_000 + 1_000
    _, flags = rules.advance("n", samples, rules.initial_state(), ctx(now_ms=now))
    stuck = [f for f in flags if f["type"] == "STUCK_PIR"]
    assert len(stuck) == 1 and stuck[0]["severity"] == "warn"
    assert stuck[0]["ts_start"] == T0 and stuck[0]["ts_end"] == now


def test_tc_qf_03_no_tt_needs_12h():
    samples = [s(i + 1, T0 + i * 300_000, pir=1) for i in range(73)]
    now = T0 + 72 * 300_000 + 1_000
    _, flags = rules.advance("n", samples, rules.initial_state(),
                             ctx(now_ms=now, timetable_present=False))
    assert [f for f in flags if f["type"] == "STUCK_PIR"] == []


def test_tc_qf_04_zero_variance_while_on():
    samples = [s(i + 1, T0 + i * 300_000, current_a=2.5, load_state=1) for i in range(13)]
    now = T0 + 12 * 300_000 + 1_000
    _, flags = rules.advance("n", samples, rules.initial_state(), ctx(now_ms=now))
    stuck = [f for f in flags if f["type"] == "STUCK_CURRENT"]
    assert len(stuck) == 1 and stuck[0]["details"]["reason"] == "zero-variance-while-on"


def test_tc_qf_04_dead_24h_weekday():
    monday = int(datetime(2026, 10, 5, 12, tzinfo=UTC).timestamp() * 1000)
    assert datetime.fromtimestamp(monday / 1000, tz=UTC).weekday() == 0
    samples = [s(i + 1, monday + i * 300_000, current_a=0, load_state=0) for i in range(289)]
    now = monday + 288 * 300_000 + 60_000
    _, flags = rules.advance("n", samples, rules.initial_state(), ctx(now_ms=now))
    stuck = [f for f in flags if f["type"] == "STUCK_CURRENT"]
    assert any(f["details"]["reason"] == "dead-24h-weekday" for f in stuck)


def test_tc_qf_05_out_of_range():
    samples = [s(1, T0), s(2, T0 + 5_000, voltage_v=400)]
    _, flags = rules.advance("n", samples, rules.initial_state(), ctx(now_ms=T0 + 6_000))
    oor = [f for f in flags if f["type"] == "OUT_OF_RANGE"]
    assert len(oor) == 1 and oor[0]["details"]["field"] == "voltage_v"
    assert oor[0]["ts_start"] == oor[0]["ts_end"] == T0 + 5_000


def test_tc_qf_06_cal_stale():
    now = T0
    assert rules.check_cal_stale({"node_id": "n", "created_ts": T0 - 1}, now)["type"] == "CAL_STALE"
    old = {"node_id": "n", "calib": {"x": 1},
           "calib_ts": T0 - 31 * 86_400_000, "created_ts": T0 - 40 * 86_400_000}
    assert rules.check_cal_stale(old, now)["details"]["reason"] == "stale"
    fresh = {"node_id": "n", "calib": {"x": 1}, "calib_ts": T0 - 1_000, "created_ts": T0 - 2_000}
    assert rules.check_cal_stale(fresh, now) is None


def test_tc_qf_07_backfilled_flag_at_ingest(db):
    node = db.get_node("cem-204-a")
    apply_batch(db, node, [s(1, T0)], [], T0, T0 + 301_000)
    flags = db.read_flags("cem-204-a")
    assert any(f["type"] == "BACKFILLED" and f["severity"] == "info" for f in flags)


def test_tc_qf_08_seq_reset_at_ingest(db):
    node = db.get_node("cem-204-a")
    apply_batch(db, node, [s(10, T0)], [], T0, T0 + 1_000)
    apply_batch(db, db.get_node("cem-204-a"), [s(3, T0 + 5_000)], [], T0 + 5_000, T0 + 6_000)
    flags = db.read_flags("cem-204-a")
    rst = [f for f in flags if f["type"] == "SEQ_RESET"]
    assert len(rst) == 1 and rst[0]["severity"] == "error"


def test_tc_qf_09_fw_mixed():
    nodes = [
        {"node_id": "a", "status": "enabled", "fw_version": "0.1.0"},
        {"node_id": "b", "status": "enabled", "fw_version": "0.2.0"},
    ]
    flags = rules.check_fw_mixed(nodes, T0)
    assert [(f["node_id"], f["type"]) for f in flags] == [("b", "FW_MIXED")]
    assert rules.check_fw_mixed([nodes[0], dict(nodes[0], node_id="c")], T0) == []


def test_tc_qf_10_rule_bump_keeps_old(db):
    """TC-QF-10 (FR-021): new rule version recomputes without deleting old."""
    from tests.conftest import NODE

    node = db.get_node(NODE)
    apply_batch(db, node, [s(1, T0), s(5, T0 + 30_000)], [], T0 + 30_000, T0 + 31_000)
    rv1 = dict(DEFAULTS, rule_version=1)
    engine.run_node(db, db.get_node(NODE), rv1, T0 + 31_000)
    before = {(f["type"], f["ts_start"], f["rule_version"]) for f in db.read_flags(NODE)}
    assert any(t == ("GAP", T0, 1) for t in before)
    rv2 = dict(DEFAULTS, rule_version=2)
    engine.run_node(db, db.get_node(NODE), rv2, T0 + 31_000)
    after = {(f["type"], f["ts_start"], f["rule_version"]) for f in db.read_flags(NODE)}
    assert before <= after  # old flags untouched
    assert any(t == ("GAP", T0, 2) for t in after)  # recomputed under v2


def test_tc_qf_12_incremental_equals_full():
    """TC-QF-12: chunked advance == one-shot advance."""
    samples = [s(1, T0), s(2, T0 + 5_000), s(5, T0 + 30_000, voltage_v=400)]
    c = ctx(now_ms=T0 + 31_000)
    _, full = rules.advance("n", samples, rules.initial_state(), c)
    st, f1 = rules.advance("n", samples[:2], rules.initial_state(), dict(c, now_ms=0))
    assert f1 == []
    st, f2 = rules.advance("n", samples[2:], st, c)
    assert sig(f1 + f2) == sig(full)


def test_engine_run_all_with_fw_mixed(db):
    """run_all covers fleet rules + watermark advance across runs."""
    from tests.conftest import NODE

    db.put_node({"node_id": "n2", "room_id": "r2", "status": "enabled", "fw_version": "9.9",
                 "mode": "shadow", "sample_period_s": 5, "batch_interval_s": 30,
                 "created_ts": T0, "last_seen_ts": T0, "calib": {"x": 1}, "calib_ts": T0})
    node = db.get_node(NODE)
    apply_batch(db, node, [s(1, T0), s(2, T0 + 5_000)], [], T0 + 5_000, T0 + 6_000)
    from cem_gw.config import Config

    cfg = Config.from_env({"CEM_DB_MODE": "memory", "CEM_AUTH_MODE": "dev",
                           "CEM_DEV_SECRET": "x"})
    first = engine.run_all(db, cfg, T0 + 6_000)
    assert set(first) >= {NODE, "n2"}
    assert any(f["type"] == "FW_MIXED" for f in db.read_flags("n2"))
    # second run with no new data: watermark holds, no new flags at all
    n_before = len(db.read_flags(NODE))
    engine.run_all(db, cfg, T0 + 60_000)
    assert len(db.read_flags(NODE)) == n_before
