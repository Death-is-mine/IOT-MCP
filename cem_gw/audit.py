"""Append-only audit log with hash chain (FR-080/FR-081, SEC-07)."""
from __future__ import annotations

from .util import now_ms


def record(db, actor: str, action: str, target: str = "", detail: str = "", ip: str = "") -> str:
    return db.append_audit(
        {
            "ts": now_ms(),
            "actor": actor,
            "action": action,
            "target": target,
            "detail": detail[:2000],
            "ip": ip,
        }
    )
