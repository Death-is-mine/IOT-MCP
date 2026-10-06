"""M5 tests: labels, timetable, export. TC-LB-01..05, TC-EX-01..04."""
from __future__ import annotations

import io
import json
import zipfile

from tests.conftest import NODE, ROOM, batch, node_hdr, user_hdr

ADMIN = user_hdr("admin@x.test")
LAB = user_hdr("lab@x.test")
VIEW = user_hdr("view@x.test")
T0 = 1_760_000_000_000


def mklabel(room=ROOM, s=T0, e=T0 + 600_000, state="occupied", source="spot_check",
            labeller="SS", note=""):
    return {"room_id": room, "ts_start": s, "ts_end": e, "state": state,
            "source": source, "labeller": labeller, "note": note}


def test_tc_lb_01_create_validation(client):
    """TC-LB-01/FR-040: label validation."""
    assert client.post("/api/v1/labels", json=mklabel(), headers=LAB).status_code == 201
    bad = dict(mklabel(), state="maybe")
    assert client.post("/api/v1/labels", json=bad, headers=LAB).status_code == 400
    bad = dict(mklabel(), ts_start=T0 + 1, ts_end=T0)
    assert client.post("/api/v1/labels", json=bad, headers=LAB).status_code == 400
    bad = dict(mklabel(), note="x" * 141)
    assert client.post("/api/v1/labels", json=bad, headers=LAB).status_code == 400
    assert client.post("/api/v1/labels", json=mklabel(), headers=VIEW).status_code == 403


def test_tc_lb_02_immutable_supersede(client, db):
    """TC-LB-02/FR-041: no edit path; supersede links old->new."""
    lid = client.post("/api/v1/labels", json=mklabel(), headers=LAB).get_json()["label"]["id"]
    r = client.post(f"/api/v1/labels/{lid}/supersede", json={"state": "vacant"}, headers=LAB)
    assert r.status_code == 200
    new = r.get_json()["label"]
    assert new["state"] == "vacant" and new["id"] != lid
    assert db.get_label(lid)["superseded_by"] == new["id"]
    assert client.post(f"/api/v1/labels/{lid}/supersede", json={}, headers=LAB).status_code == 400
    # superseded label hidden from listings
    ids = {lb["id"] for lb in client.get("/api/v1/labels", headers=VIEW).get_json()["labels"]}
    assert lid not in ids and new["id"] in ids


def test_tc_lb_03_conflicts(client):
    """TC-LB-03/FR-042: conflicting overlaps listed."""
    client.post("/api/v1/labels", json=mklabel(state="occupied"), headers=LAB)
    client.post("/api/v1/labels", json=mklabel(s=T0 + 300_000, e=T0 + 900_000, state="vacant"),
                headers=LAB)
    c = client.get("/api/v1/labels/conflicts", headers=VIEW).get_json()["conflicts"]
    assert len(c) == 1 and c[0]["overlap_start"] == T0 + 300_000
    # unsure never conflicts
    client.post("/api/v1/labels", json=mklabel(state="unsure"), headers=ADMIN)
    c2 = client.get("/api/v1/labels/conflicts", headers=VIEW).get_json()["conflicts"]
    assert len(c2) == 1


def test_tc_lb_04_coverage(client):
    """TC-LB-04/FR-043: coverage equals hand-computed hours."""
    client.post("/api/v1/labels", json=mklabel(e=T0 + 3_600_000, state="occupied"), headers=LAB)
    client.post("/api/v1/labels", json=mklabel(s=T0 + 3_600_000, e=T0 + 5_400_000, state="vacant"),
                headers=LAB)
    cov = { (c["room_id"], c["state"]): c["hours"]
            for c in client.get("/api/v1/labels/coverage", headers=VIEW).get_json()["coverage"]}
    assert cov[(ROOM, "occupied")] == 1.0 and cov[(ROOM, "vacant")] == 0.5


def test_tc_lb_05_timetable(client):
    """TC-LB-05/FR-044: valid import; malformed; instructor column rejected."""
    good = "room,weekday,start,end,course_code\nr,1,09:00,10:00,CS101\n"
    r = client.post("/api/v1/timetable/import", json={"room_id": "r", "csv": good}, headers=ADMIN)
    assert r.status_code == 200 and r.get_json()["entries"] == 1
    bad = "room,weekday,start,end\nr,9,09:00,10:00\n"
    assert client.post("/api/v1/timetable/import", json={"room_id": "r", "csv": bad},
                       headers=ADMIN).status_code == 400
    evil = "room,weekday,start,end,instructor\nr,1,09:00,10:00,Dr X\n"
    r = client.post("/api/v1/timetable/import", json={"room_id": "r", "csv": evil}, headers=ADMIN)
    assert r.status_code == 400
    assert client.post("/api/v1/timetable/import", json={"room_id": "r", "csv": good},
                       headers=LAB).status_code == 403


def seed_samples(client):
    b = batch(seqs=(1, 2), ts0=T0)
    assert client.post("/api/v1/ingest", json=b, headers=node_hdr()).status_code == 200


def do_export(client):
    seed_samples(client)
    client.post("/api/v1/labels", json=mklabel(), headers=LAB)
    r = client.post("/api/v1/export", json={"rooms": [ROOM], "from": 0, "to": T0 + 10_000_000},
                    headers=VIEW)
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def test_tc_ex_01_join_and_manifest(client, db):
    """TC-EX-01/02: CSV joins readings+labels; manifest hash matches (FR-050/051)."""
    from cem_gw.flags import engine
    from cem_gw.flags.rules import DEFAULTS

    out = do_export(client)
    engine.run_node(db, db.get_node(NODE), dict(DEFAULTS), T0 + 60_000)
    eid = client.post("/api/v1/export", json={"rooms": [ROOM], "from": 0, "to": T0 + 10_000_000},
                      headers=VIEW).get_json()["export_id"]
    raw = client.get(f"/api/v1/export/{eid}", headers=VIEW).data
    z = zipfile.ZipFile(io.BytesIO(raw))
    assert set(z.namelist()) == {"data.csv", "manifest.json", "data_dictionary.md"}
    csv_data = z.read("data.csv")
    manifest = json.loads(z.read("manifest.json"))
    import hashlib

    assert manifest["sha256_data_csv"] == hashlib.sha256(csv_data).hexdigest()
    assert manifest["gateway_code_version"] and manifest["flag_rule_version"] == 1
    text = csv_data.decode()
    assert "occupied" in text and "spot_check" in text
    assert out  # first export (pre-flags) also succeeded


def test_tc_ex_03_formula_neutralised():
    """TC-EX-03/FR-052 + SEC-08: formula cells prefixed."""
    from cem_gw.util import neutralize_csv_cell

    assert neutralize_csv_cell("=cmd|'/c calc'!A0") == "'=cmd|'/c calc'!A0"
    assert neutralize_csv_cell("@x") == "'@x"
    assert neutralize_csv_cell(1.5) == 1.5 and neutralize_csv_cell("plain") == "plain"


def test_tc_ex_04_deterministic(client):
    """TC-EX-04/FR-053: same params twice -> identical bytes."""
    do_export(client)
    body = {"rooms": [ROOM], "from": 0, "to": T0 + 10_000_000}
    a = client.post("/api/v1/export", json=body, headers=VIEW).get_json()["export_id"]
    # reset export ids are random; determinism is about the CSV bytes
    raw_a = client.get(f"/api/v1/export/{a}", headers=VIEW).data
    za = zipfile.ZipFile(io.BytesIO(raw_a)).read("data.csv")
    b = client.post("/api/v1/export", json=body, headers=VIEW).get_json()["export_id"]
    raw_b = client.get(f"/api/v1/export/{b}", headers=VIEW).data
    zb = zipfile.ZipFile(io.BytesIO(raw_b)).read("data.csv")
    assert za == zb


def test_tc_ex_05_relative_export_dir_roundtrip(tmp_path, monkeypatch):
    """TC-EX-05/FR-050: relative CEM_EXPORT_DIR (the prod-default shape)
    writes and serves the zip from the same directory (walkthrough found
    POST/GET disagreeing on cwd vs Flask root_path)."""
    from cem_gw import create_app
    from cem_gw.config import Config
    from cem_gw.db import MemoryDB
    from tests.conftest import SECRET

    monkeypatch.chdir(tmp_path)
    cfg = Config.from_env(
        {
            "CEM_DB_MODE": "memory",
            "CEM_AUTH_MODE": "dev",
            "CEM_CONTROL_ENABLED": "false",
            "CEM_DEV_SECRET": SECRET,
            "CEM_EXPORT_DIR": "./var/exports",
        }
    )
    db = MemoryDB()
    db.put_node({"node_id": NODE, "room_id": ROOM})
    db.put_user({"email": "view@x.test", "role": "viewer", "active": True,
                 "created_ts": T0})
    client = create_app(cfg, db).test_client()
    body = {"rooms": [ROOM], "from": 0, "to": T0 + 10_000_000}
    eid = client.post("/api/v1/export", json=body, headers=VIEW).get_json()["export_id"]
    r = client.get(f"/api/v1/export/{eid}", headers=VIEW)
    assert r.status_code == 200, r.get_json() if r.is_json else r.data[:200]
    assert r.data[:2] == b"PK"
