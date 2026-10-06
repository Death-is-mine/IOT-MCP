# 02 — Software Requirements Document (SRD)

Version 0.1 draft · 2026-10-05. "Shall" statements are testable. Priority: M = Must, S = Should, C = Could. Milestone column refers to 00_INDEX.md. Verification: T = automated test, D = demo, I = inspection, F = field.

## 1. Ingest and poll
| ID | Requirement | Pri | MS | Ver |
|---|---|---|---|---|
| FR-001 | The gateway shall accept batched samples and events at `POST /api/v1/ingest` from authenticated nodes. | M | M1 | T |
| FR-002 | Ingest shall be idempotent on `(node_id, seq)`; duplicates are counted, not stored. | M | M1 | T |
| FR-003 | Each batch shall be validated against the schema and committed atomically; an invalid batch shall return 400 with details and store nothing. | M | M1 | T |
| FR-004 | The gateway shall store both node timestamp and server receive timestamp, and mark samples as backfill when receive time exceeds node time by more than 300 s. | M | M1 | T |
| FR-005 | The ingest response shall include accepted count, duplicate count, last stored seq, and server time. | M | M1 | T |
| FR-006 | The gateway shall enforce a maximum body size and a per-node rate limit. | S | M1 | T |
| FR-007 | `GET /api/v1/poll` shall return server time, node config, and an empty `commands` list in v1, and shall update the node's last-seen time. | M | M1 | T |
| FR-008 | A `CEM_CONTROL_ENABLED` setting, default false, shall exist; when false no command is ever created or returned. v1 shall contain no code path that issues commands. | M | M1 | T, I |

## 2. Nodes
| ID | Requirement | Pri | MS | Ver |
|---|---|---|---|---|
| FR-010 | Admin shall register a node (id, room) and receive a generated key shown once. | M | M4 | T, D |
| FR-011 | Admin shall rotate a node's key and disable/enable a node. | M | M4 | T |
| FR-012 | Admin shall record calibration constants and calibration date per node. | M | M4 | T |
| FR-013 | Node mode (`shadow`/`active`) shall be stored and displayed; v1 nodes only run `shadow`. | S | M2 | D |

## 3. Data quality
| ID | Requirement | Pri | MS | Ver |
|---|---|---|---|---|
| FR-020 | A flag engine shall compute the flags defined in 08_DATA_PIPELINE.md (QF-01..QF-09) incrementally. | M | M2 | T |
| FR-021 | Flags shall be stored as intervals with type, severity, rule version, and details; a rule change shall create a new rule version without deleting old flags. | M | M2 | T |
| FR-022 | The gateway shall compute completeness (received / expected samples) per node for 1 h, 24 h, and a custom range. | M | M2 | T |
| FR-023 | Each node shall have a derived status ONLINE / DEGRADED / OFFLINE per 08_DATA_PIPELINE.md. | M | M2 | T |

## 4. User interface
| ID | Requirement | Pri | MS | Ver |
|---|---|---|---|---|
| FR-030 | The Fleet page shall list every node with status, last seen, firmware version, mode, completeness 24 h, clock offset, calibration age, and active flags. | M | M2 | D |
| FR-031 | The Node page shall chart current/power, presence signals, CO2, lux, and temperature with flags overlaid on the same time axis. | M | M3 | D |
| FR-032 | Charts shall support time-range selection and server-side downsampling to at most 2000 points per series. | M | M3 | T, D |
| FR-033 | Shadow-mode events (`would_cut`) shall be shown as markers on the Node page. | S | M3 | D |
| FR-034 | All times shall be stored as UTC epoch milliseconds and displayed in Asia/Kolkata with a visible timezone label. | M | M2 | T, I |
| FR-035 | Pages shall be plain HTML and JavaScript with no build step; chart library files shall be served locally. | M | M2 | I |

## 5. Labelling and timetable
| ID | Requirement | Pri | MS | Ver |
|---|---|---|---|---|
| FR-040 | A labeller shall create a label: room, start, end, state (`occupied`/`vacant`/`unsure`), source (`scripted_trial`/`spot_check`/`timetable`), initials, optional note (≤ 140 chars). | M | M5 | T, D |
| FR-041 | Labels shall be immutable; a correction shall create a new label that supersedes the old one. | M | M5 | T |
| FR-042 | Overlapping non-superseded labels with conflicting states shall be listed in a conflicts view. | M | M5 | T |
| FR-043 | A label-coverage view shall show labelled hours per room and state. | S | M5 | D |
| FR-044 | Admin shall import a timetable CSV (room, weekday, start, end, optional course code, no instructor names). | S | M5 | T |

## 6. Export
| ID | Requirement | Pri | MS | Ver |
|---|---|---|---|---|
| FR-050 | The gateway shall export CSV joining readings, active flags, and labels for chosen rooms and time range. | M | M5 | T |
| FR-051 | Each export shall include `manifest.json` (versions, calibration, flag rule version, row counts, time range, SHA-256 of the CSV) and a data dictionary. | M | M5 | T |
| FR-052 | Text fields in exports shall be neutralised against spreadsheet formula injection. | M | M5 | T |
| FR-053 | Identical parameters on identical data shall produce byte-identical CSV files. | S | M5 | T |

## 7. Evaluation
| ID | Requirement | Pri | MS | Ver |
|---|---|---|---|---|
| FR-060 | An evaluation runner shall replay stored readings under configured decision rules and hold times, outside the web request thread. | M | M6 | T |
| FR-061 | Configs shall include at least `pir_only` and one multi-signal config; hold times shall be configurable (default 2, 5, 10, 15, 20, 30 min). | M | M6 | T |
| FR-062 | Metrics shall follow 08_DATA_PIPELINE.md section 5: false-vacant events per room-week, disruption minutes, wasted minutes, energy saved with method flag, label coverage. | M | M6 | T |
| FR-063 | Confidence intervals shall be computed by day-block bootstrap with a recorded seed. | S | M6 | T |
| FR-064 | Each run shall store parameters, flag rule version, code version, data hash, and results. | M | M6 | T |
| FR-065 | The Results page shall show a table and a saved-energy vs false-cut-offs curve per config. | M | M6 | D |
| FR-066 | Results shall display label coverage and the number of labelled hours behind every figure. | M | M6 | D |
| FR-067 | Any learned model shall use a time-ordered train/test split with no shuffling (see 06_AIRD). | C | S | T |

## 8. Authentication, roles, audit
| ID | Requirement | Pri | MS | Ver |
|---|---|---|---|---|
| FR-070 | `CEM_AUTH_MODE` shall select `firebase` or `local`; both implement one auth interface. | M | M4 | T |
| FR-071 | Roles `viewer`, `labeller`, `admin` shall be enforced server-side from an allowlist table. | M | M4 | T |
| FR-072 | Every non-public API route shall verify identity and role. | M | M4 | T |
| FR-073 | Admin shall add, change, and deactivate users. | M | M4 | T, D |
| FR-074 | Sessions shall expire; logout shall invalidate the session. | M | M4 | T |
| FR-080 | The gateway shall record auth events, label actions, exports, evaluation runs, user/node administration, and config changes in an audit log. | M | M4 | T |
| FR-081 | The audit log shall be append-only (updates and deletes blocked at database level). | M | M4 | T |
| FR-082 | Admin shall view and filter the audit log. | S | M4 | D |

## 9. Operations
| ID | Requirement | Pri | MS | Ver |
|---|---|---|---|---|
| FR-090 | `GET /healthz` shall report process and database health without authentication and without exposing details. | M | M1 | T |
| FR-091 | A daily backup using the SQLite online backup API shall be written and integrity-checked. | M | M7 | T |
| FR-092 | A restore procedure shall be documented and tested. | M | M7 | T, F |
| FR-093 | Logs shall be structured and shall never contain secrets or tokens. | M | M1 | T, I |
| FR-094 | Configuration shall come from environment/config file; secrets shall never be in the repository. | M | M1 | I |
| FR-095 | A node simulator CLI shall generate deterministic scenarios and matching ground-truth label files. | M | M1 | T |

## 10. Stretch (not planned)
FR-100 read-only MCP server · FR-101 LLM weekly report from precomputed metrics · FR-102 firmware milestone. All governed by 06_AIRD.md. Half 2 control is excluded from this SRD.

## 11. Non-functional requirements
| ID | Requirement | Target |
|---|---|---|
| NFR-001 | Ingest latency at 5 nodes, 30 s batches | p95 < 200 ms |
| NFR-002 | Node page load with 24 h data | < 3 s on campus LAN |
| NFR-003 | No acknowledged data lost on gateway crash/restart | 0 acknowledged samples lost |
| NFR-004 | Storage for 5 nodes over 3 weeks at 5 s sampling | < 2 GB (estimate to verify) |
| NFR-005 | No build step, no CDN at runtime | enforced by inspection |
| NFR-006 | Runtime | Python ≥ 3.11 on Linux |
| NFR-007 | Automated test coverage of flag and evaluation modules | ≥ 80% |
| NFR-008 | Dependencies | minimal; each added dependency justified in MEMORY.md |

## 12. Build notes — 2026-10-05 (what "done" means per requirement today)
- FR-001..009, FR-022/023, FR-030..035, FR-040..044, FR-050..053, FR-060..066, FR-070..073, FR-080..082, FR-090, FR-093, FR-095: implemented + tested in dev seams (81 passed, 2 skipped).
- FR-070 as built: `CEM_AUTH_MODE` selects `firebase` (production, D-016) or `dev` (local dev/tests only, requires `CEM_DEV_SECRET`; first admin via `CEM_DEV_ADMIN`). There is no password-`local` mode.
- FR-008 as built: no command code path exists at all; `CEM_CONTROL_ENABLED=true` refuses to start.
- FR-091/092 as built: memory backend → JSON snapshot + SHA-256 file via `POST /api/v1/admin/backup|restore` (round-trip tested); Firestore backend → `gcloud firestore export` (`backup_firestore()` + `tools/backup_restore.py gcloud-export`), drill pending a real project.
- FR-067 vacuous: no learned model shipped; `evaluation/configs.py` registry asserts rule-only (TC-EV-08).
- NFR-001: p95 ingest < 200 ms measured on 100 local batches (TC-PERF-01 proxy; 5-node × 7-day run pending). NFR-002: 24 h payload builds in ms locally, ≤ 2000 pts (campus-LAN timing pending). NFR-004: projection from measured snapshot size passes < 2 GB. NFR-007: 90% on flags+evaluation modules, measured 2026-10-05.
- Pending Firebase project: FR-010/011 token minting path, TC-AU-01/02, NFR-003 kill-9 run. Pending field: calibration, scripted trials, outage recovery.
