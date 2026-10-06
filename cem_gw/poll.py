"""Poll handler logic. v1 returns an empty commands list and contains no
command-issuing code path (FR-007/FR-008, SEC-12)."""
from __future__ import annotations

from .util import now_ms


def build_poll_response(db, node, recv_ts: int | None = None) -> dict:
    now = recv_ts if recv_ts is not None else now_ms()
    db.update_node(node["node_id"], {"last_seen_ts": now})
    return {
        "server_time": now,
        "config": {
            "mode": node.get("mode", "shadow"),
            "sample_period_s": node.get("sample_period_s", 5),
            "batch_interval_s": node.get("batch_interval_s", 30),
        },
        "commands": [],
    }
