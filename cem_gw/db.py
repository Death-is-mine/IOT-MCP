"""Datastore abstraction. Firestore is the production backend (DECIDED ADR-013);
`memory` is a same-interface backend for local dev/tests until the Firebase
project exists (DEFAULT D-018, reversible).

Security: Firestore impl uses SDK document references only — never
string-built queries (AGENTS.md hard rule). Memory impl keeps no update/delete
for audit/labels so append-only/immutable holds in both backends.
"""
from __future__ import annotations

import threading
import uuid

from .config import Config


class DBError(Exception):
    pass


# ---------------------------------------------------------------- MemoryDB
class MemoryDB:
    """Thread-safe in-memory store with the production method set."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.nodes: dict[str, dict] = {}
        self.samples: dict[str, dict[int, dict]] = {}
        self.events: dict[str, dict[int, dict]] = {}
        self.flags: dict[str, dict] = {}
        self.watermarks: dict[str, dict] = {}
        self.labels: dict[str, dict] = {}
        self.timetable: dict[str, dict] = {}
        self.users: dict[str, dict] = {}
        self.audit: dict[str, dict] = {}
        self.audit_head: str = "GENESIS"
        self.runs: dict[str, dict] = {}
        self.kv: dict[str, dict] = {}

    # -- nodes
    def get_node(self, node_id: str) -> dict | None:
        with self._lock:
            n = self.nodes.get(node_id)
            return dict(n) if n else None

    def put_node(self, node: dict) -> None:
        with self._lock:
            self.nodes[node["node_id"]] = dict(node)

    def list_nodes(self) -> list[dict]:
        with self._lock:
            return [dict(n) for n in self.nodes.values()]

    def update_node(self, node_id: str, patch: dict) -> dict | None:
        with self._lock:
            n = self.nodes.get(node_id)
            if n is None:
                return None
            n.update(patch)
            return dict(n)

    # -- samples / events (idempotent on seq/eseq; atomic per batch)
    def write_batch(
        self, node_id: str, samples: list[dict], events: list[dict]
    ) -> tuple[int, int, int | None]:
        """Store new samples/events. Returns (accepted, duplicates, last_seq).

        Two-phase under one lock with rollback: an exception part-way leaves
        no partial batch (NFR-003 unit half; crash half is a prod TC-ING-10).
        """
        with self._lock:
            store = self.samples.setdefault(node_id, {})
            evstore = self.events.setdefault(node_id, {})
            added_s, added_e = [], []
            accepted, dups = 0, 0
            try:
                for s in samples:
                    if s["seq"] in store:
                        dups += 1
                    else:
                        store[s["seq"]] = dict(s)
                        added_s.append(s["seq"])
                        accepted += 1
                for e in events:
                    if e["eseq"] in evstore:
                        dups += 1
                    else:
                        evstore[e["eseq"]] = dict(e)
                        added_e.append(e["eseq"])
                        accepted += 1
            except Exception:
                for k in added_s:
                    store.pop(k, None)
                for k in added_e:
                    evstore.pop(k, None)
                raise
            last = max(store.keys()) if store else None
            return accepted, dups, last

    def has_seq(self, node_id: str, seq: int) -> bool:
        with self._lock:
            return seq in self.samples.get(node_id, {})

    def read_samples(
        self, node_id: str, frm: int | None = None, to: int | None = None
    ) -> list[dict]:
        with self._lock:
            out = [
                dict(s)
                for s in self.samples.get(node_id, {}).values()
                if (frm is None or s["ts"] >= frm) and (to is None or s["ts"] <= to)
            ]
        return sorted(out, key=lambda s: s["ts"])

    def read_events(self, node_id: str, frm: int | None = None,
                      to: int | None = None) -> list[dict]:
        with self._lock:
            out = [
                dict(e)
                for e in self.events.get(node_id, {}).values()
                if (frm is None or e["ts"] >= frm) and (to is None or e["ts"] <= to)
            ]
        return sorted(out, key=lambda e: e["ts"])

    # -- flags
    def write_flags(self, flags: list[dict]) -> list[str]:
        with self._lock:
            ids = []
            for f in flags:
                fid = f.get("id") or uuid.uuid4().hex[:16]
                f = dict(f, id=fid)
                self.flags[fid] = f
                ids.append(fid)
            return ids

    def read_flags(self, node_id: str, frm: int | None = None, to: int | None = None) -> list[dict]:
        with self._lock:
            out = [
                dict(f)
                for f in self.flags.values()
                if f["node_id"] == node_id
                and (frm is None or f["ts_end"] >= frm)
                and (to is None or f["ts_start"] <= to)
            ]
        return sorted(out, key=lambda f: (f["ts_start"], f["ts_end"]))

    def get_watermark(self, key: str) -> dict | None:
        with self._lock:
            w = self.watermarks.get(key)
            return dict(w) if w else None

    def set_watermark(self, key: str, doc: dict) -> None:
        with self._lock:
            self.watermarks[key] = dict(doc)

    # -- labels (immutable; supersede only)
    def put_label(self, label: dict) -> None:
        with self._lock:
            self.labels[label["id"]] = dict(label)

    def get_label(self, lid: str) -> dict | None:
        with self._lock:
            lb = self.labels.get(lid)
            return dict(lb) if lb else None

    def mark_superseded(self, lid: str, new_id: str) -> bool:
        with self._lock:
            lb = self.labels.get(lid)
            if lb is None or lb.get("superseded_by"):
                return False
            lb["superseded_by"] = new_id
            return True

    def list_labels(self, room_id: str | None = None) -> list[dict]:
        with self._lock:
            rooms = [dict(lb) for lb in self.labels.values()]
            out = [lb for lb in rooms if room_id is None or lb["room_id"] == room_id]
        return sorted(out, key=lambda lb: (lb["ts_start"], lb["ts_end"]))

    # -- timetable
    def replace_timetable(self, room_id: str, entries: list[dict]) -> None:
        with self._lock:
            self.timetable = {k: v for k, v in self.timetable.items() if v["room_id"] != room_id}
            for en in entries:
                self.timetable[en["id"]] = dict(en)

    def list_timetable(self, room_id: str | None = None) -> list[dict]:
        with self._lock:
            return [
                dict(e)
                for e in self.timetable.values()
                if room_id is None or e["room_id"] == room_id
            ]

    # -- users
    def get_user(self, email: str) -> dict | None:
        with self._lock:
            u = self.users.get(email.lower())
            return dict(u) if u else None

    def put_user(self, user: dict) -> None:
        with self._lock:
            self.users[user["email"].lower()] = dict(user)

    def list_users(self) -> list[dict]:
        with self._lock:
            return [dict(u) for u in self.users.values()]

    # -- audit (append-only: no update/delete methods exist)
    def append_audit(self, entry: dict) -> str:
        from .util import hash_chain

        with self._lock:
            aid = entry.get("id") or uuid.uuid4().hex[:16]
            prev = self.audit_head
            row = hash_chain(
                prev,
                str(entry["ts"]),
                entry["actor"],
                entry["action"],
                entry.get("target", ""),
                entry.get("detail", ""),
            )
            self.audit[aid] = dict(entry, id=aid, prev_hash=prev, row_hash=row)
            self.audit_head = row
            return aid

    def list_audit(self, limit: int = 200) -> list[dict]:
        with self._lock:
            out = sorted(self.audit.values(), key=lambda a: a["ts"], reverse=True)
            return [dict(a) for a in out[:limit]]

    def verify_audit_chain(self) -> bool:
        from .util import hash_chain

        with self._lock:
            ordered = sorted(self.audit.values(), key=lambda a: a["ts"])
            prev = "GENESIS"
            for a in ordered:
                if a["prev_hash"] != prev:
                    return False
                expect = hash_chain(prev, str(a["ts"]), a["actor"], a["action"],
                                    a.get("target", ""), a.get("detail", ""))
                if a["row_hash"] != expect:
                    return False
                prev = a["row_hash"]
            return True

    # -- eval runs
    def put_run(self, run: dict) -> None:
        with self._lock:
            self.runs[run["id"]] = dict(run)

    def get_run(self, rid: str) -> dict | None:
        with self._lock:
            r = self.runs.get(rid)
            return dict(r) if r else None

    def list_runs(self) -> list[dict]:
        with self._lock:
            return sorted(
                (dict(r) for r in self.runs.values()), key=lambda r: r["created_ts"], reverse=True
            )

    # -- exports metadata
    def put_export(self, meta: dict) -> None:
        with self._lock:
            self.kv["export:" + meta["id"]] = dict(meta)

    def get_export(self, eid: str) -> dict | None:
        with self._lock:
            m = self.kv.get("export:" + eid)
            return dict(m) if m else None

    # -- generic kv (runtime config)
    def kv_get(self, key: str) -> dict | None:
        with self._lock:
            v = self.kv.get(key)
            return dict(v) if v else None

    def kv_set(self, key: str, doc: dict) -> None:
        with self._lock:
            self.kv[key] = dict(doc)

    # -- snapshot for backup (memory mode)
    def snapshot(self) -> dict:
        with self._lock:
            return {
                "nodes": self.nodes,
                "samples": {k: {str(s): v for s, v in d.items()} for k, d in self.samples.items()},
                "events": {k: {str(s): v for s, v in d.items()} for k, d in self.events.items()},
                "flags": self.flags,
                "watermarks": self.watermarks,
                "labels": self.labels,
                "timetable": self.timetable,
                "users": self.users,
                "audit": self.audit,
                "audit_head": self.audit_head,
                "runs": self.runs,
                "kv": self.kv,
            }

    def restore(self, snap: dict) -> None:
        with self._lock:
            self.nodes = snap.get("nodes", {})
            self.samples = {
                k: {int(s): v for s, v in d.items()} for k, d in snap.get("samples", {}).items()
            }
            self.events = {
                k: {int(s): v for s, v in d.items()} for k, d in snap.get("events", {}).items()
            }
            self.flags = snap.get("flags", {})
            self.watermarks = snap.get("watermarks", {})
            self.labels = snap.get("labels", {})
            self.timetable = snap.get("timetable", {})
            self.users = snap.get("users", {})
            self.audit = snap.get("audit", {})
            self.audit_head = snap.get("audit_head", "GENESIS")
            self.runs = snap.get("runs", {})
            self.kv = snap.get("kv", {})


# ------------------------------------------------------------ FirestoreDB
class FirestoreDB:
    """Production backend. Same method set as MemoryDB, backed by Firestore.

    Collection layout per docs/03_TRD.md section 4. Document IDs are seq/eseq
    (idempotent writes via transaction), never string-built queries.
    Requires the Firestore emulator or real credentials; import is lazy so
    tests and memory-mode runs never need firebase-admin installed.
    """

    def __init__(self, cfg: Config) -> None:
        try:
            import firebase_admin  # noqa: F401
            from firebase_admin import credentials, firestore, initialize_app
        except ImportError as e:
            raise DBError(
                "firebase-admin is required for CEM_DB_MODE=firestore "
                "(pip install -r requirements.txt, or use CEM_DB_MODE=memory for dev)"
            ) from e
        opts = {"projectId": cfg.firebase_project_id}
        if cfg.service_account_json:
            cred = credentials.Certificate(cfg.service_account_json)
            try:
                self._app = initialize_app(cred, opts, name="cem")
            except ValueError:
                self._app = firebase_admin.get_app("cem")
        else:
            # Emulator or environment-provided credentials.
            try:
                self._app = initialize_app(options=opts, name="cem")
            except ValueError:
                self._app = firebase_admin.get_app("cem")
        import os as _os

        try:
            self._db = firestore.client(app=self._app)
            # Force credential resolution now so a missing key fails fast
            # with our message instead of a traceback on first request.
            self._db.collection("nodes").limit(0).get()
        except Exception as e:
            if not cfg.service_account_json and not _os.environ.get("FIRESTORE_EMULATOR_HOST"):
                raise DBError(
                    "No Firebase credentials: set FIREBASE_SERVICE_ACCOUNT_JSON "
                    "to your service-account key file (kept outside the repo), "
                    "or point FIRESTORE_EMULATOR_HOST at the emulator, "
                    "or run the dev seam CEM_DB_MODE=memory for local use."
                ) from e
            raise

    # -- nodes
    def get_node(self, node_id: str) -> dict | None:
        snap = self._db.collection("nodes").document(node_id).get()
        return snap.to_dict() if snap.exists else None

    def put_node(self, node: dict) -> None:
        self._db.collection("nodes").document(node["node_id"]).set(dict(node))

    def list_nodes(self) -> list[dict]:
        return [d.to_dict() for d in self._db.collection("nodes").stream()]

    def update_node(self, node_id: str, patch: dict) -> dict | None:
        ref = self._db.collection("nodes").document(node_id)
        if not ref.get().exists:
            return None
        ref.update(dict(patch))
        return ref.get().to_dict()

    # -- samples / events
    def write_batch(
        self, node_id: str, samples: list[dict], events: list[dict]
    ) -> tuple[int, int, int | None]:

        sref = self._db.collection("readings").document(node_id).collection("samples")
        eref = self._db.collection("events").document(node_id).collection("entries")
        accepted, dups = 0, 0

        @self._db.transactional
        def _txn(txn):
            nonlocal accepted, dups
            for s in samples:
                if txn.get(sref.document(str(s["seq"]))).exists:
                    dups += 1
                else:
                    txn.set(sref.document(str(s["seq"])), dict(s))
                    accepted += 1
            for e in events:
                if txn.get(eref.document(str(e["eseq"]))).exists:
                    dups += 1
                else:
                    txn.set(eref.document(str(e["eseq"])), dict(e))
                    accepted += 1

        _txn(self._db.transaction())
        last = self._last_seq(node_id)
        return accepted, dups, last

    def _last_seq(self, node_id: str) -> int | None:
        q = (
            self._db.collection("readings")
            .document(node_id)
            .collection("samples")
            .order_by("__name__", direction="DESCENDING")
            .limit(1)
        )
        docs = list(q.stream())
        return int(docs[0].id) if docs else None

    def has_seq(self, node_id: str, seq: int) -> bool:
        return (
            self._db.collection("readings")
            .document(node_id)
            .collection("samples")
            .document(str(seq))
            .get()
            .exists
        )

    def read_samples(
        self, node_id: str, frm: int | None = None, to: int | None = None
    ) -> list[dict]:
        q = self._db.collection("readings").document(node_id).collection("samples")
        if frm is not None:
            q = q.where("ts", ">=", frm)
        if to is not None:
            q = q.where("ts", "<=", to)
        out = [d.to_dict() for d in q.order_by("ts").stream()]
        return sorted(out, key=lambda s: s["ts"])

    def read_events(self, node_id: str, frm: int | None = None,
                      to: int | None = None) -> list[dict]:
        q = self._db.collection("events").document(node_id).collection("entries")
        if frm is not None:
            q = q.where("ts", ">=", frm)
        if to is not None:
            q = q.where("ts", "<=", to)
        return sorted(
            [d.to_dict() for d in q.order_by("ts").stream()], key=lambda e: e["ts"]
        )

    # -- flags
    def write_flags(self, flags: list[dict]) -> list[str]:
        import uuid as _uuid

        ids = []
        batch = self._db.batch()
        for f in flags:
            fid = f.get("id") or _uuid.uuid4().hex[:16]
            batch.set(self._db.collection("flags").document(fid), dict(f, id=fid))
            ids.append(fid)
        batch.commit()
        return ids

    def read_flags(self, node_id: str, frm: int | None = None, to: int | None = None) -> list[dict]:
        q = self._db.collection("flags").where("node_id", "==", node_id)
        if frm is not None:
            q = q.where("ts_end", ">=", frm)
        if to is not None:
            q = q.where("ts_start", "<=", to)
        return sorted(
            [d.to_dict() for d in q.stream()], key=lambda f: (f["ts_start"], f["ts_end"])
        )

    def get_watermark(self, key: str) -> dict | None:
        snap = self._db.collection("flag_watermarks").document(key).get()
        return snap.to_dict() if snap.exists else None

    def set_watermark(self, key: str, doc: dict) -> None:
        self._db.collection("flag_watermarks").document(key).set(dict(doc))

    # -- labels
    def put_label(self, label: dict) -> None:
        self._db.collection("labels").document(label["id"]).set(dict(label))

    def get_label(self, lid: str) -> dict | None:
        snap = self._db.collection("labels").document(lid).get()
        return snap.to_dict() if snap.exists else None

    def mark_superseded(self, lid: str, new_id: str) -> bool:

        ref = self._db.collection("labels").document(lid)

        @self._db.transactional
        def _txn(txn):
            snap = ref.get(transaction=txn)
            if not snap.exists or snap.to_dict().get("superseded_by"):
                return False
            txn.update(ref, {"superseded_by": new_id})
            return True

        return bool(_txn(self._db.transaction()))

    def list_labels(self, room_id: str | None = None) -> list[dict]:
        q = self._db.collection("labels")
        if room_id is not None:
            q = q.where("room_id", "==", room_id)
        return sorted(
            [d.to_dict() for d in q.stream()], key=lambda lb: (lb["ts_start"], lb["ts_end"])
        )

    # -- timetable
    def replace_timetable(self, room_id: str, entries: list[dict]) -> None:
        col = self._db.collection("timetable")
        old = list(col.where("room_id", "==", room_id).stream())
        batch = self._db.batch()
        for d in old:
            batch.delete(d.reference)
        for en in entries:
            batch.set(col.document(en["id"]), dict(en))
        batch.commit()

    def list_timetable(self, room_id: str | None = None) -> list[dict]:
        q = self._db.collection("timetable")
        if room_id is not None:
            q = q.where("room_id", "==", room_id)
        return [d.to_dict() for d in q.stream()]

    # -- users
    def get_user(self, email: str) -> dict | None:
        snap = self._db.collection("users").document(email.lower()).get()
        return snap.to_dict() if snap.exists else None

    def put_user(self, user: dict) -> None:
        self._db.collection("users").document(user["email"].lower()).set(dict(user))

    def list_users(self) -> list[dict]:
        return [d.to_dict() for d in self._db.collection("users").stream()]

    # -- audit (append-only enforced by firestore.rules + no update/delete here)
    def append_audit(self, entry: dict) -> str:
        import uuid as _uuid

        from .util import hash_chain

        aid = entry.get("id") or _uuid.uuid4().hex[:16]
        head = self.kv_get("audit_head")
        prev = head["value"] if head else "GENESIS"
        row = hash_chain(
            prev,
            str(entry["ts"]),
            entry["actor"],
            entry["action"],
            entry.get("target", ""),
            entry.get("detail", ""),
        )
        self._db.collection("audit_log").document(aid).set(
            dict(entry, id=aid, prev_hash=prev, row_hash=row)
        )
        self.kv_set("audit_head", {"value": row})
        return aid

    def list_audit(self, limit: int = 200) -> list[dict]:
        q = self._db.collection("audit_log").order_by("ts", direction="DESCENDING").limit(limit)
        return [d.to_dict() for d in q.stream()]

    def verify_audit_chain(self) -> bool:
        from .util import hash_chain

        ordered = sorted(
            (d.to_dict() for d in self._db.collection("audit_log").order_by("ts").stream()),
            key=lambda a: a["ts"],
        )
        prev = "GENESIS"
        for a in ordered:
            if a["prev_hash"] != prev:
                return False
            expect = hash_chain(prev, str(a["ts"]), a["actor"], a["action"],
                                a.get("target", ""), a.get("detail", ""))
            if a["row_hash"] != expect:
                return False
            prev = a["row_hash"]
        return True

    # -- eval runs / exports / kv
    def put_run(self, run: dict) -> None:
        self._db.collection("eval_runs").document(run["id"]).set(dict(run))

    def get_run(self, rid: str) -> dict | None:
        snap = self._db.collection("eval_runs").document(rid).get()
        return snap.to_dict() if snap.exists else None

    def list_runs(self) -> list[dict]:
        q = self._db.collection("eval_runs").order_by("created_ts", direction="DESCENDING")
        return [d.to_dict() for d in q.stream()]

    def put_export(self, meta: dict) -> None:
        self._db.collection("config").document("export:" + meta["id"]).set(dict(meta))

    def get_export(self, eid: str) -> dict | None:
        snap = self._db.collection("config").document("export:" + eid).get()
        return snap.to_dict() if snap.exists else None

    def kv_get(self, key: str) -> dict | None:
        snap = self._db.collection("config").document(key).get()
        return snap.to_dict() if snap.exists else None

    def kv_set(self, key: str, doc: dict) -> None:
        self._db.collection("config").document(key).set(dict(doc))


def get_db(cfg: Config):
    if cfg.db_mode == "memory":
        return MemoryDB()
    return FirestoreDB(cfg)
