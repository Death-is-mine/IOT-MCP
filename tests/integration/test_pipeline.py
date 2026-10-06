"""End-to-end: simulator batches -> ingest -> flags -> labels -> export -> eval.
Mirrors the M7 acceptance flow on synthetic data."""
from __future__ import annotations

import sys

sys.path.insert(0, "tools")
import random  # noqa: E402

from simulator import gen_samples, to_batches  # noqa: E402

from cem_gw.evaluation import runner as _runner  # noqa: E402
from cem_gw.export import build_export  # noqa: E402
from cem_gw.flags import engine as _engine  # noqa: E402
from cem_gw.flags.rules import DEFAULTS  # noqa: E402
from cem_gw.ingest import apply_batch, validate_batch  # noqa: E402
from tests.conftest import NODE, ROOM  # noqa: E402

T0 = 1_760_000_000_000


def post_all(db, samples):
    node = db.get_node(NODE)
    acc = 0
    for b in to_batches(samples, per_batch=60):
        s, e, errs = validate_batch(
            {"schema_version": 1, "node_id": NODE, "fw_version": "0.1.0-sim",
             "batch_id": f"b-{b[0]['seq']}", "sent_ts": b[-1]["ts"],
             "time_synced": True, "samples": b, "events": []}, NODE)
        assert errs == []
        # replayed history arrives late -> honestly marked backfill
        r = apply_batch(db, node, s, e, b[-1]["ts"], b[-1]["ts"] + 3_600_000)
        acc += r["accepted"]
    return acc


def test_pipeline_sim_to_eval(db):
    samples, truth = gen_samples(random.Random(11), NODE, ROOM, T0, 1, "normal_day")
    assert post_all(db, samples) == len({s["seq"] for s in samples})
    # flags fire on synthetic faults (gap/backfill at least)
    flags = _engine.run_node(db, db.get_node(NODE), dict(DEFAULTS), T0 + 86_400_000)
    assert isinstance(flags, list)
    # ground-truth labels in
    for t in truth[:4]:
        db.put_label({"id": f"lb{truth.index(t)}", **t, "labeller": "SS", "note": "",
                      "created_ts": T0, "superseded_by": None})
    # export joins everything deterministically
    eid, blob, manifest = build_export(db, [ROOM], 0, T0 + 86_400_000, "test", "Asia/Kolkata", 1)
    assert eid and manifest["row_counts"]["rows"] > 0 and manifest["sha256_data_csv"]
    # evaluation replays it
    run = _runner.run_sync(db, {"rooms": [ROOM], "from": 0, "to": T0 + 86_400_000,
                                "configs": ["pir_only"], "holds": [5, 10], "seed": 1}, "t", 1)
    assert run["status"] == "done"
    assert set(run["results"][ROOM]["pir_only"]) == {"5", "10"}
    assert db.verify_audit_chain() is True
