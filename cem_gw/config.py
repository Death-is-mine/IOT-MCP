"""Runtime configuration from environment. See docs/03_TRD.md section 8.

FR-008/FR-094: CEM_CONTROL_ENABLED exists, defaults false. v1 has no command
code path at all, so `true` refuses to start instead of silently doing nothing.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass


def _str(e: dict, name: str, default: str) -> str:
    v = e.get(name, default)
    return str(v) if v is not None else default


def _int(e: dict, name: str, default: int) -> int:
    try:
        return int(e.get(name, default))
    except (TypeError, ValueError):
        raise RuntimeError(f"{name} must be an integer")


@dataclass(frozen=True)
class Config:
    db_mode: str = "firestore"  # firestore | memory (memory = local dev/test only)
    auth_mode: str = "firebase"  # firebase | dev (dev = local dev/test only)
    max_body_kb: int = 256
    ingest_rate_per_min: int = 20
    display_tz: str = "Asia/Kolkata"
    flag_rules_file: str | None = None
    firebase_project_id: str = "iot-mcp"
    firebase_region: str = "asia-south1"
    service_account_json: str | None = None
    backup_dir: str = "./var/backups"
    export_dir: str = "./var/exports"
    bind_host: str = "127.0.0.1"
    port: int = 8080
    sample_period_s: int = 5
    batch_interval_s: int = 30
    flag_interval_s: int = 60
    dev_secret: str | None = None
    dev_admin: str | None = None

    @classmethod
    def from_env(cls, env: dict | None = None) -> Config:
        e = dict(env if env is not None else os.environ)
        if str(e.get("CEM_CONTROL_ENABLED", "false")).lower() == "true":
            raise RuntimeError(
                "CEM_CONTROL_ENABLED=true is not supported in v1 (monitor-only, "
                "no command code path exists). Refusing to start."
            )
        db_mode = _str(e, "CEM_DB_MODE", "firestore").lower()
        if db_mode not in ("firestore", "memory"):
            raise RuntimeError("CEM_DB_MODE must be firestore or memory")
        auth_mode = _str(e, "CEM_AUTH_MODE", "firebase").lower()
        if auth_mode not in ("firebase", "dev"):
            raise RuntimeError("CEM_AUTH_MODE must be firebase or dev")
        if (db_mode == "memory" or auth_mode == "dev") and "pytest" not in sys.modules:
            print(
                "WARNING: running with local dev seams "
                f"(CEM_DB_MODE={db_mode}, CEM_AUTH_MODE={auth_mode}); "
                "not for production use.",
                file=sys.stderr,
            )
        return cls(
            db_mode=db_mode,
            auth_mode=auth_mode,
            max_body_kb=_int(e, "CEM_MAX_BODY_KB", 256),
            ingest_rate_per_min=_int(e, "CEM_INGEST_RATE_PER_MIN", 20),
            display_tz=_str(e, "CEM_DISPLAY_TZ", "Asia/Kolkata"),
            flag_rules_file=e.get("CEM_FLAG_RULES_FILE"),
            firebase_project_id=_str(e, "CEM_FIREBASE_PROJECT_ID", "iot-mcp"),
            firebase_region=_str(e, "CEM_FIREBASE_REGION", "asia-south1"),
            service_account_json=e.get("FIREBASE_SERVICE_ACCOUNT_JSON"),
            backup_dir=_str(e, "CEM_BACKUP_DIR", "./var/backups"),
            export_dir=_str(e, "CEM_EXPORT_DIR", "./var/exports"),
            bind_host=_str(e, "CEM_BIND_HOST", "127.0.0.1"),
            port=_int(e, "CEM_PORT", 8080),
            flag_interval_s=_int(e, "CEM_FLAG_INTERVAL_S", 60),
            dev_secret=e.get("CEM_DEV_SECRET"),
            dev_admin=e.get("CEM_DEV_ADMIN"),
        )
