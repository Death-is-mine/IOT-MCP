"""Reproducible export: deterministic CSV + manifest + dictionary (FR-050..053,
SEC-04/SEC-08). Identical params on identical data -> byte-identical zip.
"""
from __future__ import annotations

import io
import json
import uuid
import zipfile

from . import labels as _labels
from .util import fmt_float, neutralize_csv_cell, now_ms, sha256_hex, to_local_iso

CODE_VERSION = "0.1.0"

COLUMNS = ["ts_utc_ms", "ts_local_iso", "node_id", "room_id", "seq", "current_a",
           "voltage_v", "power_w", "power_method", "pf", "pir", "mmwave", "co2_ppm",
           "lux", "temp_c", "rh", "load_state", "backfill", "active_flags",
           "label_state", "label_source", "label_id"]


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return neutralize_csv_cell(fmt_float(v))
    if isinstance(v, bool):
        return "1" if v else "0"
    return neutralize_csv_cell(v)


def build_csv(db, rooms: list[str], frm: int, to: int, tz: str) -> tuple[bytes, dict]:
    """Returns (csv_bytes, stats). Deterministic row order + formatting."""
    rows = []
    for node in sorted(db.list_nodes(), key=lambda n: n["node_id"]):
        if node.get("status") == "disabled" or node["room_id"] not in rooms:
            continue
        for s in db.read_samples(node["node_id"], frm=frm, to=to):
            rows.append((node, s))
    rows.sort(key=lambda r: (r[0]["node_id"], r[1]["ts"]))
    labs = _labels.active_labels(db)
    lines = [",".join(COLUMNS)]
    for node, s in rows:
        fl = sorted({f["type"] for f in db.read_flags(node["node_id"])
                     if f["ts_start"] <= s["ts"] <= f["ts_end"]})
        lb = _labels.label_at(labs, node["room_id"], s["ts"])
        vals = [s["ts"], to_local_iso(s["ts"], tz), node["node_id"], node["room_id"],
                s["seq"], s.get("current_a"), s.get("voltage_v"), s.get("power_w"),
                s.get("power_method"), s.get("pf"), s.get("pir"), s.get("mmwave"),
                s.get("co2_ppm"), s.get("lux"), s.get("temp_c"), s.get("rh"),
                s.get("load_state"), s.get("backfill"), ";".join(fl),
                lb["state"] if lb else "", lb["source"] if lb else "",
                lb["id"] if lb else ""]
        lines.append(",".join(str(_cell(v)) for v in vals))
    data = ("\n".join(lines) + "\n").encode("utf-8")
    return data, {"rows": len(rows)}


DICTIONARY = """# CEM data dictionary (v1)

All times stored as UTC epoch milliseconds; `ts_local_iso` is Asia/Kolkata
for readability only. `power_method` is `measured` (voltage channel present)
or `estimated` (`V_nominal x current x PF_assumed`; never present as measured).
`active_flags` lists flag types covering the sample timestamp. `label_*`
carry the strongest active ground-truth label or empty cells. Text cells are
CSV-injection neutralised (leading `=+-@` prefixed with `'`). Boolean
`backfill` is 1 when received >300 s after node time.
"""


def build_export(db, rooms: list[str], frm: int, to: int, requester: str,
                 tz: str = "Asia/Kolkata", rule_version: int = 1) -> tuple[str, bytes, dict]:
    csv_data, stats = build_csv(db, rooms, frm, to, tz)
    eid = uuid.uuid4().hex[:16]
    nodes = [n for n in sorted(db.list_nodes(), key=lambda n: n["node_id"])
             if n.get("status") != "disabled" and n["room_id"] in rooms]
    manifest = {
        "export_id": eid,
        "created_ts": now_ms(),
        "requester": requester,
        "params": {"rooms": sorted(rooms), "from": frm, "to": to},
        "rooms": sorted(rooms),
        "nodes": [n["node_id"] for n in nodes],
        "row_counts": stats,
        "flag_rule_version": rule_version,
        "calibration": {n["node_id"]: {"calib": n.get("calib"), "calib_ts": n.get("calib_ts")}
                        for n in nodes},
        "firmware": {n["node_id"]: n.get("fw_version", "") for n in nodes},
        "gateway_code_version": CODE_VERSION,
        "label_precedence": "scripted_trial > spot_check > timetable",
        "sha256_data_csv": sha256_hex(csv_data),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("data.csv", csv_data)
        z.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        z.writestr("data_dictionary.md", DICTIONARY)
    return eid, buf.getvalue(), manifest
