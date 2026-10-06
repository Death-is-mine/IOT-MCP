"""Ingest validation + application. Handlers stay thin; this module is pure
except for the db write. Covers FR-001..FR-006, FR-008 (no command path).
"""
from __future__ import annotations

from .util import now_ms

SAMPLE_LIMIT = 200
EVENT_LIMIT = 50
EVENT_TYPES = {"boot", "fault", "would_cut", "mode_change", "time_sync", "calib_update"}
BACKFILL_THRESHOLD_MS = 300_000
CLOCK_DRIFT_THRESHOLD_MS = 5_000

_NUMERIC_FIELDS = (
    "current_a",
    "voltage_v",
    "power_w",
    "pf",
    "pir",
    "mmwave",
    "co2_ppm",
    "lux",
    "temp_c",
    "rh",
    "load_state",
)


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _validate_sample(s: dict, i: int) -> tuple[dict | None, list[str]]:
    errs: list[str] = []
    if not isinstance(s, dict):
        return None, [f"samples[{i}]: must be an object"]
    seq, ts = s.get("seq"), s.get("ts")
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
        errs.append(f"samples[{i}].seq: must be a non-negative integer")
    if not isinstance(ts, int) or isinstance(ts, bool) or ts <= 0:
        errs.append(f"samples[{i}].ts: must be a positive UTC epoch-ms integer")
    for f in _NUMERIC_FIELDS:
        v = s.get(f)
        if v is not None and not _is_num(v):
            errs.append(f"samples[{i}].{f}: must be a number or null")
    if s.get("power_method") not in (None, "measured", "estimated"):
        errs.append(f"samples[{i}].power_method: must be measured|estimated")
    for f in ("pir", "load_state"):
        v = s.get(f)
        if v is not None and v not in (0, 1):
            errs.append(f"samples[{i}].{f}: must be 0|1|null")
    if errs:
        return None, errs
    return {k: s.get(k) for k in ("seq", "ts", *_NUMERIC_FIELDS, "power_method")}, []


def _validate_event(e: dict, i: int) -> tuple[dict | None, list[str]]:
    errs: list[str] = []
    if not isinstance(e, dict):
        return None, [f"events[{i}]: must be an object"]
    eseq, ts = e.get("eseq"), e.get("ts")
    if not isinstance(eseq, int) or isinstance(eseq, bool) or eseq < 0:
        errs.append(f"events[{i}].eseq: must be a non-negative integer")
    if not isinstance(ts, int) or isinstance(ts, bool) or ts <= 0:
        errs.append(f"events[{i}].ts: must be a positive UTC epoch-ms integer")
    if e.get("type") not in EVENT_TYPES:
        errs.append(f"events[{i}].type: must be one of {sorted(EVENT_TYPES)}")
    payload = e.get("payload", {})
    if payload is not None and not isinstance(payload, dict):
        errs.append(f"events[{i}].payload: must be an object")
    if errs:
        return None, errs
    return {"eseq": eseq, "ts": ts, "type": e["type"], "payload": payload or {}}, []


def validate_batch(batch: dict, node_id: str) -> tuple[list[dict], list[dict], list[str]]:
    """Returns (samples, events, errors). Any error => caller stores nothing (FR-003)."""
    if not isinstance(batch, dict):
        return [], [], ["body must be a JSON object"]
    errs: list[str] = []
    if batch.get("schema_version") != 1:
        errs.append("schema_version must be 1")
    if batch.get("node_id") != node_id:
        errs.append("node_id mismatch with authenticated node")
    sent_ts = batch.get("sent_ts")
    if not isinstance(sent_ts, int) or isinstance(sent_ts, bool) or sent_ts <= 0:
        errs.append("sent_ts must be a positive UTC epoch-ms integer")
    samples_raw = batch.get("samples", [])
    events_raw = batch.get("events", [])
    if not isinstance(samples_raw, list) or len(samples_raw) > SAMPLE_LIMIT:
        errs.append(f"samples must be a list of at most {SAMPLE_LIMIT}")
        samples_raw = []
    if not isinstance(events_raw, list) or len(events_raw) > EVENT_LIMIT:
        errs.append(f"events must be a list of at most {EVENT_LIMIT}")
        events_raw = []
    samples, events = [], []
    for i, s in enumerate(samples_raw):
        s2, e2 = _validate_sample(s, i)
        if e2:
            errs.extend(e2)
        else:
            samples.append(s2)
    for i, e in enumerate(events_raw):
        e2, e3 = _validate_event(e, i)
        if e3:
            errs.extend(e3)
        else:
            events.append(e2)
    if errs:
        return [], [], errs
    return samples, events, []


def apply_batch(db, node: dict, samples: list[dict], events: list[dict],
                sent_ts: int, recv_ts: int) -> dict:
    """Idempotent, atomic store (FR-002/FR-003) + ingest-time flags.

    Returns ingest response dict (FR-005). Never creates commands (FR-008).
    """
    node_id = node["node_id"]
    backfill = (recv_ts - sent_ts) > BACKFILL_THRESHOLD_MS if sent_ts else False
    for s in samples:
        s["ts_recv"] = recv_ts
        s["backfill"] = bool(backfill or (recv_ts - s["ts"]) > BACKFILL_THRESHOLD_MS)
    for e in events:
        e["ts_recv"] = recv_ts
    prev_max = node.get("max_seq")
    accepted, dups, last_seq = db.write_batch(node_id, samples, events)
    patch: dict = {"last_seen_ts": recv_ts, "clock_offset_ms": recv_ts - sent_ts}
    if samples:
        cands = [s["seq"] for s in samples]
        if prev_max is not None:
            cands.append(prev_max)
        patch["max_seq"] = max(cands)
    db.update_node(node_id, patch)

    flags = []
    if abs(recv_ts - sent_ts) > CLOCK_DRIFT_THRESHOLD_MS:
        flags.append(_flag(node_id, "CLOCK_DRIFT", "warn", sent_ts, recv_ts,
                           {"sent_ts": sent_ts, "recv_ts": recv_ts}))
    if accepted > 0 and samples and prev_max is not None:
        if min(s["seq"] for s in samples) < prev_max:
            flags.append(_flag(node_id, "SEQ_RESET", "error", sent_ts, recv_ts,
                               {"min_new_seq": min(s["seq"] for s in samples),
                                "prev_max_seq": prev_max}))
    if backfill:
        flags.append(_flag(node_id, "BACKFILLED", "info", sent_ts, recv_ts,
                           {"reason": "recv-ts - sent-ts > 300s"}))
    if flags:
        db.write_flags(flags)
    return {
        "accepted": accepted,
        "duplicates": dups,
        "last_seq": last_seq,
        "server_time": now_ms(),
    }


def _flag(node_id, ftype, severity, ts_start, ts_end, details) -> dict:
    return {
        "node_id": node_id,
        "type": ftype,
        "severity": severity,
        "ts_start": ts_start,
        "ts_end": ts_end,
        "rule_version": 1,
        "details": details,
        "computed_ts": now_ms(),
    }
