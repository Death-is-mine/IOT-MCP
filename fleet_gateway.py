"""Existing entry point (M0: file did not exist, so this thin shim IS the
entry point). All behaviour lives in cem_gw/; this file only wires and serves.
Run:  python fleet_gateway.py   (dev)  |  waitress-serve via systemd (prod)
"""
from __future__ import annotations

import sys

from cem_gw import create_app
from cem_gw.config import Config
from cem_gw.db import DBError


def main() -> int:
    import threading

    from cem_gw.flags.engine import run_forever

    try:
        cfg = Config.from_env()
        if cfg.auth_mode == "dev" and not cfg.dev_secret:
            raise RuntimeError(
                "CEM_AUTH_MODE=dev needs CEM_DEV_SECRET "
                "(any local string; e.g. $env:CEM_DEV_SECRET='local-only')."
            )
        app = create_app(cfg)
    except (RuntimeError, DBError) as e:
        print(f"cannot start gateway: {e}", file=sys.stderr)
        return 2
    stop = threading.Event()
    worker = threading.Thread(target=run_forever,
                              args=(app.config["CEM_DB"], cfg, stop), daemon=True)
    worker.start()
    try:
        if cfg.db_mode == "firestore" and cfg.auth_mode == "firebase":
            from waitress import serve

            serve(app, host=cfg.bind_host, port=cfg.port)
        else:
            # Dev/test seams active; stdlib server is fine for local use.
            app.run(host=cfg.bind_host, port=cfg.port)
    finally:
        stop.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
