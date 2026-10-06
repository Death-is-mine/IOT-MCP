# 03 — Technical Requirements Document (TRD)

Version 0.1 draft · 2026-10-05

## 1. Stack
| Layer | Choice | Status |
|---|---|---|
| Language/runtime | Python ≥ 3.11 | DEFAULT |
| Web framework | Flask thin shim (M0: no file existed; DEFAULT, reversible — `cem_gw/` stays framework-agnostic) | DEFAULT (D-017) |
| Database | **Firestore (asia-south1)** via `firebase-admin` SDK (production); same-interface `memory` backend for dev/tests (DEFAULT D-018) | DECIDED (ADR-013) |
| Frontend | Plain HTML + vanilla JS; uPlot 1.6.32 iife+css vendored under `static/vendor/` (hashes in `tests/contract/test_node_ui.py`) | DECIDED / DEFAULT |
| Auth | Firebase Auth (Email/Google/Phone) + custom claims for roles; Firebase Custom Tokens for nodes (production); `dev` bearer seam for local dev/tests (DEFAULT D-018) | DECIDED |
| Evaluation | Python modules; stdlib only (numpy present but unused by eval) | DEFAULT |
| Tests | `pytest`, `ruff`, `coverage`; type hints on all public functions | DEFAULT |
| Hosting | Mini-PC, Linux, `systemd`, reverse proxy with TLS | DEFAULT |

Dependency rule: add a dependency only if the stdlib cannot do the job reasonably; record the reason in MEMORY.md. Pin exact versions in a lock file at implementation time (versions are not fixed in these documents).

## 2. Repository layout
```
AGENTS.md  opencode.json
docs/                      # this documentation set
fleet_gateway.py           # M0: did not exist; created as thin shim (create_app + engine thread + serve)
cem_gw/                    # new code
  config.py  db.py (MemoryDB + FirestoreDB)  ingest.py  poll.py  nodes.py
  flags/ (rules.py engine.py)  api_read.py  labels.py  timetable.py  export.py
  evaluation/ (configs.py replay.py stats.py runner.py)  # no metrics.py: metrics live in replay.py
  auth/ (base.py firebase.py dev.py)  audit.py  health.py  backup.py  util.py
static/  index.html fleet.html node.html label.html eval.html export.html admin.html app.js api.js vendor/
tools/  simulator.py create_node.py backup_restore.py
tests/  unit/ contract/ integration/ security/ golden/
firestore.indexes.json     # composite indexes for Firestore queries
firmware_spec/  contract.md  schema.json
```

## 3. Time
All stored times are UTC epoch milliseconds (INTEGER). The UI displays Asia/Kolkata. Node `ts` may be wrong if the node clock is unsynced; nodes send `time_synced` and `sent_ts` so the gateway can flag drift. Server receive time is authoritative for ordering diagnostics only.

## 4. Firestore Data Model
Collections (root-level):
```
rooms/{room_id}           // {name, building, created_ts}
nodes/{node_id}           // {room_id, status, fw_version, mode, calib, calib_ts, created_ts, last_seen_ts, max_seq, clock_offset_ms, sample_period_s, batch_interval_s} — no token stored server-side
readings/{node_id}/samples/{seq}  // {ts, ts_recv, backfill, current_a, voltage_v, power_w, power_method, pf, pir, mmwave, co2_ppm, lux, temp_c, rh, load_state}
events/{node_id}/entries/{eseq}   // {ts, ts_recv, type, payload}
flags/{id}                // {node_id, type, severity, ts_start, ts_end, rule_version, details, computed_ts}
flag_watermarks/{node_id}:{rule_version} // {last_ts, state} (incremental signal state)
labels/{id}               // {room_id, ts_start, ts_end, state, source, labeller, note, created_ts, superseded_by}
timetable/{id}            // {room_id, dow (Mon=0), start_min, end_min, course_code}
users/{email}             // {role, active, created_ts} (allowlist; no password subcollection — no local-password mode)
audit_log/{id}            // {ts, actor, action, target, detail, ip, prev_hash, row_hash} (append-only + firestore.rules deny)
eval_runs/{id}            // {created_ts, created_by, status, params, rule_version, code_version, data_hash, results, error?}
config/{key}              // runtime kv: audit_head {value}, export:<id> {manifest} — no rooms/ collection (room is a node/label attribute)
```

**Key design notes:**
- Subcollections for high-volume per-node data (`readings/`, `events/`) — document ID = `seq`/`eseq` for idempotency
- Composite indexes defined in `firestore.indexes.json` (auto-created on first failed query)
- No migrations needed; schema enforced at application layer
- Atomic batch ingest via Firestore transactions (500 ops max) or batched writes
- Watermark doc per node+rule_version enables incremental flag computation

## 5. Node payload (ingest request)
```json
{"schema_version":1,"node_id":"cem-204-a","fw_version":"0.1.0","batch_id":"b-000123",
 "sent_ts":1760000000000,"time_synced":true,
 "samples":[{"seq":101,"ts":1760000000000,"current_a":1.23,"voltage_v":231.2,"power_w":271.4,
   "power_method":"measured","pf":0.95,"pir":1,"mmwave":null,"co2_ppm":612,"lux":340,
   "temp_c":29.1,"rh":48,"load_state":1}],
 "events":[{"eseq":12,"ts":1760000001000,"type":"would_cut","payload":{"hold_s":600,"config":"pir_only"}}]}
```
Limits: ≤ 200 samples and ≤ 50 events per batch; body ≤ 256 KB. Absent sensors are `null`. `seq` and `eseq` are per-node monotonic counters persisted on the node. Event types: `boot`, `fault`, `would_cut`, `mode_change`, `time_sync`, `calib_update`.

## 6. HTTP API (all JSON; prefix `/api/v1`)
| Method + path | Auth | Purpose |
|---|---|---|
| `POST /ingest` | node token | Ingest batch → `{accepted, duplicates, last_seq, server_time}`; errors 400/401/403/413/429 |
| `GET /poll?node_id=` | node token | `{server_time, config:{mode, sample_period_s, batch_interval_s}, commands:[]}` |
| `GET /fleet` | viewer+ | Node status list |
| `GET /nodes/{id}/readings?from&to&max_points` | viewer+ | Downsampled series |
| `GET /nodes/{id}/flags?from&to` | viewer+ | Flag intervals |
| `GET /nodes/{id}/events?from&to` | viewer+ | Events |
| `GET /labels`, `POST /labels`, `POST /labels/{id}/supersede`, `GET /labels/conflicts`, `GET /labels/coverage` | viewer+ / labeller+ | Labelling |
| `POST /timetable/import`, `GET /timetable` | admin / viewer+ | Timetable |
| `POST /export` → `GET /export/{id}` | viewer+ | CSV + manifest + dictionary (zip) |
| `POST /eval/runs`, `GET /eval/runs`, `GET /eval/runs/{id}` | admin / viewer+ | Evaluation |
| `GET/POST /admin/nodes`, `/admin/users`, `GET /admin/audit`, `POST /admin/backup`, `POST /admin/restore` | admin | Administration + live backup/restore |
| `GET /healthz` | none | Liveness only |
Errors use `{"error":"<code>","message":"...","details":[...]}`. Same-origin only; no CORS.

## 7. Auth contracts
- **Node (production):** `Authorization: Bearer <ID token exchanged from Firebase Custom Token>`; backend mints the custom token via `firebase_admin.auth.create_custom_token("node:<node_id>", …)`; gateway verifies the ID token via Admin SDK. Token shown once, never stored.
- **Node (dev seam):** `Bearer dev-node:<node_id>:<CEM_DEV_SECRET>`; node must be registered and enabled.
- **User (production):** `Authorization: Bearer <Firebase ID Token>` (Email/Google/Phone); server verifies via Firebase Admin SDK; role from custom claims (`viewer`/`labeller`/`admin`) intersected with the `users` allowlist; no local fallback in v1.
- **User (dev seam):** `Bearer dev-user:<email>:<CEM_DEV_SECRET>`; first admin auto-created from `CEM_DEV_ADMIN`.

## 8. Configuration (environment)
`CEM_DB_MODE` (`firestore` default | `memory` dev-only), `CEM_AUTH_MODE` (`firebase` default | `dev` dev-only), `CEM_DEV_SECRET` (required in dev), `CEM_DEV_ADMIN` (bootstrap admin, dev-only), `CEM_BACKUP_DIR`, `CEM_EXPORT_DIR`, `CEM_BIND_HOST` (127.0.0.1), `CEM_PORT` (8080), `CEM_FIREBASE_PROJECT_ID` (`iot-mcp`), `CEM_FIREBASE_REGION` (`asia-south1`), `FIREBASE_SERVICE_ACCOUNT_JSON` (path to service account key), `CEM_CONTROL_ENABLED` (must stay `false`; `true` refuses to start), `CEM_MAX_BODY_KB` (256), `CEM_INGEST_RATE_PER_MIN` (20), `CEM_DISPLAY_TZ` (Asia/Kolkata), `CEM_FLAG_RULES_FILE`, `CEM_FLAG_INTERVAL_S` (60). Provide `.env.example`; never commit `.env` or service account key.

## 9. Node simulator (`tools/simulator.py`)
Deterministic by seed. Scenarios: `normal_day`, `gap`, `duplicates`, `reorder`, `clock_skew`, `stuck_pir`, `stuck_current`, `backfill_after_outage`, `still_occupant_trial`, `fan_interference`. `--labels-out` writes a ground-truth label CSV so evaluation tests have known answers. History replays fast and is honestly flagged BACKFILLED/CLOCK_DRIFT; `--minutes N --end-now` posts a recent window for near-live demos. One simulator run per node-id (seqs restart per run and are correctly deduped). 429 responses are honoured with Retry-After back-off. Extra flags: `--node-id`/`--room` (single-node runs), `--bearer` (explicit token).

## 10. Firmware contract (spec only in v1)
Node shall: keep `seq`/`eseq` in non-volatile storage; buffer unsent samples locally and backfill in order; sync time via NTP and report `time_synced`; POST batches every `batch_interval_s`; call `/poll` at the same cadence; verify the gateway certificate by pinning (or follow the O-3 fallback); never act on data from the gateway beyond `config`. Real firmware is a separate milestone (S3).

## 11. Coding standards
Small modules; no business logic in HTTP handlers; no global mutable state; SDK document references only, never string-built queries; no `eval`/`exec`; no secrets in logs; every flag rule and metric is a pure function with unit tests; commit messages reference requirement IDs.

## 12. Commands (confirmed at M0, also in MEMORY.md)
Run: `python fleet_gateway.py` · Test: `pytest -q` · Lint: `ruff check .` · Coverage: `coverage run -m pytest tests/ -q` · Simulate: `python tools/simulator.py --scenario normal_day --nodes 3 --days 2 --seed 1`.
