"""Backup / restore CLI.

Memory mode (local dev): JSON snapshot + sha file, integrity-checked.
  python tools/backup_restore.py backup --dir ./var/backups
  python tools/backup_restore.py restore --file ./var/backups/cem-backup-<ts>.json
Firestore mode (prod): gcloud export (needs gcloud auth + bucket).
  python tools/backup_restore.py gcloud-export --bucket gs://iot-mcp-backups --project iot-mcp
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cem_gw import backup as _backup  # noqa: E402
from cem_gw.config import Config  # noqa: E402
from cem_gw.db import MemoryDB, get_db  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="CEM backup/restore")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backup")
    b.add_argument("--dir", default="./var/backups")
    r = sub.add_parser("restore")
    r.add_argument("--file", required=True)
    g = sub.add_parser("gcloud-export")
    g.add_argument("--bucket", required=True)
    g.add_argument("--project", default="iot-mcp")
    args = ap.parse_args(argv)
    cfg = Config.from_env()
    if args.cmd == "gcloud-export":
        print(_backup.backup_firestore(args.bucket, args.project))
        return 0
    if cfg.db_mode != "memory":
        print("local backup/restore supports memory mode only; "
              "use gcloud-export for firestore", file=sys.stderr)
        return 2
    db = get_db(cfg)
    if not isinstance(db, MemoryDB):  # pragma: no cover (fresh process has empty store)
        print("note: fresh process store is empty; restore into a running gateway instead",
              file=sys.stderr)
    if args.cmd == "backup":
        print(_backup.backup_memory(db, args.dir))
    else:
        print(_backup.restore_memory(db, args.file))
    return 0


if __name__ == "__main__":
    sys.exit(main())
