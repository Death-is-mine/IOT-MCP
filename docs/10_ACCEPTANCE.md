# 10 — Acceptance Document

Version 0.1 draft · 2026-10-05. A milestone is accepted only when every listed criterion is evidenced. "Evidence" means a test result, a screenshot or recording, or a file in the evidence pack (§5). Targets marked [DEFAULT] can be changed with the mentor before M1 starts.

## 1. Definition of Done (applies to every milestone)
- Linked SRD requirements implemented and their test cases pass (`pytest -q`, `ruff check .`).
- Coverage target met for flag and evaluation modules (NFR-007).
- No open S1/S2 defects (09_TEST_PLAN §7).
- No secrets in repo or logs; no actuation code (TC-SEC-06, TC-SEC-09).
- MEMORY.md updated: decisions, new facts, milestone status, known issues.
- Docs updated if behaviour or contracts changed.

## 2. Acceptance criteria by milestone
| ID | Milestone | Criterion | Evidence |
|---|---|---|---|
| AC-01 | M0 | `fleet_gateway.py` framework, entry points, run command, and integration seam recorded; minimal-change plan approved by the owner | MEMORY.md "Environment facts" + owner approval |
| AC-02 | M1 | Simulator batches ingest correctly; duplicates ignored; invalid batches rejected; no partial commits; `/poll` returns empty commands | TC-ING-01..09 |
| AC-03 | M1 | Gateway survives kill -9 during ingest with no acknowledged loss | TC-ING-10 |
| AC-04 | M2 | All nine flag rules pass golden tests; incremental equals full recompute | TC-QF-01..12 |
| AC-05 | M2 | Fleet page shows every required column for simulated nodes including injected faults | TC-UI-01 + screenshot |
| AC-06 | M3 | Node page shows series, flags, events; ≤ 2000 points; < 3 s for 24 h | TC-UI-02..04, TC-PERF-03 |
| AC-07 | M4 | Role matrix passes for every route; Firebase Auth tested (ID token + custom token) | TC-AU-01..04 |
| AC-08 | M4 | Audit log append-only and complete for listed actions | TC-AD-01..02 |
| AC-09 | M4 | Custom token minted once per node; not stored on server; rotatable; disabled node rejected | TC-NOD-01..03 |
| AC-10 | M5 | Labels immutable with supersede; conflicts view works; coverage matches hand calculation | TC-LB-01..05 |
| AC-11 | M5 | Export is deterministic, has manifest + dictionary, and is injection-safe | TC-EX-01..04 |
| AC-12 | M6 | Evaluation matches hand-computed golden results; hold-time property holds; bootstrap reproducible; runs store versions and data hash | TC-EV-01..07 |
| AC-13 | M6 | Results page shows curve, CIs, and labelled hours behind every figure | TC-EV-07 + screenshot |
| AC-14 | M7 | Firestore backup created via gcloud export and verified via dry-run import; restore drill passes | TC-OP-02..03 |
| AC-15 | M7 | Load targets met: p95 ingest < 200 ms at 5 simulated nodes; 24 h backfill burst handled | TC-PERF-01..02 |
| AC-16 | M7 | Security suite passes (injection, XSS, CSRF, headers, abuse) | TC-SEC-01..08 |
| AC-17 | M7 | Runs unattended on the mini-PC for 7 days with real or simulated nodes; incidents logged | uptime log in evidence pack |

## 3. Research-quality acceptance (field)
| ID | Criterion | Evidence |
|---|---|---|
| AC-18 | Calibration per load type against a reference, with errors reported [DEFAULT target ≤ 5% RMS, or the deviation is stated] | TC-FLD-01 table |
| AC-19 | Ground truth: ≥ 30 labelled occupied-hours, ≥ 30 vacant-hours, ≥ 5 scripted still-occupant trials [DEFAULT] | label coverage view |
| AC-20 | Baseline audit: percentage of hours lights/fans ran with zero occupancy, per room, with method (measured/estimated) | evaluation output |
| AC-21 | Comparison of `pir_only` against ≥ 1 other config at ≥ 4 hold times, with CIs and sample sizes; negative results reported as such | evaluation run |
| AC-22 | Data completeness ≥ 95% per node-day excluding declared outages [DEFAULT] | completeness report |
| AC-23 | Cost-benefit note for facilities states assumptions, tariff source, and uncertainty | note in evidence pack |

## 4. Demo script (10 minutes, honest framing)
1. **Problem and claim (1 min):** "We measure local waste and compare sensing setups; we don't claim to invent occupancy control."
2. **Fleet page (1 min):** nodes, statuses, a deliberately injected fault from the simulator shown as a flag.
3. **Node page (2 min):** power and presence on one axis; shadow-mode `would_cut` markers.
4. **Labelling (1 min):** add a label; show it is immutable and superseded when corrected.
5. **Evaluation (3 min):** curve of energy saved vs wrong cut-offs; point out intervals and labelled hours.
6. **Limits (1 min):** measured vs estimated power, small sample, room-specific results, not a safety device.
7. **Safety (1 min):** v1 cannot switch anything; demo used recorded or low-voltage data.
Backup: recorded data from the simulator if live nodes fail.

## 5. Evidence pack (folder `evidence/`)
Test run output, coverage report, screenshots (fleet, node, labelling, results), calibration table, label coverage export, evaluation run exports with manifests, restore drill log, 7-day uptime log, security test output, MEMORY.md snapshot, final report draft.

## 6. Go/no-go for any switching (Half 2). Not part of v1 acceptance.
All of the following must be true before any control code is written:
- [ ] v1 accepted (AC-01..AC-17) and field evidence collected (AC-18..AC-22).
- [ ] Evaluation shows false-vacant rates the mentor and facilities consider acceptable.
- [ ] Written facilities and mentor approval for each circuit.
- [ ] Qualified electrician has designed and will install the mains-side hardware (SAF-03..06).
- [ ] Fail-safe default-on, manual override, fuse and enclosure verified on the bench with low-voltage equivalents.
- [ ] Command signing, expiry, and audit design reviewed (SSD §8) and tested in simulation.
- [ ] Control is a separate milestone with its own SRD, tests, and acceptance.

## 7. Sign-off
| Role | Name | Date | Decision |
|---|---|---|---|
| Owner | Shreyansh Saini | | |
| Faculty mentor | | | |
| Facilities representative (if installation) | | | |

## 8. Status — 2026-10-05 (code acceptance; field acceptance open)
- AC-01..06, AC-08..13, AC-15 (proxy), AC-16: MET in code (tests cited in 09_TEST_PLAN §8).
- AC-07: PARTIAL — role matrix + dev-token halves pass; Firebase ID/custom-token halves skipped (need test project).
- AC-09: PARTIAL — mint-once/rotate/disable pass in dev seam; Firebase mint path untested (needs project).
- AC-14: PARTIAL — memory snapshot round-trip passes; gcloud export/import drill pending.
- AC-17..AC-23: OPEN — need mini-PC, hardware, calibration, and labelled hours. No S1/S2 defects open in code.
- Evidence pack so far: pytest output (81 passed), coverage report (flags+eval 90%), ruff clean, live-smoke transcript, MEMORY.md snapshot. Still to add: screenshots, calibration table, label-coverage export, eval-run exports, restore-drill log, uptime log, final report draft.
