"""Shared pure helpers: time, hashing, CSV safety, downsampling."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


def to_local_iso(ts_ms: int, tz_name: str = "Asia/Kolkata") -> str:
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=UTC).astimezone(ZoneInfo(tz_name))
    return dt.isoformat()


def canonical_bytes(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_chain(prev_hash: str, *parts: str) -> str:
    h = hashlib.sha256()
    h.update(prev_hash.encode())
    for p in parts:
        h.update(b"|")
        h.update(str(p).encode())
    return h.hexdigest()


def neutralize_csv_cell(value: object) -> object:
    """Prefix spreadsheet-formula triggers (SEC-04/FR-052). Numbers pass through."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def stride_downsample(points: list, max_points: int = 2000) -> list:
    """Deterministic stride decimation keeping first/last points. ponytail: no LTTB dep."""
    n = len(points)
    if n <= max_points or max_points < 2:
        return points
    stride = (n - 1) / (max_points - 1)
    idx = sorted({min(n - 1, round(i * stride)) for i in range(max_points)})
    return [points[j] for j in idx]


def fmt_float(v: float | None) -> str:
    if v is None:
        return ""
    s = f"{float(v):.6f}"
    return s.rstrip("0").rstrip(".") if "." in s else s
