"""Shared pytest fixtures: dev-auth + memory-db app, seeded node/user."""
from __future__ import annotations

import pytest

from cem_gw import create_app
from cem_gw.config import Config
from cem_gw.db import MemoryDB
from cem_gw.util import now_ms

SECRET = "test-secret"
NODE = "cem-204-a"
ROOM = "room-204"


@pytest.fixture()
def cfg(tmp_path):
    return Config.from_env(
        {
            "CEM_DB_MODE": "memory",
            "CEM_AUTH_MODE": "dev",
            "CEM_CONTROL_ENABLED": "false",
            "CEM_DEV_SECRET": SECRET,
            "CEM_INGEST_RATE_PER_MIN": "1000",
            "CEM_EXPORT_DIR": str(tmp_path / "exports"),
        }
    )


@pytest.fixture()
def db():
    d = MemoryDB()
    now = now_ms()
    d.put_node(
        {
            "node_id": NODE,
            "room_id": ROOM,
            "status": "enabled",
            "fw_version": "0.1.0",
            "mode": "shadow",
            "calib": {"v_nominal": 230.0, "pf": 0.9},
            "calib_ts": now,
            "sample_period_s": 5,
            "batch_interval_s": 30,
            "created_ts": now,
            "last_seen_ts": None,
            "max_seq": None,
        }
    )
    d.put_user({"email": "admin@x.test", "role": "admin", "active": True, "created_ts": now})
    d.put_user({"email": "lab@x.test", "role": "labeller", "active": True, "created_ts": now})
    d.put_user({"email": "view@x.test", "role": "viewer", "active": True, "created_ts": now})
    return d


@pytest.fixture()
def app(cfg, db):
    return create_app(cfg, db)


@pytest.fixture()
def client(app):
    return app.test_client()


def node_hdr(node=NODE):
    return {"Authorization": f"Bearer dev-node:{node}:{SECRET}"}


def user_hdr(email="admin@x.test"):
    return {"Authorization": f"Bearer dev-user:{email}:{SECRET}"}


def batch(node=NODE, seqs=(1, 2, 3), ts0=None, step=5_000, sent_ts=None):
    if ts0 is None:
        ts0 = now_ms() - len(seqs) * step - 1_000
    samples = [
        {
            "seq": s,
            "ts": ts0 + i * step,
            "current_a": 1.2,
            "voltage_v": 230.0,
            "power_w": 270.0,
            "power_method": "measured",
            "pf": 0.95,
            "pir": i % 2,
            "lux": 300,
            "temp_c": 29.0,
            "load_state": 1,
        }
        for i, s in enumerate(seqs)
    ]
    st = sent_ts if sent_ts is not None else ts0 + len(seqs) * step
    return {
        "schema_version": 1,
        "node_id": node,
        "fw_version": "0.1.0",
        "batch_id": "b-1",
        "sent_ts": st,
        "time_synced": True,
        "samples": samples,
        "events": [],
    }
