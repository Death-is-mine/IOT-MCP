"""M3/UI tests: node page, vendor integrity, no-CDN, aligned series.
TC-UI-02/03/05."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

STATIC = Path("static")
# Recorded at vendor time; changing uPlot requires updating docs/MEMORY.md.
UPLOT_JS_SHA = "19c8d4c6ad88929a79f4ae49d6f7161566dfd0ba3d15cc495e974f787eb78f1f"
UPLOT_CSS_SHA = "df630c6a8d6f8eeaff264b50f73ce5b114f646ffd9a0bb74f049b0a00135fa04"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_tc_ui_05_vendor_hash_and_no_cdn():
    """TC-UI-05/FR-035/NFR-005: local vendor files pinned; no runtime CDN."""
    assert sha(STATIC / "vendor" / "uPlot.iife.min.js") == UPLOT_JS_SHA
    assert sha(STATIC / "vendor" / "uPlot.min.css") == UPLOT_CSS_SHA
    assert not (STATIC / "package.json").exists()
    for p in list(STATIC.glob("*.html")) + list(STATIC.glob("*.js")):
        text = p.read_text(encoding="utf-8")
        assert not re.search(r'https?://', text), f"external URL in {p}"
        for tag in re.findall(r"<script[^>]*>", text):
            assert "src=" in tag, f"inline script in {p}: {tag}"
        assert "<style" not in text and "onclick=" not in text, f"inline code in {p}"


def test_tc_ui_02_pages_and_series_alignment(client):
    """TC-UI-02/FR-031: pages serve; series share one x grid; flags+events ride along."""
    from tests.conftest import NODE, batch, node_hdr, user_hdr

    for path in ("/", "/fleet", "/node", "/admin"):
        r = client.get(path)
        assert r.status_code == 200 and "text/html" in r.content_type
    b = batch(seqs=(1, 2, 3))
    b["events"] = [{"eseq": 1, "ts": b["samples"][0]["ts"], "type": "would_cut",
                    "payload": {"hold_s": 600, "config": "pir_only"}}]
    assert client.post("/api/v1/ingest", json=b, headers=node_hdr()).status_code == 200
    import time

    now = int(time.time() * 1000)
    d = client.get(f"/api/v1/nodes/{NODE}/readings?from=0&to={now}",
                   headers=user_hdr("view@x.test")).get_json()
    xs = [p[0] for p in d["series"]["power_w"]]
    assert len(xs) == 3
    for f, pts in d["series"].items():
        assert [p[0] for p in pts] == xs, f
    assert any(e["type"] == "would_cut" for e in d["events"])  # FR-033 markers
    assert isinstance(d["flags"], list)


def test_tc_ui_03_shown_lte_2000(client, db):
    import time

    from cem_gw.util import now_ms
    from tests.conftest import NODE, node_hdr, user_hdr

    end = now_ms()
    base = end - 5000 * 5000
    for k in range(25):  # 25 x 200 = 5000 samples (> 2000 cap)
        chunk = [{"seq": k * 200 + i + 1, "ts": base + (k * 200 + i) * 5000,
                  "current_a": 1.0, "power_w": 200.0, "pir": 1, "load_state": 1}
                 for i in range(200)]
        r = client.post("/api/v1/ingest", json={
            "schema_version": 1, "node_id": NODE, "fw_version": "x", "batch_id": f"b{k}",
            "sent_ts": end, "time_synced": True, "samples": chunk, "events": []},
            headers=node_hdr())
        assert r.status_code == 200
    now = int(time.time() * 1000)
    d = client.get(f"/api/v1/nodes/{NODE}/readings?from=0&to={now}&max_points=2000",
                   headers=user_hdr("view@x.test")).get_json()
    assert d["count"] == 5000 and d["shown"] <= 2000
    assert all(len(pts) <= 2000 for pts in d["series"].values())
