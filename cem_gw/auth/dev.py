"""Dev-mode verifier: local dev/test only, never production (D-018).

User tokens:  dev-user:<email>:<CEM_DEV_SECRET>
Node tokens:  dev-node:<node_id>:<CEM_DEV_SECRET>
Requires CEM_DEV_SECRET so stray dev servers are not open by accident.
"""
from __future__ import annotations

from .base import AuthError, Identity


def verify_token(db, token: str, config) -> Identity:
    secret = config.dev_secret
    if not secret:
        raise AuthError("dev auth requires CEM_DEV_SECRET")
    try:
        kind, who, sig = token.split(":", 2)
    except ValueError:
        raise AuthError("malformed token") from None
    if sig != secret:
        raise AuthError("bad token")
    if kind == "dev-node":
        node = db.get_node(who)
        if node is None:
            raise AuthError("unknown node", 401)
        if node.get("status") == "disabled":
            raise AuthError("node disabled", 403)
        return Identity(kind="node", id=who, role="node")
    if kind == "dev-user":
        user = db.get_user(who)
        if user is None or not user.get("active", True):
            raise AuthError("unknown or inactive user", 401)
        return Identity(kind="user", id=who, role=user.get("role", "viewer"), email=who)
    raise AuthError("malformed token")
