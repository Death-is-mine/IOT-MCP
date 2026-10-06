# 09 — Test Plan

Version 0.1 draft · 2026-10-05. Tests are written alongside each milestone, not at the end. Flag rules and evaluation metrics are developed test-first with hand-computed golden data.

## 1. Levels and tools
| Level | Scope | Tool |
|---|---|---|
| Unit | Pure functions: flag rules, metrics, export formatting, time handling | `pytest` |
| Contract | Ingest/poll schemas, API response shapes | `pytest` + HTTP client |
| Integration | Simulator → gateway → flags → API → export → evaluation | `pytest` with temp DB |
| Security | Auth matrix, injection, headers, secrets | `pytest` + scripted requests |
| Performance | Ingest load, backfill burst, page data size | simulator at speed-up |
| UI smoke | Each page loads, key actions work | scripted browser or manual checklist |
| Field | Calibration, scripted trials, outage recovery, safety checklist | manual protocols below |

Environments: local dev (Firestore emulator), staging on the mini-PC (dedicated Firestore project), production. Never test against the production Firestore project.

## 2. Entry and exit criteria
Entry for a milestone: SRD items identified, test cases drafted. Exit: all Must test cases pass, coverage targets met (NFR-007), no open high-severity defects, MEMORY.md updated.

## 3. Test cases
| ID | Description | Covers |
|---|---|---|
| TC-ING-01 | Valid batch stored; response counts correct | FR-001, FR-005 |
| TC-ING-02 | Same batch twice → duplicates counted, rows unchanged | FR-002 |
| TC-ING-03 | Batch with a mix of new and duplicate seqs | FR-002 |
| TC-ING-04 | Invalid schema/type/limits → 400, nothing stored | FR-003 |
| TC-ING-05 | Fault injected mid-transaction → no partial batch (Firestore transaction rolls back) | FR-003, NFR-003 |
| TC-ING-06 | Backfill marking at the 300 s boundary | FR-004 |
| TC-ING-07 | Oversize body → 413; excess rate → 429 | FR-006 |
| TC-ING-08 | `/poll` returns empty commands and updates last-seen | FR-007 |
| TC-ING-09 | With control flag false/true, no command is ever generated in v1 | FR-008, SEC-12 |
| TC-ING-10 | Kill -9 the gateway during ingest; restart; retry; no acknowledged loss | NFR-003 |
| TC-NOD-01 | Register node; custom token minted once; not stored on server | FR-010, SEC-02 |
| TC-NOD-02 | Rotate key: mint new custom token; old token rejected; disable node → 403 | FR-011 |
| TC-NOD-03 | Calibration constants saved and shown | FR-012 |
| TC-QF-01..09 | One golden-data test per rule QF-01..QF-09 (boundary values included) | FR-020, FR-021 |
| TC-QF-10 | Rule version bump keeps old flags, adds new | FR-021 |
| TC-QF-11 | Completeness and node status transitions | FR-022, FR-023 |
| TC-QF-12 | Incremental run equals full recompute | FR-020 |
| TC-UI-01 | Fleet page shows all required columns | FR-030 |
| TC-UI-02 | Node page charts + flag overlay + event markers | FR-031, FR-033 |
| TC-UI-03 | Downsampling ≤ 2000 points; time-range selection | FR-032 |
| TC-UI-04 | Times displayed in Asia/Kolkata with label; stored UTC | FR-034 |
| TC-UI-05 | No build step; no external script at runtime (firebase mode excepted); vendor files match recorded hash | FR-035, NFR-005 |
| TC-LB-01 | Create label with validation (enums, length, ts order) | FR-040 |
| TC-LB-02 | Edit attempt rejected; supersede creates new row | FR-041 |
| TC-LB-03 | Conflicting overlaps appear in conflicts view | FR-042 |
| TC-LB-04 | Coverage view equals hand-computed hours | FR-043 |
| TC-LB-05 | Timetable CSV import: valid, malformed, instructor-name column rejected | FR-044 |
| TC-EX-01 | Export joins readings, flags, labels correctly on golden data | FR-050 |
| TC-EX-02 | Manifest hash matches CSV; dictionary present | FR-051 |
| TC-EX-03 | Formula-injection strings neutralised | FR-052, SEC-08 |
| TC-EX-04 | Same params twice → identical bytes | FR-053 |
| TC-EV-01 | Golden scenario: hand-computed false-vacant events | FR-062 |
| TC-EV-02 | Golden scenario: hand-computed disruption and wasted minutes | FR-062 |
| TC-EV-03 | Golden scenario: hand-computed energy saved, with method flag | FR-062 |
| TC-EV-04 | Property: larger hold time never increases false-vacant events or energy saved | FR-061, FR-062 |
| TC-EV-05 | Bootstrap reproducible with the same seed | FR-063 |
| TC-EV-06 | Run record stores params, versions, data hash | FR-064 |
| TC-EV-07 | Results page shows curve and labelled hours | FR-065, FR-066 |
| TC-EV-08 | Time-split leakage test for any learned model | FR-067, AI-04 |
| TC-AU-01 | Firebase Auth: valid ID token accepted; expired, wrong audience, unverified email, wrong domain, not allowlisted → rejected | FR-070..072 |
| TC-AU-02 | Custom token verification: valid node token accepted; expired, wrong claims, revoked → rejected | FR-070, FR-074 |
| TC-AU-03 | Role matrix for every route (viewer/labeller/admin/anonymous) | FR-071, FR-072, SEC-06 |
| TC-AU-04 | Admin adds/deactivates users | FR-073 |
| TC-AD-01 | Audit entries for each audited action | FR-080 |
| TC-AD-02 | UPDATE/DELETE on audit_log aborts; hash chain verifies | FR-081, SEC-07 |
| TC-OP-01 | `/healthz` minimal and unauthenticated | FR-090 |
| TC-OP-02 | Backup created via gcloud export and integrity-checked via dry-run import | FR-091 |
| TC-OP-03 | Restore drill into a separate Firestore project passes smoke checks | FR-092 |
| TC-OP-04 | Logs contain no tokens or secrets (scan) | FR-093 |
| TC-OP-05 | Simulator determinism: same seed → same output; scenarios produce ground-truth files | FR-095 |
| TC-SEC-01 | Anonymous request to every non-public route → 401 | SEC-01 |
| TC-SEC-02 | Injection attempts in all inputs (Firestore field paths, query params) | SEC-04 |
| TC-SEC-03 | Stored XSS via note and node name rendered inert | SEC-04 |
| TC-SEC-04 | CSRF attempt on mutating endpoints rejected (state-changing requests require valid session) | SEC-10 |
| TC-SEC-05 | Security headers and CSP present; no inline scripts | SEC-11 |
| TC-SEC-06 | Secret scan over repo and history | SEC-09 |
| TC-SEC-07 | Oversize/rate-limit/slow-request abuse handled | SEC-05 |
| TC-SEC-08 | A node token cannot call user routes and vice versa | SEC-02, SEC-06 |
| TC-SEC-09 | Search codebase: no actuation, relay or command-issuing code | SEC-12, SAF-01 |
| TC-PERF-01 | 5 simulated nodes × 7 days at speed-up: p95 ingest < 200 ms | NFR-001 |
| TC-PERF-02 | 24 h backfill burst from one node accepted and flagged correctly | Q-2 |
| TC-PERF-03 | 24 h node page data within size and time targets | NFR-002 |
| TC-PERF-04 | Storage projection check against NFR-004 | NFR-004 |
| TC-FLD-01 | Calibration vs reference meter (§5) | PRD metrics |
| TC-FLD-02 | Scripted still-occupant trials (§6) | PRD metrics |
| TC-FLD-03 | Real Wi-Fi outage and recovery | Q-2 |
| TC-FLD-04 | Mains-side installation safety checklist | SAF-03..06 |
| TC-AI-* | Created only if stretch AI features are started (AIRD) | AI-* |
| TC-MCP-01 | MCP input validation rejects hostile args before upstream I/O | FR-100, SEC-04 |
| TC-MCP-02 | MCP completeness math: received/expected per node + overall | FR-100 |
| TC-MCP-03 | MCP outputs carry no notes, labeller initials or operator emails | FR-100, SEC-15 |
| TC-MCP-04 | MCP upstream failures mapped (unknown node/run vs gateway error) | FR-100 |
| TC-MCP-05 | MCP config requires tokens; ports/rates validated | FR-100, SEC-01 |
| TC-MCP-10 | MCP lists exactly the six read-only tools, version-pinned blurbs | FR-100 |
| TC-MCP-11 | MCP read journey over seeded live data; outputs clean | FR-100, SEC-15 |
| TC-MCP-12 | MCP without/wrong bearer refused (401) before any tool runs | FR-100, SEC-01 |
| TC-MCP-13 | MCP hostile args and unknown ids return tool errors | FR-100, SEC-04 |
| TC-MCP-14 | MCP rate limit answers then 429 (low-rate instance) | FR-100, SEC-05 |

## 4. Test data
Golden fixtures live in `tests/golden/` as small CSV files plus a README showing the hand calculation for every expected number. Simulator scenarios supply larger synthetic data and matching label files. No real student data is used in tests.

## 5. Field protocol: calibration (TC-FLD-01)
For each load type (lights circuit, fans circuit): measure with a reference meter or clamp meter at several known loads (off, partial, full, fan speeds). Record node vs reference; compute RMS error and bias; store calibration constants and date; report error next to every energy figure. Repeat if hardware changes.

## 6. Field protocol: scripted trial (TC-FLD-02)
Two people with a timer. Trial A: occupant sits still 30 min, fans on. Trial B: occupant leaves and re-enters at defined times. Trial C: empty room, loads on. Record exact times in the labelling UI during the trial (source `scripted_trial`). No photos or audio.

## 7. Defect handling
Severity: S1 data loss/security/safety, S2 wrong metric or flag, S3 UI defect, S4 cosmetic. S1 and S2 block acceptance.

## 8. Status — 2026-10-05 (81 passed, 2 skipped, ruff clean, flags+eval coverage 90%)
- PASS in dev seams (memory/dev): TC-ING-01..10 (TC-ING-10 unit half: idempotent retry), TC-NOD-01..03, TC-QF-01..12, TC-UI-01..05, TC-LB-01..05, TC-EX-01..04, TC-EV-01..08, TC-AU-03/04, TC-AD-01/02, TC-OP-01/02 (memory half)/04/05, TC-SEC-01..09 (applicable halves), TC-PERF-01 (proxy)/02/03/04, plus a full sim→ingest→flags→labels→export→eval integration test and a live-HTTP smoke (register → 17,280 ingested → ONLINE → flags → readings).
- SKIPPED (need Firebase test project): TC-AU-01, TC-AU-02.
- PENDING production evidence: TC-ING-10 kill-9 half, TC-OP-02/03 gcloud halves, TC-PERF-01 full 5-node × 7-day, TC-FLD-01..04, 7-day unattended run.
- Added beyond this plan (kept, all passing): backup/restore HTTP round-trip + traversal/tamper rejection, esc()-contract render tests, token non-echo, uPlot hash pinning, config-rule hold monotonicity.
