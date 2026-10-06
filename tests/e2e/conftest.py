"""E2E fixtures: live gateway on an ephemeral port (no hardcoded host/port).

Set CEM_E2E_BASE_URL to target an existing instance (e.g. staging) instead
of spawning one. Auth uses the dev seam (memory DB); never production.
Covers agent (node HTTP) and human (browser) journeys end to end.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SECRET = "e2e-secret"
ADMIN = "admin-e2e@x.test"


def admin_token() -> str:
    return f"dev-user:{ADMIN}:{SECRET}"


def node_token(node_id: str) -> str:
    return f"dev-node:{node_id}:{SECRET}"


def uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class Api:
    """Minimal stdlib HTTP client (no extra deps). Returns (status, body)."""

    def __init__(self, base: str) -> None:
        self.base = base

    def _req(self, method: str, path: str, body=None, token: str | None = None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(self.base + path, data=data,
                                     headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                raw = r.read().decode()
                return r.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            try:
                return e.code, json.loads(raw) if raw else None
            except ValueError:
                return e.code, {"raw": raw[:20000]}

    def get(self, path: str, token: str | None = None):
        return self._req("GET", path, None, token)

    def post(self, path: str, body, token: str | None = None):
        return self._req("POST", path, body, token)


def _wait_healthy(base: str, timeout: float = 25.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base + "/healthz", timeout=2) as r:
                if r.status == 200:
                    return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"gateway did not become healthy: {base}")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def server(tmp_path_factory):
    ext = os.environ.get("CEM_E2E_BASE_URL", "").rstrip("/")
    if ext:
        _wait_healthy(ext)
        yield ext
        return
    work = tmp_path_factory.mktemp("e2e")
    port = _free_port()
    env = dict(os.environ,
               CEM_DB_MODE="memory", CEM_AUTH_MODE="dev",
               CEM_CONTROL_ENABLED="false", CEM_DEV_SECRET=SECRET,
               CEM_DEV_ADMIN=ADMIN, CEM_INGEST_RATE_PER_MIN="1000",
               CEM_EXPORT_DIR=str(work / "exports"),
               CEM_BACKUP_DIR=str(work / "backups"),
               CEM_BIND_HOST="127.0.0.1", CEM_PORT=str(port))
    proc = subprocess.Popen([sys.executable, "fleet_gateway.py"], env=env, cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_healthy(base)
        yield base
    finally:
        proc.terminate()
        proc.wait(timeout=15)


@pytest.fixture(scope="session")
def api(server):
    return Api(server)


def register_node(api: Api, node_id: str, room_id: str) -> dict:
    st, body = api.post("/api/v1/admin/nodes",
                        {"node_id": node_id, "room_id": room_id},
                        token=admin_token())
    assert st == 201, body
    assert body["token"], "one-time node token must be returned"
    return body


def ingest(api: Api, node_id: str, batch: dict):
    return api.post("/api/v1/ingest", batch, token=node_token(node_id))


def dev_login(page, server: str) -> None:
    """Human login via the Dev-token tab; ends on /fleet."""
    page.goto(server + "/fleet")
    page.wait_for_url("**/login", timeout=10000)
    page.click('.auth-tab[data-tab="dev"]')
    page.fill("#dev-token", admin_token())
    page.click("#btn-dev-save")
    page.wait_for_url("**/fleet", timeout=10000)


def wait_for_run(api: Api, run_id: str, timeout: float = 90.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        st, body = api.get(f"/api/v1/eval/runs/{run_id}", token=admin_token())
        assert st == 200, body
        if body["run"]["status"] in ("done", "failed"):
            return body["run"]
        time.sleep(1.0)
    raise RuntimeError(f"eval run {run_id} did not finish in {timeout}s")
