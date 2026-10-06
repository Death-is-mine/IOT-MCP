"""MCP unit tests: input validation, completeness math, output sanitization,
config handling. TC-MCP-01..05 (AIRD S1, FR-100, SEC-15). No network."""
from __future__ import annotations

import pytest

from cem_gw.mcp_server import (
    InputError,
    MCPConfig,
    ReadTools,
    UpstreamError,
)


def stub(routes: dict):
    def get(path: str):
        if path not in routes:
            raise AssertionError(f"unexpected upstream call: {path}")
        out = routes[path]
        if isinstance(out, UpstreamError):
            raise out
        return out

    return get


def test_tc_mcp_01_input_validation():
    """TC-MCP-01: hostile/malformed tool args rejected before any upstream call."""
    calls = []
    tools = ReadTools(lambda p: calls.append(p) or {})
    for bad in ("", "../x", "a" * 65, "x!y", None, 42):
        with pytest.raises(InputError):
            tools.get_node_flags(bad, 1, 2)
    for frm, to in ((2, 1), (1, 1), (-1, 2), ("a", 2), (0, 32 * 86_400_000)):
        with pytest.raises(InputError):
            tools.get_node_flags("n1", frm, to)
    for bad in ("zzz", "ABCDEF1234567890", "a" * 15, ""):
        with pytest.raises(InputError):
            tools.get_eval_result(bad)
    assert calls == [], "validation must happen before any upstream I/O"


def test_tc_mcp_02_completeness_math():
    """TC-MCP-02: received/expected per node + overall ratio."""
    tools = ReadTools(stub({
        "/api/v1/fleet": {"nodes": [
            {"node_id": "a", "room_id": "r1", "sample_period_s": 5},
            {"node_id": "b", "room_id": "r2", "sample_period_s": 10}]},
        "/api/v1/nodes/a/readings?from=0&to=60000&max_points=1": {"count": 12},
        "/api/v1/nodes/b/readings?from=0&to=60000&max_points=1": {"count": 3},
    }))
    out = tools.get_data_completeness(0, 60_000)
    assert out["nodes"][0] == {"node_id": "a", "room_id": "r1", "received": 12,
                               "expected": 12, "completeness": 1.0}
    assert out["nodes"][1]["completeness"] == pytest.approx(0.5)
    assert out["overall"] == pytest.approx(round(15 / 18, 4))


def test_tc_mcp_03_no_free_text_or_identity_in_outputs():
    """TC-MCP-03/SEC-15: notes, labeller initials and operator emails stripped."""
    run = {"id": "a" * 16, "created_ts": 1, "created_by": "op@x.test",
           "status": "done", "params": {}, "results": {"r": {}}}
    tools = ReadTools(stub({
        "/api/v1/eval/runs": {"runs": [run]},
        "/api/v1/eval/runs/" + "a" * 16: {"run": run},
        "/api/v1/nodes/n1/flags?from=0&to=9": {"flags": [
            {"id": "f1", "node_id": "n1", "type": "GAP", "severity": "warn",
             "ts_start": 1, "ts_end": 2, "rule_version": 1,
             "details": {"reason": "anything goes here"}, "extra": "x"}]},
    }))
    listed = tools.list_eval_runs()["runs"][0]
    assert "created_by" not in listed and listed["id"] == "a" * 16
    full = tools.get_eval_result("a" * 16)["run"]
    assert "created_by" not in full and full["results"] == {"r": {}}
    flag = tools.get_node_flags("n1", 0, 9)["flags"][0]
    assert flag == {"id": "f1", "type": "GAP", "severity": "warn",
                    "ts_start": 1, "ts_end": 2, "rule_version": 1}


def test_tc_mcp_04_upstream_failures_mapped():
    """TC-MCP-04: unknown node/run -> InputError; gateway 500 propagates."""
    tools = ReadTools(stub({
        "/api/v1/nodes/nope/flags?from=0&to=9": UpstreamError(404, "nope"),
        "/api/v1/eval/runs/" + "b" * 16: UpstreamError(404, "nope"),
        "/api/v1/fleet": UpstreamError(500, "boom"),
    }))
    with pytest.raises(InputError, match="unknown node"):
        tools.get_node_flags("nope", 0, 9)
    with pytest.raises(InputError, match="unknown run"):
        tools.get_eval_result("b" * 16)
    with pytest.raises(UpstreamError):
        tools.get_fleet_status()


def test_tc_mcp_05_config_requires_tokens():
    """TC-MCP-05: tokens required and non-empty; ports/rates validated."""
    base = {"CEM_MCP_GATEWAY_TOKEN": "gw", "CEM_MCP_TOKEN": "mcp"}
    cfg = MCPConfig.from_env(dict(base))
    assert (cfg.gateway, cfg.port, cfg.rate_per_min) == ("http://127.0.0.1:8080",
                                                         8090, 120)
    for env in ({}, {"CEM_MCP_TOKEN": "mcp"}, {"CEM_MCP_GATEWAY_TOKEN": "",
                                               "CEM_MCP_TOKEN": "mcp"},
                dict(base, CEM_MCP_PORT="x")):
        with pytest.raises(RuntimeError):
            MCPConfig.from_env(env)
