"""Incremental flag engine (FR-020/FR-021). Reads only samples newer than the
stored watermark; a rule-version bump recomputes from scratch without deleting
old flags (old rows keep their rule_version).
"""
from __future__ import annotations

from ..util import now_ms
from .rules import advance, check_cal_stale, check_fw_mixed, initial_state, load_rules


def watermark_key(node_id: str, rule_version: int) -> str:
    return f"{node_id}:{rule_version}"


def run_node(db, node: dict, thresholds: dict, now: int | None = None) -> list[dict]:
    """Run all rules for one node incrementally. Returns new flags."""
    now = now if now is not None else now_ms()
    rv = thresholds.get("rule_version", 1)
    node_id = node["node_id"]
    wm = db.get_watermark(watermark_key(node_id, rv)) or {}
    state = wm.get("state") or initial_state()
    last_ts = wm.get("last_ts")
    samples = db.read_samples(node_id, frm=(last_ts + 1) if last_ts else None)
    ctx = {
        "sample_period_s": node.get("sample_period_s", 5),
        "timetable_present": bool(db.list_timetable(node.get("room_id"))),
        "thresholds": thresholds,
        "now_ms": now,
    }
    new_state, flags = advance(node_id, samples, state, ctx)
    for f in flags:
        f["computed_ts"] = now
    # Dedup: a flag with same (type, ts_start) under this rule version exists.
    # Range covers stuck-signal lookback (24 h) without scanning all history.
    if flags:
        frm = (last_ts - 90_000_000) if last_ts else None
        seen = {(f["type"], f["ts_start"]) for f in db.read_flags(node_id, frm=frm)
                if f["rule_version"] == rv}
        flags = [f for f in flags if (f["type"], f["ts_start"]) not in seen]
    if flags:
        db.write_flags(flags)
    if samples:
        db.set_watermark(watermark_key(node_id, rv),
                         {"last_ts": samples[-1]["ts"], "state": new_state})
    else:
        # No new samples: still persist stuck-signal evaluation already done above.
        db.set_watermark(watermark_key(node_id, rv),
                         {"last_ts": last_ts, "state": new_state})
        # Stuck flags reference `now`; avoid duplicates by not re-writing when
        # nothing changed is handled by callers running the engine periodically.
    cal = check_cal_stale(node, now, thresholds)
    if cal:
        cal["computed_ts"] = now
        # Write at most one active CAL_STALE per node per rule version.
        active = [f for f in db.read_flags(node_id) if f["type"] == "CAL_STALE"
                  and f["rule_version"] == rv and f["ts_end"] >= now - 86_400_000]
        if not active:
            db.write_flags([cal])
            flags.append(cal)
    return flags


def run_forever(db, config, stop) -> None:
    """Background loop (ADD: every 60 s default). Started by fleet_gateway.main."""
    import traceback

    while not stop.wait(config.flag_interval_s):
        try:
            run_all(db, config)
        except Exception:
            traceback.print_exc()


def run_all(db, config, now: int | None = None) -> dict[str, list[dict]]:
    thresholds = load_rules(config.flag_rules_file)
    now = now if now is not None else now_ms()
    nodes = [n for n in db.list_nodes() if n.get("status") != "disabled"]
    out = {}
    for node in nodes:
        out[node["node_id"]] = run_node(db, node, thresholds, now)
    rv = thresholds.get("rule_version", 1)
    for f in check_fw_mixed(nodes, now, thresholds):
        f["computed_ts"] = now
        seen = {(x["type"], x["ts_start"]) for x in db.read_flags(f["node_id"])
                if x["rule_version"] == rv}
        if (f["type"], f["ts_start"]) not in seen:
            db.write_flags([f])
    return out
