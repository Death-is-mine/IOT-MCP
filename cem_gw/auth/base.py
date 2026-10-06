"""Auth interface + role guards. Firebase is production (DECIDED D-016);
`dev` mode is local dev/test only (DEFAULT D-018). Covers FR-070..FR-072.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import wraps

from flask import g, jsonify, request

ROLE_RANK = {"viewer": 1, "labeller": 2, "admin": 3}


class AuthError(Exception):
    def __init__(self, message: str, status: int = 401):
        super().__init__(message)
        self.status = status


@dataclass
class Identity:
    kind: str  # user | node
    id: str
    role: str = ""  # viewer|labeller|admin for users; node for nodes
    email: str = ""


def get_verifier(config, db):
    if config.auth_mode == "dev":
        from .dev import verify_token as verify
    else:
        from .firebase import verify_token as verify
    return verify


def _bearer() -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise AuthError("missing bearer token")
    return auth[7:]


def identify(config, db) -> Identity:
    verify = get_verifier(config, db)
    return verify(db, _bearer(), config)


def require_user(*roles: str):
    """User with at least the lowest listed role (roles are hierarchical)."""

    def deco(fn):
        @wraps(fn)
        def inner(*a, **kw):
            from flask import current_app

            ident = identify(current_app.config["CEM_CONFIG"], current_app.config["CEM_DB"])
            if ident.kind != "user":
                raise AuthError("user credential required", 403)
            need = min(ROLE_RANK[r] for r in roles)
            if ROLE_RANK.get(ident.role, 0) < need:
                raise AuthError("forbidden for role " + ident.role, 403)
            g.identity = ident
            return fn(*a, **kw)

        return inner

    return deco


def require_node(fn):
    @wraps(fn)
    def inner(*a, **kw):
        from flask import current_app

        ident = identify(current_app.config["CEM_CONFIG"], current_app.config["CEM_DB"])
        if ident.kind != "node":
            raise AuthError("node credential required", 403)
        g.identity = ident
        return fn(*a, **kw)

    return inner


def auth_error_response(e: AuthError):
    return jsonify({"error": "unauthorized" if e.status == 401 else "forbidden",
                    "message": str(e)}), e.status
