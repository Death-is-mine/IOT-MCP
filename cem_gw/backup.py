"""Backup/restore. Memory mode: JSON snapshot + SHA-256 file (FR-091/092,
integrity-checked on restore). Firestore mode: gcloud export/import
(documented; needs gcloud + bucket, exercised in prod evidence at M7).
"""
from __future__ import annotations

import json
import os
import subprocess

from .util import canonical_bytes, now_ms, sha256_hex


def backup_memory(db, backup_dir: str) -> dict:
    os.makedirs(backup_dir, exist_ok=True)
    stamp = now_ms()
    snap = db.snapshot()
    raw = canonical_bytes({"stamp": stamp, "snapshot": snap})
    digest = sha256_hex(raw)
    base = os.path.join(backup_dir, f"cem-backup-{stamp}")
    with open(base + ".json", "wb") as fh:
        fh.write(raw)
    with open(base + ".sha256", "w", encoding="utf-8") as fh:
        fh.write(digest + "\n")
    return {"path": base + ".json", "sha256": digest, "stamp": stamp}


def restore_memory(db, path: str) -> dict:
    with open(path, "rb") as fh:
        raw = fh.read()
    with open(os.path.splitext(path)[0] + ".sha256", encoding="utf-8") as fh:
        expect = fh.read().strip()
    if sha256_hex(raw) != expect:
        raise ValueError("backup integrity check failed (sha mismatch)")
    payload = json.loads(raw.decode("utf-8"))
    db.restore(payload["snapshot"])
    if not db.verify_audit_chain():
        raise ValueError("restored audit chain does not verify")
    return {"stamp": payload["stamp"], "sha256": expect}


def backup_firestore(bucket: str, project: str) -> dict:
    """Daily export via gcloud (prod). Raises with stderr on failure."""
    out = f"{bucket}/backup-{now_ms()}"
    cmd = ["gcloud", "firestore", "export", out, f"--project={project}"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if p.returncode != 0:
        raise RuntimeError(f"gcloud export failed: {p.stderr[-2000:]}")
    return {"path": out, "log": p.stdout[-2000:]}
