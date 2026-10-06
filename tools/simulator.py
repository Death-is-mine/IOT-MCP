"""Node simulator: deterministic synthetic batches + ground-truth labels.

Usage:
  python tools/simulator.py --scenario normal_day --nodes 3 --days 2 --seed 1
  python tools/simulator.py --scenario still_occupant_trial --nodes 1 --seed 7

History is replayed fast (all sent_ts in the past), so the gateway honestly
marks it BACKFILLED per QF-07 — good for exercising flags.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import urllib.error
import urllib.request

DAY = 86_400_000
SP = 5_000  # sample_period_ms

SCENARIOS = (
    "normal_day", "gap", "duplicates", "reorder", "clock_skew", "stuck_pir",
    "stuck_current", "backfill_after_outage", "still_occupant_trial", "fan_interference",
)


def gen_samples(rng: random.Random, node_id: str, room: str, start_ms: int, days: int,
                scenario: str) -> tuple[list[dict], list[dict]]:
    """Returns (samples, truth_labels). Deterministic in (seed, scenario, ...)."""
    n = int(days * DAY // SP)
    samples, labels = [], []
    seq = 1
    occ = False  # ground-truth occupancy
    for i in range(n):
        ts = start_ms + i * SP
        tod = (ts // 3_600_000) % 24  # hour of day UTC (synthetic; documented)
        # class-hours occupancy pattern: occupied 9-12 and 14-17 with gaps
        should_occ = tod in (9, 10, 11, 14, 15, 16) and rng.random() < 0.9
        if scenario == "still_occupant_trial":
            should_occ = (i * SP) < 30 * 60_000  # first 30 min: sits still
        if should_occ != occ:
            if samples:
                labels.append(_label(room, samples[0]["ts"] if not labels else labels[-1]["ts_end"],
                                     ts, occ))
            occ = should_occ
        motion = occ and rng.random() < (0.02 if scenario == "still_occupant_trial" else 0.3)
        pir = 0
        if scenario == "stuck_pir":
            pir = 1
        elif motion:
            pir = 1
        load_on = occ or rng.random() < 0.25  # 25% waste: load on while vacant
        if scenario == "still_occupant_trial":
            load_on = True
        current = round(1.2 if load_on else 0.0, 3)
        if scenario == "stuck_current" and load_on:
            current = 1.2
        mmwave = None
        if scenario == "fan_interference":
            mmwave = 1 if (load_on and rng.random() < 0.6) else (1 if occ else 0)
        samples.append({
            "seq": seq, "ts": ts, "current_a": current, "voltage_v": 230.0,
            "power_w": round(current * 230.0 * 0.9, 2), "power_method": "estimated",
            "pf": 0.9, "pir": pir, "mmwave": mmwave, "co2_ppm": 550 + (200 if occ else 0),
            "lux": 320, "temp_c": 29.0, "rh": 48, "load_state": 1 if load_on else 0,
        })
        seq += 1
    if samples:
        labels.append(_label(room, labels[-1]["ts_end"] if labels else samples[0]["ts"],
                             samples[-1]["ts"] + SP, occ))
    # scenario mutations (deterministic, applied after base generation)
    if scenario == "gap" and len(samples) > 400:
        del samples[100:300]  # ~17 min hole -> GAP error
    if scenario == "duplicates":
        samples = samples + [dict(s) for s in samples[:50]]
    if scenario == "reorder" and len(samples) > 60:
        seg = samples[10:60]
        samples = samples[:10] + seg[::-1] + samples[60:]
    if scenario == "backfill_after_outage" and len(samples) > 500:
        del samples[100:460]  # 30 min outage hole
    return samples, labels


def _label(room, start, end, occ):
    return {"room_id": room, "ts_start": start, "ts_end": end,
            "state": "occupied" if occ else "vacant", "source": "scripted_trial"}


def to_batches(samples: list[dict], per_batch: int = 60) -> list[list[dict]]:
    return [samples[i:i + per_batch] for i in range(0, len(samples), per_batch)]


def post_batch(gateway: str, token: str, node_id: str, fw: str, batch_samples: list[dict],
               sent_ts: int, skew_ms: int = 0) -> dict:
    import time

    body = {
        "schema_version": 1, "node_id": node_id, "fw_version": fw,
        "batch_id": f"b-{batch_samples[0]['seq']}", "sent_ts": sent_ts + skew_ms,
        "time_synced": skew_ms == 0, "samples": batch_samples, "events": [],
    }
    data = json.dumps(body).encode()
    for attempt in range(6):
        req = urllib.request.Request(
            gateway.rstrip("/") + "/api/v1/ingest", data=data,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 5:  # real nodes back off and retry
                wait = int(e.headers.get("Retry-After", "60"))
                time.sleep(min(wait, 120))
                continue
            raise
    raise RuntimeError("ingest refused after retries")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="CEM node simulator")
    ap.add_argument("--scenario", default="normal_day", choices=SCENARIOS)
    ap.add_argument("--nodes", type=int, default=3)
    ap.add_argument("--days", type=int, default=2)
    ap.add_argument("--minutes", type=float, default=0,
                    help="span in minutes (overrides --days; small values demo live data)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--gateway", default="http://127.0.0.1:8080")
    ap.add_argument("--dev-secret", default="")
    ap.add_argument("--bearer", default="",
                      help="explicit node bearer token (overrides dev-secret)")
    ap.add_argument("--node-prefix", default="cem-sim")
    ap.add_argument("--node-id", default="",
                    help="exact node id for --nodes 1 (else <prefix>-<k>); room likewise")
    ap.add_argument("--room", default="", help="room for labels (defaults per node)")
    ap.add_argument("--labels-out", default="", help="write ground-truth labels CSV here")
    ap.add_argument("--dry", action="store_true", help="generate but do not post")
    ap.add_argument("--end-now", action="store_true",
                    help="end the synthetic history at the current time (live demo)")
    ap.add_argument("--rate", type=int, default=0,
                    help="batches per minute cap (0 = as fast as the gateway allows)")
    args = ap.parse_args(argv)

    rng = random.Random(args.seed)
    span_ms = int(args.minutes * 60_000) if args.minutes > 0 else args.days * DAY
    if args.end_now:
        import time as _time

        end_ms = int(_time.time() * 1000)
    else:
        end_ms = 1_760_000_000_000  # fixed epoch base => same seed always replays same history
    start_ms = end_ms - span_ms
    all_labels = []
    for k in range(args.nodes):
        if args.node_id and args.nodes == 1:
            node_id = args.node_id
        else:
            node_id = f"{args.node_prefix}-{k + 1}"
        room = args.room or f"room-sim-{k + 1}"
        samples, labels = gen_samples(rng, node_id, room, start_ms, span_ms / DAY,
                                      args.scenario)
        all_labels.extend(labels)
        skew = 60_000 if args.scenario == "clock_skew" else 0
        if not args.dry:
            token = args.bearer or f"dev-node:{node_id}:{args.dev_secret}"
            acc = dup = 0
            for b in to_batches(samples):
                r = post_batch(args.gateway, token, node_id, "0.1.0-sim", b, b[-1]["ts"], skew)
                acc += r["accepted"]
                dup += r["duplicates"]
            print(f"{node_id}: accepted={acc} duplicates={dup}")
    if args.labels_out:
        with open(args.labels_out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["room_id", "ts_start", "ts_end", "state", "source"])
            w.writeheader()
            w.writerows(all_labels)
        print(f"labels: {len(all_labels)} rows -> {args.labels_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
