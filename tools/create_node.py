"""Register a node via the admin API. Prints the one-time node token.

Usage:
  python tools/create_node.py --gateway http://127.0.0.1:8080 \\
      --admin-token <admin-bearer> --node-id cem-204-a --room room-204
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Register a CEM node")
    ap.add_argument("--gateway", default="http://127.0.0.1:8080")
    ap.add_argument("--admin-token", required=True)
    ap.add_argument("--node-id", required=True)
    ap.add_argument("--room", required=True)
    args = ap.parse_args(argv)
    body = json.dumps({"node_id": args.node_id, "room_id": args.room}).encode()
    req = urllib.request.Request(
        args.gateway.rstrip("/") + "/api/v1/admin/nodes", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {args.admin_token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            out = json.load(resp)
    except urllib.error.HTTPError as e:
        print(f"register failed: HTTP {e.code} {e.read().decode()[:500]}", file=sys.stderr)
        return 1
    print(f"node: {out['node']['node_id']}  room: {out['node']['room_id']}")
    print(f"ONE-TIME NODE TOKEN (store on the node, it is never shown again):\n{out['token']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
