"""Timetable CSV import (FR-044). No instructor names: a column that looks
like one is rejected. All-or-nothing: any error stores nothing.
"""
from __future__ import annotations

import csv
import io
import uuid

BANNED_COLUMNS = ("instructor", "teacher", "professor", "staff", "lecturer", "name")


def parse_csv(room_id: str, text: str) -> tuple[list[dict], list[str]]:
    """Returns (entries, errors). Entry: room/weekday/start/end/course."""
    try:
        rows = list(csv.DictReader(io.StringIO(text)))
    except Exception as e:
        return [], [f"unparseable CSV: {e}"]
    if not rows:
        return [], ["empty CSV"]
    header = [ (h or "").strip().lower() for h in (rows[0].keys() or []) ]
    for h in header:
        if any(b in h for b in BANNED_COLUMNS):
            return [], [f"column '{h}' looks like an instructor name; remove it (FR-044)"]
    entries, errs = [], []

    def get(key: str) -> str:
        return (r.get(key) or r.get(key.title()) or "").strip()

    for i, r in enumerate(rows, start=2):
        try:
            dow = int(get("weekday"))
            assert 0 <= dow <= 6
        except (ValueError, AssertionError):
            errs.append(f"row {i}: weekday must be 0-6 (Mon-Sun)")
            continue
        try:
            sh, sm = map(int, get("start").split(":"))
            eh, em = map(int, get("end").split(":"))
            smin, emin = sh * 60 + sm, eh * 60 + em
            assert 0 <= smin < emin <= 24 * 60
        except (ValueError, AssertionError):
            errs.append(f"row {i}: start/end must be HH:MM with start < end")
            continue
        entries.append({"id": uuid.uuid4().hex[:16], "room_id": room_id, "dow": dow,
                        "start_min": smin, "end_min": emin,
                        "course_code": get("course_code") or get("course")})
    if errs:
        return [], errs
    return entries, []


def import_timetable(db, room_id: str, text: str) -> list[dict]:
    entries, errs = parse_csv(room_id, text)
    if errs:
        raise ValueError("; ".join(errs))
    db.replace_timetable(room_id, entries)
    return entries
