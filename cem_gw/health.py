"""Liveness probe. Unauthenticated by design; exposes no details (FR-090)."""
from __future__ import annotations


def health_status(db) -> tuple[dict, int]:
    try:
        db.list_nodes()
    except Exception:
        return {"status": "degraded"}, 503
    return {"status": "ok"}, 200
