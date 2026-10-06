"""M6 contract tests: eval run lifecycle + results page (TC-EV-07, FR-060/064/065)."""
from __future__ import annotations

import time

from tests.conftest import ROOM, batch, node_hdr, user_hdr

ADMIN = user_hdr("admin@x.test")
VIEW = user_hdr("view@x.test")
T0 = 1_760_000_000_000


def seed(client):
    for k in range(5):
        b = batch(seqs=tuple(range(k * 200 + 1, k * 200 + 201)), ts0=T0 + k * 200 * 5_000)
        for s in b["samples"]:
            s["pir"] = 1 if (s["ts"] // 60_000) % 20 < 5 else 0
        assert client.post("/api/v1/ingest", json=b, headers=node_hdr()).status_code == 200
    lb = {"room_id": ROOM, "ts_start": T0, "ts_end": T0 + 1_000 * 5_000,
          "state": "occupied", "source": "spot_check", "labeller": "SS", "note": ""}
    assert client.post("/api/v1/labels", json=lb,
                       headers=user_hdr("lab@x.test")).status_code == 201


def wait_run(client, rid, timeout_s=15):
    for _ in range(int(timeout_s * 5)):
        run = client.get(f"/api/v1/eval/runs/{rid}", headers=VIEW).get_json()["run"]
        if run["status"] in ("done", "failed"):
            return run
        time.sleep(0.2)
    raise AssertionError("eval run did not finish")


def test_tc_ev_07_results_curve_and_hours(client):
    """TC-EV-07/FR-065/066: curve points + labelled hours behind every figure."""
    seed(client)
    r = client.post("/api/v1/eval/runs",
                    json={"rooms": [ROOM], "from": 0, "to": T0 + 2_000 * 5_000,
                          "configs": ["pir_only", "pir_mmwave"], "holds": [5, 10],
                          "bootstrap_reps": 50}, headers=ADMIN)
    assert r.status_code == 202
    rid = r.get_json()["run"]["id"]
    run = wait_run(client, rid)
    assert run["status"] == "done", run.get("error")
    res = run["results"][ROOM]["pir_only"]
    assert set(res) == {"5", "10"}
    for hold, m in res.items():
        assert m["labelled_hours"] > 0
        assert m["ci_energy_saved_kwh"]["n_days"] >= 0
    assert client.get("/eval").status_code == 200
    # list endpoint stays slim (no results payload)
    slim = client.get("/api/v1/eval/runs", headers=VIEW).get_json()["runs"]
    assert slim and "results" not in slim[0]


def test_eval_requires_admin(client):
    r = client.post("/api/v1/eval/runs", json={"rooms": [ROOM], "from": 0, "to": 1},
                    headers=VIEW)
    assert r.status_code == 403
    assert client.get("/api/v1/eval/runs/bad-id!", headers=VIEW).status_code == 400
