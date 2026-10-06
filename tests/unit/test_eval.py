"""Golden tests for evaluation replay/metrics/stats. Hand calc: 60-min fixture
(signal min 0-9, truth occupied 0-29 / vacant 30-59, 0.27 kW load always on,
hold 10) => 1 false event, 11 disruption min, 0 wasted min, 0.135 kWh saved
(measured), 0.135 kWh baseline. Covers TC-EV-01..06, TC-EV-08.
"""
from __future__ import annotations

from cem_gw.evaluation import configs, replay, runner
from cem_gw.evaluation.stats import bootstrap_ci

T0 = 1_760_000_000_000  # minute-aligned base


def fixture_rows(hold=10):
    samples = []
    for m in range(60):
        for k in range(12):  # 12 x 5 s per minute
            samples.append({
                "seq": m * 12 + k, "ts": T0 + m * 60_000 + k * 5_000,
                "current_a": 1.2, "power_w": 270.0, "power_method": "measured",
                "pir": 1 if m < 10 else 0, "load_state": 1,
            })
    labels = [
        {"room_id": "r", "ts_start": T0, "ts_end": T0 + 30 * 60_000,
         "state": "occupied", "source": "spot_check"},
        {"room_id": "r", "ts_start": T0 + 30 * 60_000, "ts_end": T0 + 60 * 60_000,
         "state": "vacant", "source": "spot_check"},
    ]
    rows = replay.build_minutes(samples, labels, "r", "pir_only")
    return replay.replay(rows, hold)


def test_tc_ev_01_false_events():
    """TC-EV-01: hand-computed false-vacant event count."""
    assert fixture_rows()["false_vacant_events"] == 1


def test_tc_ev_02_disruption_and_wasted():
    """TC-EV-02: hand-computed disruption and wasted minutes."""
    m = fixture_rows()
    assert m["disruption_min"] == 11
    assert m["wasted_min"] == 0


def test_tc_ev_03_energy_saved_with_method():
    """TC-EV-03: hand-computed energy saved, method-split."""
    m = fixture_rows()
    assert m["energy_saved_kwh"] == 0.135
    assert m["energy_saved_measured_kwh"] == 0.135
    assert m["energy_saved_estimated_kwh"] == 0.0
    assert m["baseline_wasted_kwh"] == 0.135


def test_tc_ev_04_hold_monotonicity():
    """TC-EV-04: larger hold never increases false events or saved energy."""
    falses, saved = [], []
    for h in (2, 5, 10, 15, 20, 30):
        m = fixture_rows(hold=h)
        falses.append(m["false_vacant_events"])
        saved.append(m["energy_saved_kwh"])
    assert all(a >= b for a, b in zip(falses, falses[1:])), falses
    assert all(a >= b for a, b in zip(saved, saved[1:])), saved


def test_tc_ev_05_bootstrap_reproducible():
    """TC-EV-05/FR-063: same seed -> identical CIs; mean inside CI."""
    days = [0.1, 0.2, 0.0, 0.15, 0.1, 0.05]
    a = bootstrap_ci(days, seed=42)
    b = bootstrap_ci(days, seed=42)
    assert a == b and a["n_days"] == 6
    assert a["ci_low"] <= a["mean"] <= a["ci_high"]


def test_tc_ev_06_run_record(db):
    """TC-EV-06/FR-064: stored run has params, versions, data hash."""
    from tests.conftest import NODE, ROOM

    node = db.get_node(NODE)
    samples = [{"seq": i + 1, "ts": T0 + i * 5_000, "current_a": 1.2,
                "power_w": 270.0, "power_method": "measured", "pir": 1,
                "load_state": 1} for i in range(24)]
    from cem_gw.ingest import apply_batch

    apply_batch(db, node, samples, [], T0, T0 + 120_000)
    db.put_label({"id": "lb1", "room_id": ROOM, "ts_start": T0,
                  "ts_end": T0 + 120_000, "state": "occupied",
                  "source": "spot_check", "labeller": "SS", "note": "",
                  "created_ts": T0, "superseded_by": None})
    run = runner.run_sync(db, {"rooms": [ROOM], "from": 0, "to": T0 + 600_000,
                               "configs": ["pir_only"], "holds": [10], "seed": 1}, "admin@x", 1)
    assert run["status"] == "done" and len(run["data_hash"]) == 64
    assert run["rule_version"] == 1 and run["code_version"]
    assert set(run["params"]) >= {"rooms", "from", "to", "configs", "holds", "seed"}
    assert db.get_run(run["id"])["results"][ROOM]["pir_only"]["10"]["labelled_hours"] > 0


def test_tc_ev_08_no_learned_models():
    """TC-EV-08/FR-067: v1 has rule configs only; nothing to leak across splits."""
    assert all(c["learned"] is False for c in configs.describe())
    assert set(configs.CONFIGS) >= {"pir_only"}


def test_all_config_branches():
    """Every decision config fires on its own signal and stays silent without."""
    from cem_gw.evaluation.configs import _sig_minute

    base = {"pir": 0, "mmwave": 0, "co2_ppm": 500}
    assert _sig_minute([{**base, "pir": 1}], "pir_only", False) is True
    assert _sig_minute([base], "pir_only", False) is False
    assert _sig_minute([{**base, "mmwave": 1}], "pir_mmwave", False) is True
    assert _sig_minute([{**base, "co2_ppm": 900}], "pir_co2", False) is True
    assert _sig_minute([base], "pir_timetable", True) is True
    assert _sig_minute([base], "pir_timetable", False) is False
    assert _sig_minute([{**base, "co2_ppm": 900}], "all", False) is True
    assert _sig_minute([base], "all", False) is False
    import pytest

    with pytest.raises(ValueError):
        _sig_minute([base], "nope", False)
