"""Flask application factory. Handlers are thin; logic lives in modules.
v1 is monitor-only: no route issues commands (FR-008, SEC-12).
"""
from __future__ import annotations

import re

from flask import Flask, current_app, g, jsonify, request

from . import audit
from .auth.base import AuthError, auth_error_response, require_node, require_user
from .config import Config
from .db import get_db
from .health import health_status
from .ingest import apply_batch, validate_batch
from .poll import build_poll_response
from .util import now_ms


def csp_for(auth_mode: str) -> str:
    """Content-Security-Policy. Firebase origins (phone reCAPTCHA scripts and
    frames, Google identity APIs) are allowed only in firebase auth mode,
    per docs/07_SSD.md SEC-11. Dev mode keeps the strict self-only policy."""
    script = "'self'"
    extra = ""
    if auth_mode == "firebase":
        script += " https://www.google.com https://www.gstatic.com"
        extra = ("; frame-src 'self' https://www.google.com"
                 "; connect-src 'self' https://identitytoolkit.googleapis.com"
                 " https://securetoken.googleapis.com https://www.googleapis.com")
    return ("default-src 'self'; script-src " + script + "; object-src 'none'; "
            "base-uri 'self'; frame-ancestors 'none'" + extra)


def err(code: str, message: str, status: int, details: list | None = None):
    body = {"error": code, "message": message}
    if details is not None:
        body["details"] = details
    return jsonify(body), status


def create_app(cfg: Config | None = None, db=None) -> Flask:
    cfg = cfg or Config.from_env()
    app = Flask(__name__, static_folder="../static", static_url_path="/static")
    app.config["CEM_CONFIG"] = cfg
    store = db if db is not None else get_db(cfg)
    app.config["CEM_DB"] = store
    app.config["MAX_CONTENT_LENGTH"] = cfg.max_body_kb * 1024
    app.config["CEM_RATE"] = {}  # node_id -> [window_start_ms, count]
    if cfg.auth_mode == "dev" and cfg.dev_admin:
        from .util import now_ms as _now

        if store.get_user(cfg.dev_admin.lower()) is None:
            store.put_user({"email": cfg.dev_admin.lower(), "role": "admin",
                            "active": True, "created_ts": _now()})

    @app.after_request
    def _headers(resp):
        resp.headers["Content-Security-Policy"] = csp_for(
            current_app.config["CEM_CONFIG"].auth_mode)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        return resp

    @app.errorhandler(AuthError)
    def _auth_err(e):
        return auth_error_response(e)

    @app.errorhandler(413)
    def _too_big(e):
        return err("too_large", "request body exceeds limit", 413)

    @app.errorhandler(400)
    def _bad(e):
        return err("bad_request", "malformed request", 400)

    @app.errorhandler(404)
    def _nf(e):
        return err("not_found", "no such route", 404)

    @app.get("/healthz")
    def healthz():
        body, status = health_status(current_app.config["CEM_DB"])
        return jsonify(body), status

    def _rate_ok(node_id: str) -> bool:
        if cfg.ingest_rate_per_min <= 0:
            return True
        window = 60_000
        now = now_ms()
        bucket = app.config["CEM_RATE"].get(node_id)
        if bucket is None or now - bucket[0] >= window:
            app.config["CEM_RATE"][node_id] = [now, 1]
            return True
        if bucket[1] >= cfg.ingest_rate_per_min:
            return False
        bucket[1] += 1
        return True

    @app.post("/api/v1/ingest")
    @require_node
    def ingest():
        db = current_app.config["CEM_DB"]
        node = db.get_node(g.identity.id)
        if node is None:
            return err("unknown_node", "node not registered", 401)
        if node.get("status") == "disabled":
            return err("node_disabled", "node disabled", 403)
        if not _rate_ok(node["node_id"]):
            resp = err("rate_limited", "too many batches", 429)
            resp[0].headers["Retry-After"] = "60"
            return resp
        try:
            batch = request.get_json(force=True)
        except Exception as e:
            from werkzeug.exceptions import RequestEntityTooLarge

            if isinstance(e, RequestEntityTooLarge):
                raise
            return err("invalid_batch", "body must be JSON", 400, ["unparseable JSON"])
        body = batch if isinstance(batch, dict) else {}
        samples, events, errs = validate_batch(body, node["node_id"])
        if errs:
            return err("invalid_batch", "schema validation failed", 400, errs)
        resp = apply_batch(db, node, samples, events, batch["sent_ts"], now_ms(),
                             batch.get("fw_version"))
        return jsonify(resp), 200

    @app.get("/api/v1/poll")
    @require_node
    def poll():
        db = current_app.config["CEM_DB"]
        qid = request.args.get("node_id", "")
        if qid and qid != g.identity.id:
            return err("forbidden", "node mismatch", 403)
        node = db.get_node(g.identity.id)
        if node is None:
            return err("unknown_node", "node not registered", 401)
        if node.get("status") == "disabled":
            return err("node_disabled", "node disabled", 403)
        return jsonify(build_poll_response(db, node)), 200

    # ---- M2 read APIs (FR-030..032) ----
    @app.get("/api/v1/fleet")
    @require_user("viewer", "labeller", "admin")
    def fleet():
        from .api_read import fleet as _fleet

        return jsonify({"nodes": _fleet(current_app.config["CEM_DB"])}), 200

    def _range_args():
        try:
            frm = int(request.args.get("from", "0"))
            to = int(request.args.get("to", str(now_ms())))
            max_pts = min(int(request.args.get("max_points", "2000")), 5000)
        except ValueError:
            return None
        if frm < 0 or to <= frm:
            return None
        return frm, to, max_pts

    @app.get("/api/v1/nodes/<node_id>/readings")
    @require_user("viewer", "labeller", "admin")
    def readings(node_id):
        from .api_read import series as _series

        r = _range_args()
        if r is None:
            return err("bad_request", "from/to/max_points must be valid", 400)
        frm, to, max_pts = r
        if current_app.config["CEM_DB"].get_node(node_id) is None:
            return err("not_found", "unknown node", 404)
        return jsonify(_series(current_app.config["CEM_DB"], node_id, frm, to, max_pts)), 200

    @app.get("/api/v1/nodes/<node_id>/flags")
    @require_user("viewer", "labeller", "admin")
    def flags(node_id):
        r = _range_args()
        if r is None:
            return err("bad_request", "from/to must be valid", 400)
        frm, to, _ = r
        if current_app.config["CEM_DB"].get_node(node_id) is None:
            return err("not_found", "unknown node", 404)
        return jsonify({"flags": current_app.config["CEM_DB"].read_flags(node_id, frm, to)}), 200

    @app.get("/api/v1/nodes/<node_id>/events")
    @require_user("viewer", "labeller", "admin")
    def events(node_id):
        r = _range_args()
        if r is None:
            return err("bad_request", "from/to must be valid", 400)
        frm, to, _ = r
        if current_app.config["CEM_DB"].get_node(node_id) is None:
            return err("not_found", "unknown node", 404)
        return jsonify({"events": current_app.config["CEM_DB"].read_events(node_id, frm, to)}), 200

    # ---- M4 admin: nodes, users, audit (FR-010..013, FR-073, FR-080..082) ----
    @app.get("/api/v1/admin/nodes")
    @require_user("admin")
    def admin_nodes():
        return jsonify({"nodes": current_app.config["CEM_DB"].list_nodes()}), 200

    @app.post("/api/v1/admin/nodes")
    @require_user("admin")
    def admin_nodes_create():
        from . import nodes as _nodes

        db = current_app.config["CEM_DB"]
        body = request.get_json(silent=True) or {}
        try:
            node, token = _nodes.register_node(
                db, current_app.config["CEM_CONFIG"], body.get("node_id", ""),
                body.get("room_id", ""))
        except ValueError as e:
            return err("bad_request", str(e), 400)
        audit.record(db, g.identity.id, "node.register", node["node_id"],
                     str(body.get("room_id", "")), request.remote_addr or "")
        return jsonify({"node": node, "token": token}), 201

    @app.post("/api/v1/admin/nodes/<node_id>/rotate")
    @require_user("admin")
    def admin_nodes_rotate(node_id):
        from . import nodes as _nodes

        db = current_app.config["CEM_DB"]
        try:
            token = _nodes.rotate_node_token(db, current_app.config["CEM_CONFIG"], node_id)
        except ValueError as e:
            return err("not_found", str(e), 404)
        audit.record(db, g.identity.id, "node.rotate", node_id, "", request.remote_addr or "")
        return jsonify({"token": token}), 200

    @app.post("/api/v1/admin/nodes/<node_id>/status")
    @require_user("admin")
    def admin_nodes_status(node_id):
        from . import nodes as _nodes

        db = current_app.config["CEM_DB"]
        body = request.get_json(silent=True) or {}
        try:
            node = _nodes.set_node_status(db, node_id, body.get("status", ""))
        except ValueError as e:
            return err("bad_request", str(e), 400)
        audit.record(db, g.identity.id, "node.status", node_id,
                     body.get("status", ""), request.remote_addr or "")
        return jsonify({"node": node}), 200

    @app.post("/api/v1/admin/nodes/<node_id>/calibration")
    @require_user("admin")
    def admin_nodes_calib(node_id):
        from . import nodes as _nodes

        db = current_app.config["CEM_DB"]
        body = request.get_json(silent=True) or {}
        try:
            node = _nodes.set_calibration(db, node_id, body.get("calib", {}))
        except ValueError as e:
            return err("bad_request", str(e), 400)
        audit.record(db, g.identity.id, "node.calibrate", node_id, "",
                     request.remote_addr or "")
        return jsonify({"node": node}), 200

    @app.get("/api/v1/admin/users")
    @require_user("admin")
    def admin_users():
        return jsonify({"users": current_app.config["CEM_DB"].list_users()}), 200

    @app.post("/api/v1/admin/users")
    @require_user("admin")
    def admin_users_upsert():
        from .util import now_ms as _now

        db = current_app.config["CEM_DB"]
        body = request.get_json(silent=True) or {}
        email = str(body.get("email", "")).lower().strip()
        role = body.get("role", "viewer")
        if "@" not in email or role not in ("viewer", "labeller", "admin"):
            return err("bad_request", "email must contain @; role viewer|labeller|admin", 400)
        db.put_user({"email": email, "role": role, "active": True, "created_ts": _now()})
        audit.record(db, g.identity.id, "user.upsert", email, role, request.remote_addr or "")
        return jsonify({"user": db.get_user(email)}), 200

    @app.post("/api/v1/admin/users/<path:email>/deactivate")
    @require_user("admin")
    def admin_users_deactivate(email):
        from .util import now_ms as _now

        db = current_app.config["CEM_DB"]
        u = db.get_user(email.lower())
        if u is None:
            return err("not_found", "unknown user", 404)
        u["active"] = False
        u["created_ts"] = u.get("created_ts", _now())
        db.put_user(u)
        audit.record(db, g.identity.id, "user.deactivate", email, "", request.remote_addr or "")
        return jsonify({"user": u}), 200

    @app.get("/api/v1/admin/audit")
    @require_user("admin")
    def admin_audit():
        try:
            limit = min(int(request.args.get("limit", "200")), 1000)
        except ValueError:
            return err("bad_request", "limit must be an integer", 400)
        return jsonify({"entries": current_app.config["CEM_DB"].list_audit(limit)}), 200

    @app.post("/api/v1/admin/backup")
    @require_user("admin")
    def admin_backup():
        from . import backup as _backup

        db = current_app.config["CEM_DB"]
        if not hasattr(db, "snapshot"):
            return err("bad_request", "live backup needs a snapshot-capable backend", 400)
        info = _backup.backup_memory(db, current_app.config["CEM_CONFIG"].backup_dir)
        audit.record(db, g.identity.id, "backup.create", info["path"],
                     info["sha256"][:16], request.remote_addr or "")
        return jsonify(info), 201

    @app.post("/api/v1/admin/restore")
    @require_user("admin")
    def admin_restore():
        import os

        from . import backup as _backup

        db = current_app.config["CEM_DB"]
        body = request.get_json(silent=True) or {}
        name = os.path.basename(str(body.get("file", "")))
        if not name.endswith(".json"):
            return err("bad_request", "file must be a backup .json name", 400)
        base = os.path.realpath(current_app.config["CEM_CONFIG"].backup_dir)
        path = os.path.realpath(os.path.join(base, name))
        if not path.startswith(base + os.sep) or not os.path.isfile(path):
            return err("not_found", "unknown backup file", 404)
        try:
            info = _backup.restore_memory(db, path)
        except ValueError as e:
            return err("bad_request", str(e), 400)
        audit.record(db, g.identity.id, "backup.restore", path, "", request.remote_addr or "")
        return jsonify(info), 200

    # ---- M5 labelling, timetable, export (FR-040..053) ----
    @app.get("/api/v1/labels")
    @require_user("viewer", "labeller", "admin")
    def labels_list():
        from . import labels as _labels

        room = request.args.get("room")
        lbs = _labels.active_labels(current_app.config["CEM_DB"], room)
        return jsonify({"labels": lbs}), 200

    @app.post("/api/v1/labels")
    @require_user("labeller", "admin")
    def labels_create():
        from . import labels as _labels

        db = current_app.config["CEM_DB"]
        body = request.get_json(silent=True) or {}
        try:
            lb = _labels.create_label(
                db, body.get("room_id", ""), body.get("ts_start"), body.get("ts_end"),
                body.get("state", ""), body.get("source", ""),
                body.get("labeller", ""), body.get("note", ""))
        except (ValueError, TypeError) as e:
            return err("bad_request", str(e), 400)
        audit.record(db, g.identity.id, "label.create", lb["id"],
                     lb["room_id"], request.remote_addr or "")
        return jsonify({"label": lb}), 201

    @app.post("/api/v1/labels/<lid>/supersede")
    @require_user("labeller", "admin")
    def labels_supersede(lid):
        from . import labels as _labels

        db = current_app.config["CEM_DB"]
        body = request.get_json(silent=True) or {}
        allowed = {"room_id", "ts_start", "ts_end", "state", "source", "labeller", "note"}
        try:
            lb = _labels.supersede(db, lid, **{k: v for k, v in body.items() if k in allowed})
        except (ValueError, TypeError) as e:
            return err("bad_request", str(e), 400)
        audit.record(db, g.identity.id, "label.supersede", lid,
                     lb["id"], request.remote_addr or "")
        return jsonify({"label": lb}), 200

    @app.get("/api/v1/labels/conflicts")
    @require_user("viewer", "labeller", "admin")
    def labels_conflicts():
        from . import labels as _labels

        return jsonify({"conflicts": _labels.conflicts(
            current_app.config["CEM_DB"], request.args.get("room"))}), 200

    @app.get("/api/v1/labels/coverage")
    @require_user("viewer", "labeller", "admin")
    def labels_coverage():
        from . import labels as _labels

        return jsonify({"coverage": _labels.coverage(current_app.config["CEM_DB"])}), 200

    @app.post("/api/v1/timetable/import")
    @require_user("admin")
    def timetable_import():
        from . import timetable as _tt

        db = current_app.config["CEM_DB"]
        body = request.get_json(silent=True) or {}
        room = str(body.get("room_id", "")).strip()
        if not room:
            return err("bad_request", "room_id required", 400)
        try:
            entries = _tt.import_timetable(db, room, body.get("csv", ""))
        except ValueError as e:
            return err("bad_request", str(e), 400)
        audit.record(db, g.identity.id, "timetable.import", room,
                     f"{len(entries)} entries", request.remote_addr or "")
        return jsonify({"entries": len(entries)}), 200

    @app.get("/api/v1/timetable")
    @require_user("viewer", "labeller", "admin")
    def timetable_list():
        return jsonify({"entries": current_app.config["CEM_DB"].list_timetable(
            request.args.get("room"))}), 200

    @app.post("/api/v1/export")
    @require_user("viewer", "labeller", "admin")
    def export_create():
        import os

        from . import export as _export
        from .flags.rules import load_rules

        db = current_app.config["CEM_DB"]
        cfg = current_app.config["CEM_CONFIG"]
        body = request.get_json(silent=True) or {}
        rooms = body.get("rooms")
        if not isinstance(rooms, list) or not rooms:
            return err("bad_request", "rooms must be a non-empty list", 400)
        try:
            frm, to = int(body.get("from", 0)), int(body.get("to", 0))
            assert to > frm
        except (ValueError, AssertionError, TypeError):
            return err("bad_request", "from/to must be valid range", 400)
        rv = load_rules(cfg.flag_rules_file).get("rule_version", 1)
        eid, blob, manifest = _export.build_export(
            db, rooms, frm, to, g.identity.id, cfg.display_tz, rv)
        os.makedirs(os.path.abspath(cfg.export_dir), exist_ok=True)
        with open(os.path.join(os.path.abspath(cfg.export_dir), eid + ".zip"),
                  "wb") as fh:
            fh.write(blob)
        db.put_export({"id": eid, "created_ts": manifest["created_ts"],
                       "by": g.identity.id, "manifest": manifest})
        audit.record(db, g.identity.id, "export.create", eid,
                     ",".join(sorted(rooms)), request.remote_addr or "")
        return jsonify({"export_id": eid, "manifest": manifest}), 201

    @app.get("/api/v1/export/<eid>")
    @require_user("viewer", "labeller", "admin")
    def export_get(eid):
        import os

        from flask import send_file

        if not re_fullmatch_eid(eid):
            return err("bad_request", "bad export id", 400)
        cfg = current_app.config["CEM_CONFIG"]
        path = os.path.join(os.path.abspath(cfg.export_dir), eid + ".zip")
        if not os.path.isfile(path):
            return err("not_found", "unknown export", 404)
        return send_file(path, mimetype="application/zip", as_attachment=True,
                         download_name=f"cem-export-{eid}.zip")

    # ---- M6 evaluation (FR-060..066) ----
    @app.post("/api/v1/eval/runs")
    @require_user("admin")
    def eval_create():
        from .evaluation import runner as _runner
        from .flags.rules import load_rules

        db = current_app.config["CEM_DB"]
        cfg = current_app.config["CEM_CONFIG"]
        body = request.get_json(silent=True) or {}
        rooms = body.get("rooms")
        if not isinstance(rooms, list) or not rooms:
            return err("bad_request", "rooms must be a non-empty list", 400)
        try:
            params = {"rooms": rooms, "from": int(body.get("from", 0)),
                      "to": int(body.get("to", 0)),
                      "configs": body.get("configs", ["pir_only", "pir_mmwave",
                                                      "pir_co2", "pir_timetable", "all"]),
                      "holds": body.get("holds", [2, 5, 10, 15, 20, 30]),
                      "seed": int(body.get("seed", 1)),
                      "bootstrap_reps": min(int(body.get("bootstrap_reps", 200)), 5000)}
            assert params["to"] > params["from"]
        except (ValueError, AssertionError, TypeError):
            return err("bad_request", "invalid eval params", 400)
        rv = load_rules(cfg.flag_rules_file).get("rule_version", 1)
        run = _runner.run_async(db, cfg, params, g.identity.id, rv)
        audit.record(db, g.identity.id, "eval.create", run["id"],
                     ",".join(sorted(rooms)), request.remote_addr or "")
        return jsonify({"run": run}), 202

    @app.get("/api/v1/eval/runs")
    @require_user("viewer", "labeller", "admin")
    def eval_list():
        runs = current_app.config["CEM_DB"].list_runs()
        slim = [{k: r.get(k) for k in ("id", "created_ts", "created_by", "status",
                "params", "rule_version", "code_version", "data_hash")} for r in runs]
        return jsonify({"runs": slim}), 200

    @app.get("/api/v1/eval/runs/<rid>")
    @require_user("viewer", "labeller", "admin")
    def eval_get(rid):
        if not re.fullmatch(r"[0-9a-f]{16}", rid or ""):
            return err("bad_request", "bad run id", 400)
        run = current_app.config["CEM_DB"].get_run(rid)
        if run is None:
            return err("not_found", "unknown run", 404)
        return jsonify({"run": run}), 200

    # ---- pages (plain HTML, no build step; scripts are local files per CSP) ----
    @app.get("/")
    def index_page():
        return current_app.send_static_file("index.html")

    @app.get("/login")
    def login_page():
        return current_app.send_static_file("login.html")

    @app.get("/fleet")
    def fleet_page():
        return current_app.send_static_file("fleet.html")

    @app.get("/node")
    def node_page():
        return current_app.send_static_file("node.html")

    @app.get("/label")
    def label_page():
        return current_app.send_static_file("label.html")

    @app.get("/export")
    def export_page():
        return current_app.send_static_file("export.html")

    @app.get("/admin")
    def admin_page():
        return current_app.send_static_file("admin.html")

    @app.get("/eval")
    def eval_page():
        return current_app.send_static_file("eval.html")

    return app


def re_fullmatch_eid(eid: str) -> bool:
    return re.fullmatch(r"[0-9a-f]{16}", eid or "") is not None
