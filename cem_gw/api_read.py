"""Read APIs: fleet status, downsampled series, flags, events (FR-022/023,
FR-030..032). Pure functions over db; handlers stay thin.
"""
from __future__ import annotations

from .util import now_ms, stride_downsample

SERIES_FIELDS = ("current_a", "voltage_v", "power_w", "pir", "mmwave", "co2_ppm",
                 "lux", "temp_c", "rh", "load_state")


def completeness(db, node: dict, window_ms: int, now: int | None = None) -> float:
    """Received / expected samples over the window (FR-022)."""
    now = now if now is not None else now_ms()
    sp = node.get("sample_period_s", 5)
    expected = max(1, window_ms // (sp * 1000))
    got = len(db.read_samples(node["node_id"], frm=now - window_ms, to=now))
    return round(got / expected, 4)


def node_status(db, node: dict, now: int | None = None) -> str:
    """ONLINE / DEGRADED / OFFLINE per docs/08_DATA_PIPELINE.md section 4."""
    now = now if now is not None else now_ms()
    last = node.get("last_seen_ts")
    if last is None or now - last > 3 * node.get("batch_interval_s", 30) * 1000:
        return "OFFLINE"
    recent_err = [f for f in db.read_flags(node["node_id"], frm=now - 3_600_000)
                  if f["severity"] == "error" and f["ts_end"] >= now - 3_600_000]
    if recent_err or completeness(db, node, 3_600_000, now) < 0.9:
        return "DEGRADED"
    return "ONLINE"


def fleet(db, now: int | None = None) -> list[dict]:
    """Fleet rows for FR-030."""
    now = now if now is not None else now_ms()
    rows = []
    for n in db.list_nodes():
        calib_ts = n.get("calib_ts")
        active = db.read_flags(n["node_id"], frm=now - 3_600_000)
        rows.append({
            "node_id": n["node_id"],
            "room_id": n.get("room_id"),
            "status": node_status(db, n, now),
            "last_seen_ts": n.get("last_seen_ts"),
            "fw_version": n.get("fw_version", ""),
            "mode": n.get("mode", "shadow"),
            "completeness_24h": completeness(db, n, 86_400_000, now),
            "clock_offset_ms": n.get("clock_offset_ms"),
            "calib_age_days": round((now - calib_ts) / 86_400_000, 1) if calib_ts else None,
            "active_flags": [{"type": f["type"], "severity": f["severity"],
                              "ts_start": f["ts_start"], "ts_end": f["ts_end"]}
                             for f in active],
        })
    return sorted(rows, key=lambda r: r["node_id"])


def series(db, node_id: str, frm: int, to: int, max_points: int = 2000) -> dict:
    """Downsampled series + flags + events on one axis (FR-031/032/033).

    Rows are decimated as joined rows so every field shares the same x grid
    (chart overlay correctness); nulls mark absent sensors.
    """
    samples = db.read_samples(node_id, frm=frm, to=to)
    rows = stride_downsample(samples, max_points)
    out = {"from": frm, "to": to, "count": len(samples), "shown": len(rows), "series": {}}
    for field in SERIES_FIELDS:
        out["series"][field] = [[r["ts"], r.get(field)] for r in rows]
    out["flags"] = db.read_flags(node_id, frm=frm, to=to)
    out["events"] = db.read_events(node_id, frm=frm, to=to)
    return out
