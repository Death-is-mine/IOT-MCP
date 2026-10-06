"""Agent journeys: node registration, ingest, poll over live HTTP.

Mirrors what ESP32 nodes (or the simulator) do against a real gateway:
register once, push idempotent batches, poll for config. TC-ING live half.
"""
from __future__ import annotations

import time

import pytest

from tests.conftest import batch
from tests.e2e.conftest import admin_token, ingest, node_token, register_node, uid

pytestmark = pytest.mark.e2e


def test_agent_register_ingest_poll_idempotent(api):
    """TC-ING-01/02/05 live: register -> ingest -> dedupe replay -> poll.

    FR-008/SEC-12: /poll commands stay empty (monitor-only, v1 has no
    command code path at all).
    """
    nid, room = uid("e2e-node"), uid("e2e-room")
    register_node(api, nid, room)

    b = batch(node=nid, seqs=(1, 2, 3))
    st, body = ingest(api, nid, b)
    assert st == 200, body
    assert body["accepted"] == 3 and body["duplicates"] == 0

    st, body = ingest(api, nid, b)  # device retry of the same batch
    assert st == 200, body
    assert body["accepted"] == 0 and body["duplicates"] == 3

    st, poll = api.get("/api/v1/poll", token=node_token(nid))
    assert st == 200, poll
    assert poll["commands"] == [], "v1 is monitor-only; poll must carry no commands"
    assert poll["config"]["mode"] == "shadow"
    assert abs(poll["server_time"] - int(time.time() * 1000)) < 60_000

    st, fleet = api.get("/api/v1/fleet", token=admin_token())
    assert st == 200, fleet
    seen = {n["node_id"]: n for n in fleet["nodes"]}
    assert nid in seen and seen[nid]["room_id"] == room
    assert seen[nid]["last_seen_ts"] is not None


def test_agent_rejected_states(api):
    """TC-ING-03/04/08 + TC-SEC live: unknown node, bad schema, oversize,
    disabled node all fail closed; re-enable recovers."""
    nid, room = uid("e2e-node"), uid("e2e-room")
    register_node(api, nid, room)

    st, _ = ingest(api, "no-such-node", batch(node="no-such-node"))
    assert st == 401

    st, body = ingest(api, nid, {"schema_version": 1})
    assert st == 400 and body["error"] == "invalid_batch"

    st, body = ingest(api, nid, {"pad": "x" * 300_000})
    assert st == 413, body

    st, _ = api.post(f"/api/v1/admin/nodes/{nid}/status", {"status": "disabled"},
                     token=admin_token())
    assert st == 200
    st, _ = ingest(api, nid, batch(node=nid))
    assert st == 403
    st, _ = api.get("/api/v1/poll", token=node_token(nid))
    assert st == 403

    st, _ = api.post(f"/api/v1/admin/nodes/{nid}/status", {"status": "enabled"},
                     token=admin_token())
    assert st == 200
    st, body = ingest(api, nid, batch(node=nid))
    assert st == 200 and body["accepted"] == 3, body


def test_agent_user_allowlist_deny(api):
    """TC-AUTH live: a well-formed dev token for a non-allowlisted user
    is denied; no token at all is 401."""
    st, _ = api.get("/api/v1/fleet", token="dev-user:ghost@x.test:e2e-secret")
    assert st in (401, 403)
    st, _ = api.get("/api/v1/fleet")
    assert st == 401
