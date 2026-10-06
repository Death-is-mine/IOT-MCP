# 01 — Product Requirements Document (PRD)

Version 0.1 draft · 2026-10-05 · Owner: Shreyansh Saini · Context: JECRC University Sustainability Practicum (3 credits, 120 hrs, faculty-mentored)

## 1. Problem
Lights and fans are often left running in empty classrooms. Awareness drives alone give no numbers and little lasting change. Occupancy-based switching exists, but a campus facilities team cannot judge it without local evidence: how much energy is wasted, how much a given sensing setup would save, and how often it would wrongly cut power on people who are sitting still (PIR detects motion, not presence).

## 2. Product statement
A low-cost monitoring-and-evaluation platform that (1) collects power and presence data from ESP32 nodes, (2) tells the researcher whether each node's data can be trusted, (3) captures ground-truth occupancy labels, and (4) quantifies the trade-off between energy saved and wrong cut-offs for different sensor setups and hold times.

## 3. Honest differentiation
- **Not new:** occupancy-based lighting control, PIR sensors, commercial occupancy sensors, published savings studies.
- **Our contribution (claim only what is measured):** local baseline waste data including ceiling fans; an explicit wrong-cut-off metric from shadow-mode replay; a measured comparison of PIR-only vs PIR plus a second signal and the timetable; a reproducible dataset and cost-benefit note for facilities.
- Any claim of improvement must come from the platform's own evaluation with sample sizes and confidence intervals (see 06_AIRD AI-10).

## 4. Users and roles
| Role | Who | Needs |
|---|---|---|
| Admin | Project owner | Manage nodes/users, run evaluations, export |
| Labeller | Owner, volunteers | Mark occupied/vacant intervals quickly |
| Viewer | Faculty mentor, facilities, evaluators | Read fleet status and results |
| Node | ESP32 device | Push data, poll for config |

## 5. Goals and non-goals
**Goals (v1, Half 1):** trustworthy data; fleet and data-quality visibility; ground-truth labelling; reproducible export; evaluation of energy saved vs wrong cut-offs; secure campus-only access.
**Non-goals (v1):** switching any circuit from the website (Half 2); OTA firmware updates; custom PCB; appliance identification; public internet exposure; cameras or audio; any safety/arc-fault claim; billing-grade metering.

## 6. User stories
- US-01 As the owner I see at a glance which nodes are healthy, so I know which data to trust.
- US-02 As the owner I see why a node is flagged (gap, stuck sensor, clock drift, stale calibration).
- US-03 As a labeller I mark an interval occupied/vacant/unsure in under 30 seconds.
- US-04 As the owner I export a reproducible dataset with its manifest and data dictionary.
- US-05 As the owner I compare PIR-only against other sensor setups at several hold times.
- US-06 As a mentor or facilities viewer I read results and the cost-benefit summary without editing anything.
- US-07 As admin I add users, register nodes, and rotate node keys.
- US-08 As admin I audit who exported, labelled, or changed what.
- US-09 (stretch) I ask an assistant read-only questions about fleet data.

## 7. Scope tiers
| Tier | Items |
|---|---|
| Must | Ingest + storage, quality flags, fleet page, node detail, labelling, export with manifest, evaluation, authentication + roles, audit log, backup/restore, node simulator |
| Should | Timetable import, evaluation comparison across sensor configs, local-time display, simple dashboards for label coverage |
| Could (stretch) | Read-only MCP server, LLM weekly report from precomputed metrics, interpretable learned presence model, adaptive hold time |
| Won't (v1) | Remote control, OTA, custom PCB, appliance health, NILM |

## 8. Success metrics ([DEFAULT] targets; adjust with the mentor)
| Metric | Target |
|---|---|
| Data completeness per node-day (excluding declared outages) | ≥ 95% |
| Exports with manifest and data dictionary | 100% |
| Ground truth | ≥ 30 labelled occupied-hours and ≥ 30 vacant-hours, including ≥ 5 scripted still-occupant trials of ≥ 30 min |
| Current calibration vs reference meter, per load type | reported; target ≤ 5% RMS error |
| Evaluation output | PIR-only vs ≥ 1 alternative config, ≥ 4 hold times, with CIs |
| Reproducibility | Same data + params → identical evaluation numbers |

Success is **not** "15-25% savings". That number is a hypothesis the baseline will confirm or reject.

## 9. Constraints
Campus-only, no public exposure [DECIDED]; plain HTML, no build step [DECIDED]; keep and extend `fleet_gateway.py` [DECIDED]; 120 practicum hours shared with field work; ESP32 ADC is noisy, so calibration is mandatory; no cloud storage of occupancy data [DEFAULT].

## 10. Assumptions and dependencies
Campus Wi-Fi allows nodes to reach the gateway [ASSUMED]; a mini-PC is available [ASSUMED]; facilities/mentor approval for installation [OPEN O-8]; timetable access [OPEN O-5]; outbound internet only if Firebase auth is used [OPEN O-1].

## 11. Risks
| ID | Risk | Mitigation |
|---|---|---|
| R-1 | Too little ground truth | Scripted trials early; label-coverage dashboard |
| R-2 | ESP32 ADC error | External ADC/metering chip, per-load calibration, error bars |
| R-3 | mmWave false triggers from fans | Zone tuning; compare against PIR-only before claiming benefit |
| R-4 | Hours overrun | Strict tiers; stretch only after M7 |
| R-5 | Network/IT restrictions | Early IT conversation; HTTP + signed mode as fallback |
| R-6 | Auth provider dependency | Auth interface with local fallback |
| R-7 | Privacy concerns | No cameras/audio; anonymous labels; notice in rooms |
| R-8 | Mains safety | SSD SAF rules; electrician; v1 is monitor-only |
| R-9 | Scope creep | AGENTS.md rules; owner approval for new features |
| R-10 | Unknown structure of `fleet_gateway.py` | M0 discovery before any code — RESOLVED: file did not exist; thin shim created |

## 12. Open questions
See 00_INDEX.md section 8.

## 13. Build notes — 2026-10-05 (v1 code-complete, dev seams)
- Roles shipped as specified: viewer / labeller / admin (§4), plus node credentials.
- R-6 now reads "auth interface with dev seam": Firebase Auth is production (D-016); `CEM_AUTH_MODE=dev` exists for local dev/tests only, never production.
- Assumption "no cloud storage of occupancy data" (§9) is SUPERSEDED by ADR-013/D-015: Firestore asia-south1, mentor/facilities sign-off still required.
- Simulator (`tools/simulator.py`) covers §8 Must "node simulator" with 10 scenarios + ground-truth labels; US-09 (MCP) and LLM report remain stretch, unstarted.
