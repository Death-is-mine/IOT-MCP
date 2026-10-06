"""MCP journeys: live Streamable HTTP client against seeded gateway data.

TC-MCP-10..14 (AIRD S1, FR-100, SEC-15): tool listing, read journey,
auth, input errors, rate limiting. Server fixtures spawn real processes;
override with CEM_E2E_BASE_URL / CEM_E2E_MCP_URL for existing instances.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time

import pytest

from tests.conftest import batch
from tests.e2e.conftest import (
    ROOT,
    admin_token,
    node_token,
    register_node,
    uid,
    wait_for_run,
)

pytestmark = pytest.mark.e2e

MCP_TOKEN = "mcp-e2e-token"
TOOLS = {"get_fleet_status", "get_node_flags", "get_data_completeness",
         "get_label_coverage", "list_eval_runs", "get_eval_result"}


def mcp_rpc(mcp_base, token, tool=None, args=None, list_only=False):
    import httpx
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    headers = {"Authorization": f"Bearer {token}"} if token else {}

    async def _go():
        async with httpx.AsyncClient(headers=headers, timeout=30) as http:
            async with streamable_http_client(mcp_base + "/mcp",
                                              http_client=http) as streams:
                read, write = streams[0], streams[1]
                async with ClientSession(read, write) as s:
                    await s.initialize()
                    if list_only:
                        found = await s.list_tools()
                        return [(t.name, t.description or "") for t in found.tools]
                    return await s.call_tool(tool, args or {})

    # Isolated thread: browser tests leave the main thread's event loop
    # running, which asyncio.run() refuses to nest into.
    box: dict = {}

    def _target():
        try:
            box["ok"] = asyncio.run(_go())
        except BaseException as e:  # noqa: BLE001 (re-raised below)
            box["err"] = e

    worker = threading.Thread(target=_target, daemon=True)
    worker.start()
    worker.join(timeout=120)
    if "err" in box:
        raise box["err"]
    if "ok" not in box:
        raise TimeoutError("mcp call timed out")
    return box["ok"]


def _result(res):
    assert not res.isError, res.content
    return json.loads(res.content[0].text)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _spawn_mcp(server: str, rate: str):
    ext = os.environ.get("CEM_E2E_MCP_URL", "").rstrip("/")
    if ext:
        return None, ext
    port = _free_port()
    env = dict(os.environ, CEM_MCP_GATEWAY=server,
               CEM_MCP_GATEWAY_TOKEN=admin_token(), CEM_MCP_TOKEN=MCP_TOKEN,
               CEM_MCP_HOST="127.0.0.1", CEM_MCP_PORT=str(port),
               CEM_MCP_RATE_PER_MIN=rate)
    proc = subprocess.Popen([sys.executable, "mcp_server.py"], env=env, cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc, f"http://127.0.0.1:{port}"


def _wait_mcp(base: str, timeout: float = 30.0) -> None:
    """Readiness without spending rate budget: unauthenticated POSTs 401
    in the gate middleware before the rate limiter runs."""
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            req = urllib.request.Request(
                base + "/mcp", data=b"{}",
                headers={"Content-Type": "application/json",
                         "Accept": "application/json, text/event-stream"},
                method="POST")
            urllib.request.urlopen(req, timeout=3)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return
        except OSError:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"mcp server did not answer: {base}")


@pytest.fixture(scope="session")
def mcp_server(server):
    proc, base = _spawn_mcp(server, "1000")
    try:
        _wait_mcp(base)
        yield base
    finally:
        if proc is not None:
            proc.terminate()
            proc.wait(timeout=15)


def test_tc_mcp_10_tool_listing(mcp_server):
    """TC-MCP-10: exactly the six read-only tools, version-pinned blurbs."""
    found = dict(mcp_rpc(mcp_server, MCP_TOKEN, list_only=True))
    assert set(found) == TOOLS
    for name, desc in found.items():
        assert "toolset v1.0.0" in desc, name
        assert "Read-only" in desc or "read-only" in desc.lower(), name


def test_tc_mcp_11_read_journey(mcp_server, api):
    """TC-MCP-11: seeded gateway data readable end to end, outputs clean."""
    import time as _time

    nid, room = uid("e2e-node"), uid("e2e-room")
    register_node(api, nid, room)
    now = int(_time.time() * 1000)
    frm, to = now - 10 * 60_000, now
    st, body = api.post("/api/v1/ingest",
                        batch(node=nid, seqs=tuple(range(1, 31)), ts0=frm,
                              step=5_000),
                        token=node_token(nid))
    assert st == 200, body
    st, lb = api.post("/api/v1/labels",
                      {"room_id": room, "ts_start": frm, "ts_end": to,
                       "state": "occupied", "source": "spot_check",
                       "labeller": "E2E", "note": "must never leak"},
                      token=admin_token())
    assert st == 201, lb
    st, created = api.post("/api/v1/eval/runs",
                           {"rooms": [room], "from": frm, "to": to,
                            "configs": ["pir_only"], "holds": [5],
                            "seed": 1, "bootstrap_reps": 5},
                           token=admin_token())
    assert st == 202, created
    run = wait_for_run(api, created["run"]["id"])
    assert run["status"] == "done", run

    fleet = _result(mcp_rpc(mcp_server, MCP_TOKEN, "get_fleet_status", {}))
    assert nid in {n["node_id"] for n in fleet["nodes"]}

    flags = _result(mcp_rpc(mcp_server, MCP_TOKEN, "get_node_flags",
                            {"node_id": nid, "from_ms": frm, "to_ms": to}))
    assert flags["node_id"] == nid and isinstance(flags["flags"], list)
    assert all(set(f) <= {"id", "type", "severity", "ts_start", "ts_end",
                          "rule_version"} for f in flags["flags"])

    comp = _result(mcp_rpc(mcp_server, MCP_TOKEN, "get_data_completeness",
                           {"from_ms": frm, "to_ms": to}))
    mine = [r for r in comp["nodes"] if r["node_id"] == nid][0]
    assert mine["received"] == 30 and mine["expected"] == 120
    assert mine["completeness"] == pytest.approx(0.25)
    assert 0 < comp["overall"] <= 1.0

    cov = _result(mcp_rpc(mcp_server, MCP_TOKEN, "get_label_coverage", {}))
    assert any(c["room_id"] == room for c in cov["coverage"])
    assert "must never leak" not in json.dumps(cov)

    runs = _result(mcp_rpc(mcp_server, MCP_TOKEN, "list_eval_runs", {}))
    slim = [r for r in runs["runs"] if r["id"] == run["id"]]
    assert slim and "created_by" not in slim[0]

    full = _result(mcp_rpc(mcp_server, MCP_TOKEN, "get_eval_result",
                           {"run_id": run["id"]}))["run"]
    assert full["results"][room]["pir_only"]["5"]
    assert "created_by" not in full


def _flatten(exc: BaseException) -> str:
    """SDK wraps transport errors in a TaskGroup; search the whole tree."""
    parts = [str(exc)]
    for sub in getattr(exc, "exceptions", ()):
        parts.append(_flatten(sub))
    return "\n".join(parts)


def _raises_status(fn, code: int) -> None:
    try:
        fn()
    except BaseException as e:  # noqa: BLE001 (assert on wrapped transport error)
        assert str(code) in _flatten(e), _flatten(e)[:500]
        return
    raise AssertionError(f"expected HTTP {code}")


def test_tc_mcp_12_auth_required(mcp_server):
    """TC-MCP-12: missing/wrong MCP bearer is refused before any tool runs."""
    for token in (None, "", "wrong-token"):
        _raises_status(lambda: mcp_rpc(mcp_server, token, "get_fleet_status", {}),
                       401)


def test_tc_mcp_13_input_errors(mcp_server):
    """TC-MCP-13: hostile args and unknown ids come back as tool errors."""
    res = mcp_rpc(mcp_server, MCP_TOKEN, "get_node_flags",
                  {"node_id": "../x", "from_ms": 0, "to_ms": 9})
    assert res.isError and "node_id" in res.content[0].text
    res = mcp_rpc(mcp_server, MCP_TOKEN, "get_eval_result",
                  {"run_id": "f" * 16})
    assert res.isError and "unknown run" in res.content[0].text


def test_tc_mcp_14_rate_limited(server):
    """TC-MCP-14: a low-rate instance serves 3 requests then says 429."""
    import urllib.error
    import urllib.request

    def _raw_post(base: str) -> int:
        req = urllib.request.Request(
            base + "/mcp", data=b"{}",
            headers={"Content-Type": "application/json",
                     "Accept": "application/json, text/event-stream",
                     "Authorization": f"Bearer {MCP_TOKEN}"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    proc, base = _spawn_mcp(server, "3")
    try:
        _wait_mcp(base)
        statuses = [_raw_post(base) for _ in range(5)]
        assert 429 not in statuses[:3], statuses
        assert statuses[3] == 429, statuses
    finally:
        if proc is not None:
            proc.terminate()
            proc.wait(timeout=15)
