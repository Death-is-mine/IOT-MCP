"""Data-quality flag rules QF-01..QF-09 (docs/08_DATA_PIPELINE.md section 4).

Pure functions, test-first with hand-computed golden data (tests/golden/).
Design: the engine feeds ordered samples through `advance()` which updates a
small per-node state dict (kept in `flag_watermarks`). Each run reads ONLY new
samples, so Firestore read cost stays flat. Feeding all samples at once or in
chunks yields identical flags (TC-QF-12).

QF-02/07/08 are detected at ingest time (cem_gw/ingest.py); the rest here.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

DEFAULTS: dict = {
    "rule_version": 1,
    "gap_multiplier": 3,
    "gap_error_min": 15,
    "stuck_pir_hours": 6,
    "stuck_pir_hours_no_tt": 12,
    "stuck_current_zero_var_min": 60,
    "stuck_current_dead_hours": 24,
    "cal_stale_days": 30,
    "bounds": {
        "voltage_v": [80, 300],
        "current_a": [0, 100],
        "co2_ppm": [300, 10000],
        "temp_c": [-5, 60],
        "rh": [0, 100],
        "lux": [0, 100000],
    },
}

RULE_VERSION = 1
SAMPLE_PERIOD_S = 5


def load_rules(path: str | None) -> dict:
    """Load threshold overrides. Changing any threshold must bump rule_version."""
    if not path:
        return dict(DEFAULTS)
    with open(path, encoding="utf-8") as fh:
        custom = json.load(fh)
    merged = dict(DEFAULTS)
    merged.update(custom)
    return merged


def initial_state() -> dict:
    return {
        "last_ts": None,
        "last_seq": None,
        "last_pir": None,
        "last_pir_change_ts": None,
        "last_cur": None,
        "last_cur_change_ts": None,
    }


def _mk(node_id: str, ftype: str, severity: str, ts_start: int, ts_end: int,
         rule_version: int, details: dict) -> dict:
    return {
        "node_id": node_id,
        "type": ftype,
        "severity": severity,
        "ts_start": ts_start,
        "ts_end": ts_end,
        "rule_version": rule_version,
        "details": details,
    }


def advance(node_id: str, samples: list[dict], state: dict, ctx: dict) -> tuple[dict, list[dict]]:
    """Fold ordered samples into state. Returns (new_state, new_flags).

    ctx: {sample_period_s, timetable_present, thresholds, now_ms}
    """
    th = ctx.get("thresholds") or DEFAULTS
    rv = th.get("rule_version", RULE_VERSION)
    sp_ms = ctx.get("sample_period_s", SAMPLE_PERIOD_S) * 1000
    now = ctx.get("now_ms", 0)
    flags: list[dict] = []
    st = dict(state)

    for s in samples:
        ts, seq = s["ts"], s["seq"]
        # QF-01 GAP (time delta or seq discontinuity)
        if st["last_ts"] is not None:
            gap_ms = ts - st["last_ts"]
            seq_jump = seq != st["last_seq"] + 1 if st["last_seq"] is not None else False
            if gap_ms > th["gap_multiplier"] * sp_ms or seq_jump:
                sev = "error" if gap_ms > th["gap_error_min"] * 60_000 else "warn"
                flags.append(_mk(node_id, "GAP", sev, st["last_ts"], ts, rv,
                                 {"gap_ms": gap_ms, "seq_jump": bool(seq_jump)}))
        # QF-05 OUT_OF_RANGE (per sample)
        for field, (lo, hi) in th["bounds"].items():
            v = s.get(field)
            if v is not None and not (lo <= v <= hi):
                flags.append(_mk(node_id, "OUT_OF_RANGE", "warn", ts, ts, rv,
                                 {"field": field, "value": v, "bounds": [lo, hi]}))
        # track signal changes
        pir = s.get("pir")
        if pir is not None and st["last_pir"] is not None and pir != st["last_pir"]:
            st["last_pir_change_ts"] = ts
        if pir is not None and st["last_pir"] is None:
            st["last_pir_change_ts"] = ts
        if pir is not None:
            st["last_pir"] = pir
        cur = s.get("current_a")
        if cur is not None and (st["last_cur"] is None or cur != st["last_cur"]):
            st["last_cur_change_ts"] = ts
        if cur is not None:
            st["last_cur"] = cur
        st["last_ts"] = ts
        st["last_seq"] = seq

    if now and st["last_ts"] is not None:
        # QF-03 STUCK_PIR
        if st["last_pir"] is not None and st["last_pir_change_ts"] is not None:
            if ctx.get("timetable_present"):
                limit_h = th["stuck_pir_hours"]
            else:
                limit_h = th["stuck_pir_hours_no_tt"]
            still_h = (now - st["last_pir_change_ts"]) / 3600_000
            if still_h >= limit_h:
                flags.append(_mk(node_id, "STUCK_PIR", "warn", st["last_pir_change_ts"], now,
                                 rv, {"still_hours": round(still_h, 2)}))
        # QF-04 STUCK_CURRENT
        if st["last_cur"] is not None and st["last_cur_change_ts"] is not None:
            still_ms = now - st["last_cur_change_ts"]
            last_load = samples[-1].get("load_state") if samples else None
            if still_ms >= th["stuck_current_zero_var_min"] * 60_000 and last_load == 1:
                flags.append(_mk(node_id, "STUCK_CURRENT", "warn", st["last_cur_change_ts"],
                                 now, rv, {"still_min": round(still_ms / 60_000, 1),
                                           "reason": "zero-variance-while-on"}))
            if st["last_cur"] == 0 and still_ms >= th["stuck_current_dead_hours"] * 3600_000:
                # Weekday check in UTC (recorded choice; display tz is Kolkata).
                if datetime.fromtimestamp(now / 1000, tz=UTC).weekday() < 5:
                    flags.append(_mk(node_id, "STUCK_CURRENT", "warn",
                                     st["last_cur_change_ts"], now, rv,
                                     {"still_hours": round(still_ms / 3600_000, 1),
                                      "reason": "dead-24h-weekday"}))
    return st, flags


def check_cal_stale(node: dict, now: int, th: dict | None = None) -> dict | None:
    """QF-06 CAL_STALE: calibration missing or older than 30 days."""
    th = th or DEFAULTS
    rv = th.get("rule_version", RULE_VERSION)
    calib_ts = node.get("calib_ts")
    if node.get("calib") is None or calib_ts is None:
        return _mk(node["node_id"], "CAL_STALE", "info",
                   node.get("created_ts", now), now, rv, {"reason": "missing"})
    if now - calib_ts > th["cal_stale_days"] * 86_400_000:
        return _mk(node["node_id"], "CAL_STALE", "info", calib_ts, now, rv,
                   {"reason": "stale", "age_days": round((now - calib_ts) / 86_400_000, 1)})
    return None


def check_fw_mixed(nodes: list[dict], now: int, th: dict | None = None) -> list[dict]:
    """QF-09 FW_MIXED: enabled nodes on differing firmware."""
    th = th or DEFAULTS
    rv = th.get("rule_version", RULE_VERSION)
    fws = {n.get("fw_version") or "" for n in nodes if n.get("status") != "disabled"}
    fws.discard("")
    if len(fws) <= 1:
        return []
    common = sorted(fws)[0]
    return [_mk(n["node_id"], "FW_MIXED", "info", now, now, rv,
                {"fw": n.get("fw_version"), "fleet_versions": sorted(fws)})
            for n in nodes
            if n.get("status") != "disabled" and (n.get("fw_version") or "") != common]
