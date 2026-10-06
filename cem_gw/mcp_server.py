"""Read-only MCP server core (AIRD S1, FR-100, SEC-15).

Separate process (see `mcp_server.py`); reads the gateway's GET APIs with a
read-scoped credential. Six read-only tools; outputs carry ids, enumerated
values and numbers only (no label notes, no labeller initials, no emails).
Every invocation is logged with caller identity. Control is never exposed.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from collections import deque
from contextvars import ContextVar
from dataclasses import dataclass

log = logging.getLogger("cem-mcp")

TOOLSET_VERSION = "1.0.0"  # pinned into every tool description; bump on change
MAX_SPAN_MS = 31 * 86_400_000  # range cap: one month per call

NODE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
RUN_RE = re.compile(r"[0-9a-f]{16}")

_caller: ContextVar[str] = ContextVar("cem_mcp_caller", default="unknown")


class InputError(ValueError):
    """Bad caller argument (surfaced as an MCP tool error)."""


class UpstreamError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"gateway answered {status}")
        self.status = status
        self.body = body


@dataclass(frozen=True)
class MCPConfig:
    gateway: str
    gateway_token: str  # read-scoped gateway credential (viewer role)
    mcp_token: str  # callers present this as Bearer on /mcp
    bind_host: str = "127.0.0.1"  # campus-only; never 0.0.0.0 (SEC)
    port: int = 8090
    rate_per_min: int = 120

    @classmethod
    def from_env(cls, env: dict | None = None) -> MCPConfig:
        e = dict(env if env is not None else os.environ)
        try:
            gateway_token = str(e["CEM_MCP_GATEWAY_TOKEN"])
            mcp_token = str(e["CEM_MCP_TOKEN"])
        except KeyError as missing:
            raise RuntimeError(f"{missing} is required (never commit it)") from None
        if not gateway_token or not mcp_token:
            raise RuntimeError("CEM_MCP_GATEWAY_TOKEN and CEM_MCP_TOKEN must be non-empty")
        try:
            port = int(e.get("CEM_MCP_PORT", "8090"))
            rate = int(e.get("CEM_MCP_RATE_PER_MIN", "120"))
        except ValueError:
            raise RuntimeError("CEM_MCP_PORT and CEM_MCP_RATE_PER_MIN must be integers")
        return cls(
            gateway=str(e.get("CEM_MCP_GATEWAY", "http://127.0.0.1:8080")).rstrip("/"),
            gateway_token=gateway_token,
            mcp_token=mcp_token,
            bind_host=str(e.get("CEM_MCP_HOST", "127.0.0.1")),
            port=port,
            rate_per_min=rate,
        )


def gateway_get_factory(base: str, token: str):
    """Upstream GET closure; raises UpstreamError (never leaks the token)."""

    def get(path: str) -> dict:
        req = urllib.request.Request(base.rstrip("/") + path,
                                     headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            raise UpstreamError(e.code, e.read().decode()[:500]) from None

    return get


def _node_id(v) -> str:
    if not isinstance(v, str) or not NODE_RE.fullmatch(v):
        raise InputError("node_id must be 1-64 chars: letters, digits, _ -")
    return v


def _range(frm, to) -> tuple[int, int]:
    for v in (frm, to):
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise InputError("from_ms/to_ms must be non-negative integers (UTC epoch ms)")
    if to <= frm:
        raise InputError("to_ms must be after from_ms")
    if to - frm > MAX_SPAN_MS:
        raise InputError("range exceeds 31 days; split the query")
    return frm, to


def _run_id(v) -> str:
    if not isinstance(v, str) or not RUN_RE.fullmatch(v):
        raise InputError("run_id must be 16 lowercase hex chars")
    return v


def _strip_eval_run(run: dict) -> dict:
    """Drop operator identity (created_by email); keep everything measurable."""
    return {k: v for k, v in run.items() if k != "created_by"}


def _strip_flag(f: dict) -> dict:
    return {"id": f.get("id"), "type": f.get("type"), "severity": f.get("severity"),
            "ts_start": f.get("ts_start"), "ts_end": f.get("ts_end"),
            "rule_version": f.get("rule_version")}


class ReadTools:
    """The six AIRD S1 tools over an upstream GET callable (injectable)."""

    def __init__(self, get) -> None:
        self._get = get

    def get_fleet_status(self) -> dict:
        nodes = self._get("/api/v1/fleet")["nodes"]
        return {"as_of_ms": int(time.time() * 1000), "nodes": nodes}

    def get_node_flags(self, node_id: str, from_ms: int, to_ms: int) -> dict:
        nid = _node_id(node_id)
        frm, to = _range(from_ms, to_ms)
        try:
            flags = self._get(f"/api/v1/nodes/{nid}/flags?from={frm}&to={to}")["flags"]
        except UpstreamError as e:
            if e.status == 404:
                raise InputError(f"unknown node: {nid}") from None
            raise
        return {"node_id": nid, "from_ms": frm, "to_ms": to,
                "flags": [_strip_flag(f) for f in flags]}

    def get_data_completeness(self, from_ms: int, to_ms: int) -> dict:
        frm, to = _range(from_ms, to_ms)
        span = to - frm
        rows, got_all, exp_all = [], 0, 0
        for n in self._get("/api/v1/fleet")["nodes"]:
            sp = n.get("sample_period_s", 5) or 5
            expected = max(1, span // (sp * 1000))
            count = self._get(f"/api/v1/nodes/{n['node_id']}/readings"
                              f"?from={frm}&to={to}&max_points=1")["count"]
            got_all += count
            exp_all += expected
            rows.append({"node_id": n["node_id"], "room_id": n.get("room_id"),
                         "received": count, "expected": expected,
                         "completeness": round(count / expected, 4)})
        rows.sort(key=lambda r: r["node_id"])
        return {"from_ms": frm, "to_ms": to, "nodes": rows,
                "overall": round(got_all / exp_all, 4) if exp_all else 0.0}

    def get_label_coverage(self) -> dict:
        return {"coverage": self._get("/api/v1/labels/coverage")["coverage"]}

    def list_eval_runs(self) -> dict:
        runs = self._get("/api/v1/eval/runs")["runs"]
        return {"runs": [_strip_eval_run(r) for r in runs]}

    def get_eval_result(self, run_id: str) -> dict:
        rid = _run_id(run_id)
        try:
            run = self._get(f"/api/v1/eval/runs/{rid}")["run"]
        except UpstreamError as e:
            if e.status == 404:
                raise InputError(f"unknown run: {rid}") from None
            raise
        return {"run": _strip_eval_run(run)}


def _logged(name: str, args: dict, fn):
    start = time.time()
    try:
        out = fn()
    except (InputError, UpstreamError) as e:
        log.info("tool=%s caller=%s args=%s error=%s ms=%d",
                 name, _caller.get(), args, e, int((time.time() - start) * 1000))
        raise
    log.info("tool=%s caller=%s args=%s ok bytes=%d ms=%d",
             name, _caller.get(), args, len(json.dumps(out, default=str)),
             int((time.time() - start) * 1000))
    return out


def create_mcp(tools: ReadTools):
    """FastMCP app with static, version-pinned tool descriptions."""
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("cem-readonly", stateless_http=True)

    @mcp.tool()
    def get_fleet_status() -> dict:
        """Fleet status: every node with ONLINE/DEGRADED/OFFLINE, last-seen,
        firmware, completeness and active flags. Read-only. (toolset v1.0.0)"""
        return _logged("get_fleet_status", {}, tools.get_fleet_status)

    @mcp.tool()
    def get_node_flags(node_id: str, from_ms: int, to_ms: int) -> dict:
        """Data-quality flags for one node in [from_ms, to_ms] (UTC epoch ms,
        at most 31 days). Enumerated types and severities only. Read-only.
        (toolset v1.0.0)"""
        return _logged("get_node_flags",
                       {"node_id": node_id, "from_ms": from_ms, "to_ms": to_ms},
                       lambda: tools.get_node_flags(node_id, from_ms, to_ms))

    @mcp.tool()
    def get_data_completeness(from_ms: int, to_ms: int) -> dict:
        """Received vs expected samples per node in [from_ms, to_ms] (UTC epoch
        ms, at most 31 days), plus the fleet overall ratio. Read-only.
        (toolset v1.0.0)"""
        return _logged("get_data_completeness", {"from_ms": from_ms, "to_ms": to_ms},
                       lambda: tools.get_data_completeness(from_ms, to_ms))

    @mcp.tool()
    def get_label_coverage() -> dict:
        """Labelled hours per room and occupancy state. No label text, no
        labeller identities. Read-only. (toolset v1.0.0)"""
        return _logged("get_label_coverage", {}, tools.get_label_coverage)

    @mcp.tool()
    def list_eval_runs() -> dict:
        """Evaluation runs, newest first (ids, params, data hashes; operator
        identities stripped). Read-only. (toolset v1.0.0)"""
        return _logged("list_eval_runs", {}, tools.list_eval_runs)

    @mcp.tool()
    def get_eval_result(run_id: str) -> dict:
        """Full result of one evaluation run: per-config saved energy with
        bootstrap CIs, false-vacant rates and labelled hours. Read-only.
        (toolset v1.0.0)"""
        return _logged("get_eval_result", {"run_id": run_id},
                       lambda: tools.get_eval_result(run_id))

    return mcp


def create_app(cfg: MCPConfig, tools: ReadTools):
    """Starlette app: Bearer gate + per-caller rate limit on /mcp."""
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    window: dict[str, deque] = {}

    class Gate(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if request.url.path.startswith("/mcp"):
                auth = request.headers.get("authorization", "")
                if not hmac.compare_digest(auth, "Bearer " + cfg.mcp_token):
                    return JSONResponse({"error": "unauthorized"}, 401)
                caller = "sha256:" + hashlib.sha256(auth.encode()).hexdigest()[:12]
                now = time.time()
                q = window.setdefault(caller, deque())
                while q and now - q[0] > 60:
                    q.popleft()
                if len(q) >= cfg.rate_per_min:
                    return JSONResponse({"error": "rate_limited"}, 429,
                                        headers={"Retry-After": "60"})
                q.append(now)
                _caller.set(caller)
            return await call_next(request)

    app = create_mcp(tools).streamable_http_app()
    app.add_middleware(Gate)
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    cfg = MCPConfig.from_env()
    tools = ReadTools(gateway_get_factory(cfg.gateway, cfg.gateway_token))
    app = create_app(cfg, tools)
    import uvicorn

    log.info("cem mcp listening on %s:%d upstream=%s", cfg.bind_host, cfg.port,
             cfg.gateway)
    uvicorn.run(app, host=cfg.bind_host, port=cfg.port, log_level="warning")
