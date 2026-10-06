"""Decision replay + metrics on a 1-minute grid (docs/08_DATA_PIPELINE.md s5).

Pure functions; hand-computed golden test in tests/unit/test_eval.py.
Vacancy is declared once no presence signal has been seen for H minutes and
clears on the next signal (shadow-mode 'would cut').
"""
from __future__ import annotations

from .configs import _sig_minute

CURRENT_ON_A = 0.05


def build_minutes(samples: list[dict], labels: list[dict], room_id: str, config: str,
                  scheduled_fn=None) -> list[dict]:
    """Collapse samples to minute rows: signal, load, power, truth, method."""
    by_min: dict[int, list[dict]] = {}
    for s in samples:
        by_min.setdefault(s["ts"] // 60_000, []).append(s)
    rows = []
    for minute in sorted(by_min):
        ss = by_min[minute]
        sched = bool(scheduled_fn(minute * 60_000)) if scheduled_fn else False
        curs = [s.get("current_a") for s in ss if s.get("current_a") is not None]
        pwrs = [s.get("power_w") for s in ss if s.get("power_w") is not None]
        meths = {s.get("power_method", "estimated") for s in ss}
        truth = None
        weak = False
        for lb in labels:
            if lb["room_id"] == room_id and lb["ts_start"] <= minute * 60_000 < lb["ts_end"]:
                if lb["source"] == "timetable":
                    weak = True
                elif truth is None:
                    truth = lb["state"]
        rows.append({
            "minute": minute,
            "signal": _sig_minute(ss, config, sched),
            "load_on": bool(curs) and sum(curs) / len(curs) >= CURRENT_ON_A,
            "power_kw": (sum(pwrs) / len(pwrs) / 1000.0) if pwrs else 0.0,
            "method": "measured" if meths == {"measured"} else "estimated",
            "truth": truth,  # occupied | vacant | None (unsure/unlabelled)
            "weak": weak,
        })
    return rows


def replay(rows: list[dict], hold_min: int) -> dict:
    """Returns per-minute declared-vacant flags + metric totals."""
    declared = []
    last_sig = None
    false_events = 0
    disruption = wasted = 0
    saved_m = saved_e = base_waste = 0.0
    for i, r in enumerate(rows):
        if r["signal"]:
            last_sig = i
        vac = last_sig is not None and (i - last_sig) >= hold_min
        # A vacancy declaration starting while truth is occupied is one event.
        if vac and (not declared or not declared[-1]) and r["truth"] == "occupied":
            false_events += 1
        declared.append(vac)
        if r["truth"] == "occupied" and vac:
            disruption += 1
        if r["truth"] == "vacant" and r["load_on"] and not vac:
            wasted += 1
        if r["truth"] == "vacant" and r["load_on"]:
            base_waste += r["power_kw"] / 60.0
            if vac:
                if r["method"] == "measured":
                    saved_m += r["power_kw"] / 60.0
                else:
                    saved_e += r["power_kw"] / 60.0
    strong_min = sum(1 for r in rows if r["truth"] in ("occupied", "vacant"))
    return {
        "false_vacant_events": false_events,
        "disruption_min": disruption,
        "wasted_min": wasted,
        "energy_saved_measured_kwh": round(saved_m, 6),
        "energy_saved_estimated_kwh": round(saved_e, 6),
        "energy_saved_kwh": round(saved_m + saved_e, 6),
        "baseline_wasted_kwh": round(base_waste, 6),
        "labelled_strong_min": strong_min,
    }
