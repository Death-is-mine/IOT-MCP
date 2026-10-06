"""Ground-truth labelling (FR-040..043). Labels immutable; corrections via
supersede. Free-text note stored raw, escaped at render/export (XSS/CSV-safe).
"""
from __future__ import annotations

import uuid

from .util import now_ms

STATES = ("occupied", "vacant", "unsure")
SOURCES = ("scripted_trial", "spot_check", "timetable")
SOURCE_RANK = {"scripted_trial": 3, "spot_check": 2, "timetable": 1}


def create_label(db, room_id: str, ts_start: int, ts_end: int, state: str,
                 source: str, labeller: str, note: str = "") -> dict:
    room_id = (room_id or "").strip()
    if not room_id or len(room_id) > 64:
        raise ValueError("room_id required (<=64 chars)")
    if not isinstance(ts_start, int) or not isinstance(ts_end, int) or not ts_start < ts_end:
        raise ValueError("need ts_start < ts_end as integers")
    if state not in STATES:
        raise ValueError(f"state must be one of {STATES}")
    if source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}")
    labeller = (labeller or "").strip()
    if not labeller or len(labeller) > 8:
        raise ValueError("labeller initials required (<=8 chars)")
    if not isinstance(note, str) or len(note) > 140:
        raise ValueError("note must be a string of at most 140 chars")
    label = {
        "id": uuid.uuid4().hex[:16],
        "room_id": room_id,
        "ts_start": ts_start,
        "ts_end": ts_end,
        "state": state,
        "source": source,
        "labeller": labeller,
        "note": note,
        "created_ts": now_ms(),
        "superseded_by": None,
    }
    db.put_label(label)
    return label


def supersede(db, lid: str, **fields) -> dict:
    """Create a corrected label; the old one keeps its row + superseded_by."""
    old = db.get_label(lid)
    if old is None:
        raise ValueError("unknown label")
    if old.get("superseded_by"):
        raise ValueError("label already superseded")
    merged = {
        "room_id": fields.get("room_id", old["room_id"]),
        "ts_start": fields.get("ts_start", old["ts_start"]),
        "ts_end": fields.get("ts_end", old["ts_end"]),
        "state": fields.get("state", old["state"]),
        "source": fields.get("source", old["source"]),
        "labeller": fields.get("labeller", old["labeller"]),
        "note": fields.get("note", old.get("note", "")),
    }
    new = create_label(db, **merged)
    if not db.mark_superseded(lid, new["id"]):
        raise ValueError("label already superseded")
    return new


def active_labels(db, room_id: str | None = None) -> list[dict]:
    return [lb for lb in db.list_labels(room_id) if not lb.get("superseded_by")]


def conflicts(db, room_id: str | None = None) -> list[dict]:
    """Overlapping active labels with conflicting states (FR-042)."""
    out = []
    for room in {lb["room_id"] for lb in db.list_labels(room_id)}:
        lbs = sorted(active_labels(db, room), key=lambda lb: lb["ts_start"])
        for i, a in enumerate(lbs):
            for b in lbs[i + 1:]:
                if b["ts_start"] >= a["ts_end"]:
                    break
                if a["state"] != b["state"] and a["state"] != "unsure" and b["state"] != "unsure":
                    out.append({"room_id": room, "a_id": a["id"], "b_id": b["id"],
                                "overlap_start": max(a["ts_start"], b["ts_start"]),
                                "overlap_end": min(a["ts_end"], b["ts_end"])})
    return out


def coverage(db) -> list[dict]:
    """Labelled hours per room and state (FR-043)."""
    agg: dict[tuple[str, str], int] = {}
    for lb in active_labels(db):
        if lb["state"] == "unsure":
            continue
        key = (lb["room_id"], lb["state"])
        agg[key] = agg.get(key, 0) + (lb["ts_end"] - lb["ts_start"])
    return [{"room_id": r, "state": s, "hours": round(ms / 3_600_000, 3)}
            for (r, s), ms in sorted(agg.items())]


def label_at(labels: list[dict], room_id: str, ts: int) -> dict | None:
    """Strongest active label covering ts (scripted > spot > timetable)."""
    cands = [lb for lb in labels
             if lb["room_id"] == room_id and lb["ts_start"] <= ts < lb["ts_end"]]
    if not cands:
        return None
    return sorted(cands, key=lambda lb: (SOURCE_RANK[lb["source"]], lb["created_ts"]))[-1]
