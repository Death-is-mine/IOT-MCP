"""Decision configs as explicit rules (AI-02). No learned models in v1;
every config is a pure function of the minute's signals (FR-067 vacuous).
"""
from __future__ import annotations

CO2_PRESENT_PPM = 800


def _sig_minute(samples: list[dict], config: str, scheduled: bool) -> bool:
    pir = any(s.get("pir") == 1 for s in samples)
    mmw = any(s.get("mmwave") == 1 for s in samples)
    co2 = any((s.get("co2_ppm") or 0) >= CO2_PRESENT_PPM for s in samples)
    if config == "pir_only":
        return pir
    if config == "pir_mmwave":
        return pir or mmw
    if config == "pir_co2":
        return pir or co2
    if config == "pir_timetable":
        return pir or scheduled
    if config == "all":
        return pir or mmw or co2 or scheduled
    raise ValueError(f"unknown config {config}")


CONFIGS = ("pir_only", "pir_mmwave", "pir_co2", "pir_timetable", "all")
DEFAULT_HOLDS_MIN = (2, 5, 10, 15, 20, 30)


def describe() -> list[dict]:
    return [{"name": c, "rule": f"presence := {c} (see configs.py)",
             "learned": False} for c in CONFIGS]
