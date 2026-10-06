"""Evaluation runner: offline replay job storing versioned results (FR-060..066).

FR-060: runs outside the request thread (background thread; status queued ->
done/failed). Each run stores params, flag rule version, code version and a
data hash (FR-064). Every figure carries its labelled hours (FR-066).
"""
from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime

from ..export import CODE_VERSION
from ..labels import active_labels
from ..util import canonical_bytes, now_ms, sha256_hex
from . import replay as _replay
from .configs import CONFIGS, DEFAULT_HOLDS_MIN
from .stats import bootstrap_ci


def _scheduled_fn(entries: list[dict], room_id: str):
    room_entries = [e for e in entries if e["room_id"] == room_id]

    def fn(ts_ms: int) -> bool:
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=UTC)  # recorded: UTC
        minute = dt.hour * 60 + dt.minute
        dow = dt.weekday()
        return any(e["dow"] == dow and e["start_min"] <= minute < e["end_min"]
                   for e in room_entries)

    return fn


def _data_hash(node_rows: list, flags: list, labels: list) -> str:
    canon = sorted(
        [n, s["ts"], s["seq"], s.get("current_a"), s.get("power_w"),
         s.get("power_method"), s.get("pir"), s.get("mmwave"),
         s.get("co2_ppm"), s.get("load_state")] for n, s in node_rows)
    return sha256_hex(canonical_bytes({
        "readings": canon,
        "flags": sorted((f["node_id"], f["type"], f["ts_start"], f["ts_end"],
                         f["rule_version"]) for f in flags),
        "labels": sorted((lb["room_id"], lb["ts_start"], lb["ts_end"], lb["state"],
                          lb["source"]) for lb in labels),
    }))


def run_sync(db, params: dict, created_by: str, rule_version: int) -> dict:
    rooms = params["rooms"]
    frm, to = params["from"], params["to"]
    configs = params.get("configs", list(CONFIGS))
    holds = params.get("holds", list(DEFAULT_HOLDS_MIN))
    seed = params.get("seed", 1)
    reps = params.get("bootstrap_reps", 1000)
    bad = [c for c in configs if c not in CONFIGS]
    if bad:
        raise ValueError(f"unknown configs: {bad}")

    labs = [lb for lb in active_labels(db) if lb["room_id"] in rooms
            and lb["ts_end"] > frm and lb["ts_start"] < to]
    tt = [e for e in db.list_timetable() if e["room_id"] in rooms]
    node_rows, all_flags = [], []
    by_room: dict[str, list] = {r: [] for r in rooms}
    for node in sorted(db.list_nodes(), key=lambda n: n["node_id"]):
        if node.get("status") == "disabled" or node["room_id"] not in rooms:
            continue
        for s in db.read_samples(node["node_id"], frm=frm, to=to):
            node_rows.append((node["node_id"], s))
            by_room[node["room_id"]].append(s)
        all_flags.extend(db.read_flags(node["node_id"], frm=frm, to=to))

    results: dict = {}
    for room, samples in by_room.items():
        samples = sorted(samples, key=lambda s: s["ts"])
        sched = _scheduled_fn(tt, room)
        room_res: dict = {}
        for config in configs:
            rows = _replay.build_minutes(
                samples, labs, room, config,
                scheduled_fn=sched if "timetable" in config or config == "all" else None)
            cfg_res: dict = {}
            for hold in holds:
                m = _replay.replay(rows, hold)
                weeks = m["labelled_strong_min"] / (7 * 24 * 60) or 0
                per_week = round(m["false_vacant_events"] / weeks, 4) if weeks else None
                # day-block bootstrap on per-day energy + false events
                by_day: dict[int, list] = {}
                for r in rows:
                    by_day.setdefault(r["minute"] // 1440, []).append(r)
                e_days, f_days = [], []
                for day_rows in by_day.values():
                    dm = _replay.replay(day_rows, hold)
                    e_days.append(dm["energy_saved_kwh"])
                    f_days.append(dm["false_vacant_events"])
                cfg_res[str(hold)] = {
                    **m,
                    "false_per_room_week": per_week,
                    "labelled_hours": round(m["labelled_strong_min"] / 60, 3),
                    "ci_energy_saved_kwh": bootstrap_ci(e_days, seed, reps),
                    "ci_false_events": bootstrap_ci([float(v) for v in f_days], seed + 1, reps),
                }
            room_res[config] = cfg_res
        results[room] = room_res

    weak_min = sum(lb["ts_end"] - lb["ts_start"] for lb in labs if lb["source"] == "timetable")
    run = {
        "id": uuid.uuid4().hex[:16],
        "created_ts": now_ms(),
        "created_by": created_by,
        "status": "done",
        "params": {"rooms": sorted(rooms), "from": frm, "to": to, "configs": configs,
                   "holds": holds, "seed": seed, "bootstrap_reps": reps},
        "rule_version": rule_version,
        "code_version": CODE_VERSION,
        "data_hash": _data_hash(node_rows, all_flags, labs),
        "weak_timetable_hours": round(weak_min / 3_600_000, 3),
        "results": results,
    }
    db.put_run(run)
    return run


def run_async(db, config, params: dict, created_by: str, rule_version: int) -> dict:
    """Queue a run; worker thread flips queued -> done/failed (FR-060)."""
    rid = uuid.uuid4().hex[:16]
    run = {"id": rid, "created_ts": now_ms(), "created_by": created_by, "status": "queued",
           "params": params, "rule_version": rule_version, "code_version": CODE_VERSION,
           "data_hash": "", "results": {}}
    db.put_run(run)

    def _work():
        try:
            done = run_sync(db, params, created_by, rule_version)
            done["id"] = rid
            db.put_run(done)
        except Exception as e:  # noqa: BLE001 (status surface, not silent)
            run["status"] = "failed"
            run["error"] = str(e)[:500]
            db.put_run(run)

    threading.Thread(target=_work, daemon=True).start()
    return run
