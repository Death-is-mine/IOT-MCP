"""Node registry business logic (FR-010..FR-013). Token minting per backend."""
from __future__ import annotations

from .util import now_ms


def register_node(db, config, node_id: str, room_id: str) -> tuple[dict, str]:
    """Returns (node_doc, one_time_token). Token is never stored (SEC-02)."""
    node_id = node_id.strip()
    if not node_id or len(node_id) > 64:
        raise ValueError("bad node_id")
    if db.get_node(node_id) is not None:
        raise ValueError("node already exists")
    now = now_ms()
    node = {
        "node_id": node_id,
        "room_id": room_id.strip(),
        "status": "enabled",
        "fw_version": "",
        "mode": "shadow",
        "calib": None,
        "calib_ts": None,
        "sample_period_s": config.sample_period_s,
        "batch_interval_s": config.batch_interval_s,
        "created_ts": now,
        "last_seen_ts": None,
        "max_seq": None,
    }
    db.put_node(node)
    token = _mint(db, config, node_id)
    return node, token


def rotate_node_token(db, config, node_id: str) -> str:
    node = db.get_node(node_id)
    if node is None:
        raise ValueError("unknown node")
    return _mint(db, config, node_id)


def _mint(db, config, node_id: str) -> str:
    if config.auth_mode == "dev":
        if not config.dev_secret:
            raise ValueError("dev auth requires CEM_DEV_SECRET")
        return f"dev-node:{node_id}:{config.dev_secret}"
    from .auth.firebase import mint_node_token

    return mint_node_token(node_id)


def random_token_hint() -> str:
    """Dev-mode token prefix hint only; real secret never logged (SEC-09)."""
    return "dev-node:<node_id>:***"


def set_node_status(db, node_id: str, status: str) -> dict:
    if status not in ("enabled", "disabled"):
        raise ValueError("status must be enabled|disabled")
    node = db.update_node(node_id, {"status": status})
    if node is None:
        raise ValueError("unknown node")
    return node


def set_calibration(db, node_id: str, calib: dict) -> dict:
    if not isinstance(calib, dict):
        raise ValueError("calib must be an object")
    node = db.update_node(node_id, {"calib": calib, "calib_ts": now_ms()})
    if node is None:
        raise ValueError("unknown node")
    return node
