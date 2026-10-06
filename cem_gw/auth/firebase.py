"""Production verifier: Firebase Auth ID tokens (users) + Firebase Custom
Token-derived ID tokens (nodes). Verifies via Admin SDK; role comes from
custom claims AND the users allowlist (deny by default). Covers FR-070..072.
"""
from __future__ import annotations

from .base import AuthError, Identity


def _auth(config=None):
    try:
        import firebase_admin
        from firebase_admin import auth, credentials
    except ImportError as e:
        raise AuthError("firebase-admin required for firebase auth mode", 500) from e
    if config is not None:
        try:
            app = firebase_admin.get_app("cem")
        except ValueError:
            app = None
        if app is None:
            if config.service_account_json:
                cred = credentials.Certificate(config.service_account_json)
                app = firebase_admin.initialize_app(
                    cred, {"projectId": config.firebase_project_id}, name="cem")
            else:
                raise AuthError(
                    "server Firebase is not configured: set FIREBASE_SERVICE_ACCOUNT_JSON "
                    "or run the emulator (FIRESTORE_EMULATOR_HOST).", 500)
        try:
            app.credential.get_credential()
        except AuthError:
            raise
        except Exception as e:
            raise AuthError(
                "server Firebase is not configured: set FIREBASE_SERVICE_ACCOUNT_JSON "
                "or run the emulator (FIRESTORE_EMULATOR_HOST).", 500) from e
    return auth


def verify_token(db, token: str, config) -> Identity:
    auth = _auth(config)
    try:
        claims = auth.verify_id_token(token)
    except AuthError:
        raise
    except Exception:
        raise AuthError("invalid token") from None
    uid = claims.get("uid", "")
    if uid.startswith("node:"):
        node_id = uid.split("node:", 1)[1]
        node = db.get_node(node_id)
        if node is None:
            raise AuthError("unknown node", 401)
        if node.get("status") == "disabled":
            raise AuthError("node disabled", 403)
        return Identity(kind="node", id=node_id, role="node")
    email = (claims.get("email") or "").lower()
    if not email or not claims.get("email_verified"):
        raise AuthError("verified email required", 401)
    user = db.get_user(email)
    if user is None or not user.get("active", True):
        raise AuthError("user not allowlisted", 403)
    role = claims.get("role") or user.get("role", "viewer")
    if role not in ("viewer", "labeller", "admin"):
        raise AuthError("bad role claim", 403)
    return Identity(kind="user", id=email, role=role, email=email)


def mint_node_token(node_id: str) -> str:
    """Mint a Firebase Custom Token for a node (TC-NOD-01). The node (or its
    provisioner) exchanges it for an ID token; the gateway verifies the ID
    token above. Token is returned once and never stored (SEC-02)."""
    auth = _auth()
    token = auth.create_custom_token(f"node:{node_id}", {"node_id": node_id, "role": "node"})
    return token.decode()
