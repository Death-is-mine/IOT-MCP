"""Existing entry point (M0: file did not exist, so this thin shim IS the
entry point). All behaviour lives in cem_gw/; this file only wires and serves.
Run:  python fleet_gateway.py   (dev)  |  waitress-serve via systemd (prod)
"""
from __future__ import annotations

from cem_gw import create_app
from cem_gw.config import Config

app = create_app()


def main() -> None:
    import threading

    from cem_gw.flags.engine import run_forever

    cfg: Config = app.config["CEM_CONFIG"]
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


if __name__ == "__main__":
    main()
