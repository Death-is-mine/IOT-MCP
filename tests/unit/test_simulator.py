"""TC-OP-05: simulator determinism + scenario ground truth (FR-095)."""
from __future__ import annotations

import sys

sys.path.insert(0, "tools")
import random  # noqa: E402

from simulator import SCENARIOS, gen_samples  # noqa: E402


def gen(seed, scenario="normal_day", days=1):
    return gen_samples(random.Random(seed), "n1", "room-1", 1_760_000_000_000, days, scenario)


def test_tc_op_05_deterministic():
    """Same seed -> byte-identical samples and labels."""
    assert gen(7) == gen(7)
    assert gen(7) != gen(8)


def test_tc_op_05_scenarios_cover_truth():
    for sc in SCENARIOS:
        samples, labels = gen(3, sc)
        assert samples, sc
        assert labels and all(lb["state"] in ("occupied", "vacant") for lb in labels), sc
        # labels tile the underlying time span (transport mutations in
        # gap/duplicates/reorder/backfill scenarios don't change ground truth)
        lo, hi = min(s["ts"] for s in samples), max(s["ts"] for s in samples)
        assert labels[0]["ts_start"] == lo, sc
        assert labels[-1]["ts_end"] == hi + 5_000, sc
        for a, b in zip(labels, labels[1:]):
            assert a["ts_end"] == b["ts_start"], sc


def test_tc_op_05_still_trial_has_occupied_truth():
    _, labels = gen(7, "still_occupant_trial")
    occ = [lb for lb in labels if lb["state"] == "occupied"]
    assert occ and occ[0]["ts_end"] - occ[0]["ts_start"] >= 30 * 60_000
