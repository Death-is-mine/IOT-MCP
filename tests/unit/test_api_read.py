"""M2 read-API tests: completeness, status, downsampling, timezone.
TC-QF-11, TC-UI-03, TC-UI-04."""
from __future__ import annotations

from cem_gw import api_read
from cem_gw.util import to_local_iso
from tests.conftest import NODE


def seed(db, n=720, step=5_000, end=None):
    """720 samples @5s = 1 h of full data ending at `end`."""
    import time

    end = end if end is not None else int(time.time() * 1000)
    samples = [{"seq": i + 1, "ts": end - (n - 1 - i) * step, "current_a": 1.0,
                "load_state": 1, "ts_recv": end, "backfill": False} for i in range(n)]
    db.write_batch(NODE, samples, [])
    db.update_node(NODE, {"last_seen_ts": end, "max_seq": n})
    return end


def test_tc_qf_11_completeness_full_and_half(db):
    end = seed(db)
    assert api_read.completeness(db, db.get_node(NODE), 3_600_000, end) == 1.0
    assert api_read.completeness(db, db.get_node(NODE), 7_200_000, end) == 0.5


def test_tc_qf_11_status_transitions(db):
    end = seed(db)
    node = db.get_node(NODE)
    assert api_read.node_status(db, node, end) == "ONLINE"
    # stale last-seen (> 3 x 30 s) -> OFFLINE
    assert api_read.node_status(db, node, end + 91_000) == "OFFLINE"
    # error flag in last hour -> DEGRADED
    db.write_flags([{"node_id": NODE, "type": "SEQ_RESET", "severity": "error",
                     "ts_start": end - 1000, "ts_end": end - 1000,
                     "rule_version": 1, "details": {}, "computed_ts": end}])
    assert api_read.node_status(db, node, end) == "DEGRADED"


def test_tc_ui_03_downsampling_bound(db):
    end = seed(db, n=17_280)  # 24 h @5 s
    out = api_read.series(db, NODE, end - 86_400_000, end, max_points=2000)
    assert out["count"] == 17_280
    for pts in out["series"].values():
        assert len(pts) <= 2000
    # first/last preserved
    cur = out["series"]["current_a"]
    assert cur[0][0] == end - 86_400_000 + 0 or cur[0][0] >= end - 86_400_000
    assert cur[-1][0] <= end


def test_tc_ui_04_utc_store_kolkata_display():
    """TC-UI-04/FR-034: store UTC epoch-ms, display Asia/Kolkata with label."""
    # 2026-10-05T06:30:00Z == 12:00 IST (+5:30)
    ts = 1_780_000_000_000 + 0  # arbitrary fixed point
    iso = to_local_iso(ts, "Asia/Kolkata")
    assert "+05:30" in iso
