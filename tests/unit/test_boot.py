"""Boot failure modes: clean messages, no tracebacks (human operability)."""
from __future__ import annotations

import pytest


def test_boot_no_credentials_explains(monkeypatch):
    """Bare boot without Firebase credentials returns 2 with guidance."""
    import fleet_gateway

    for var in ("FIREBASE_SERVICE_ACCOUNT_JSON", "FIRESTORE_EMULATOR_HOST",
                "GOOGLE_APPLICATION_CREDENTIALS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("CEM_DB_MODE", "firestore")
    monkeypatch.setenv("CEM_AUTH_MODE", "firebase")
    assert fleet_gateway.main() == 2


def test_boot_dev_without_secret_explains(monkeypatch):
    monkeypatch.setenv("CEM_AUTH_MODE", "dev")
    monkeypatch.setenv("CEM_DB_MODE", "memory")
    monkeypatch.delenv("CEM_DEV_SECRET", raising=False)
    import fleet_gateway

    assert fleet_gateway.main() == 2


def test_firebase_verifier_unconfigured_is_500(monkeypatch):
    """Missing server key is a 500 with guidance, never a 401 (TC-AU-01 edge)."""
    from cem_gw.auth import firebase as fb
    from cem_gw.auth.base import AuthError
    from cem_gw.config import Config

    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    cfg = Config.from_env({"CEM_DB_MODE": "memory", "CEM_AUTH_MODE": "firebase"})
    with pytest.raises(AuthError) as ei:
        fb.verify_token(None, "whatever", cfg)
    assert ei.value.status == 500 and "FIREBASE_SERVICE_ACCOUNT_JSON" in str(ei.value)
