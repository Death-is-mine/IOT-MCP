"""Day-block bootstrap CIs with recorded seed (FR-063). Resamples whole days
with replacement; reports percentile intervals. Deterministic per seed.
"""
from __future__ import annotations

import random


def _pct(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * q
    lo, hi = int(k), min(len(sorted_vals) - 1, int(k) + 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def bootstrap_ci(day_values: list[float], seed: int, reps: int = 1000) -> dict:
    """day_values: one number per labelled day. Returns mean + 95% CI."""
    rng = random.Random(seed)
    n = len(day_values)
    if n == 0:
        return {"n_days": 0, "mean": 0.0, "ci_low": 0.0, "ci_high": 0.0, "seed": seed}
    means = []
    for _ in range(reps):
        sample = [day_values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    return {"n_days": n, "mean": round(sum(day_values) / n, 6),
            "ci_low": round(_pct(means, 0.025), 6), "ci_high": round(_pct(means, 0.975), 6),
            "seed": seed}
