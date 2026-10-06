# CEM Documentation Set — Index

**Project:** Classroom Energy Monitor (CEM) — fleet gateway, data-quality tooling and evaluation platform
**Owner:** Shreyansh Saini · **Version:** 0.1 draft · **Date:** 2026-10-05
**Audience:** the owner, the faculty mentor, and OpenCode (coding agent)

## 1. What this project is
ESP32 nodes measure lights/fans current and room presence (PIR, optionally mmWave or CO2) in 3-5 classrooms and push data to a campus-only gateway. The gateway stores raw data, computes data-quality flags, lets people label ground-truth occupancy, exports reproducible datasets, and runs an offline evaluation that measures **energy saved vs. wrong cut-offs** for different presence-sensing setups and hold times.

**What it is not:** a smart switch, a safety device, or a first-of-its-kind invention. Occupancy-based switching is established. The contribution is local, measured evidence and an honest comparison. Do not write marketing claims into code, UI text, or reports.

## 2. Document set
Acronyms are **interpreted** here; the owner should confirm or correct them.

| File | Document | Meaning used |
|---|---|---|
| 01_PRD.md | PRD | Product Requirements: why, who, goals, scope, metrics |
| 02_SRD.md | SRD | Software Requirements: numbered, testable "shall" statements |
| 03_TRD.md | TRD | Technical Requirements: stack, schema, API contracts, standards |
| 04_ARD.md | ARD | Architecture Requirements: quality targets, constraints, decision records |
| 05_ADD.md | ADD | Architecture Design: components, flows, deployment, failure modes |
| 06_AIRD.md | AIRD | AI Requirements: models, LLM/MCP rules, AI evaluation |
| 07_SSD.md | SSD | Security & Safety Design (includes privacy and mains safety) |
| 08_DATA_PIPELINE.md | Data pipeline | Stages, flag rules, evaluation definitions, export format |
| 09_TEST_PLAN.md | Test plan | Test levels, cases mapped to requirements, field protocols |
| 10_ACCEPTANCE.md | Acceptance | Criteria per milestone, demo script, sign-off, control go/no-go |
| MEMORY.md + ../AGENTS.md | Agent memory | Rules the agent follows and the living decision/status log |

## 3. Status legend (used in every document)
- **[DECIDED]** stated by the owner. Do not change without asking.
- **[DEFAULT]** recommended, reversible. Implement it, make it easy to change.
- **[OPEN]** needs owner input. Implement the default behind a config flag and record it in MEMORY.md.
- **[ASSUMED]** unverified assumption. Verify early.

## 4. Precedence when documents conflict
SSD (safety/security) > SRD > TRD > ADD > ARD > PRD > others. Record every resolved conflict in MEMORY.md.

## 5. Reading order for the agent
AGENTS.md → MEMORY.md → 02_SRD → 03_TRD → 05_ADD → 08_DATA_PIPELINE → 07_SSD → 09_TEST_PLAN → 10_ACCEPTANCE. Read 01, 04, 06 for context when a decision needs it.

## 6. Traceability
IDs: `FR-` functional, `NFR-` non-functional (SRD) · `SEC-`/`SAF-` (SSD) · `AI-` (AIRD) · `QF-` flag rules (pipeline) · `TC-` tests · `AC-` acceptance · `ADR-` decisions (ARD) · `D-`/`O-` memory log.
Rule: every Must/Should `FR-` has at least one `TC-`, and every `TC-` maps to an `AC-`.

## 7. Milestones (effort is a rough guess in human-hours including review, not a commitment)
| ID | Milestone | Est. h |
|---|---|---|
| M0 | Discovery: read `fleet_gateway.py`, set repo layout, record facts in MEMORY.md | 4 |
| M1 | DB + ingest + `/poll` stub + node simulator + tests | 10 |
| M2 | Flag engine + Fleet page | 8 |
| M3 | Node detail page (charts, flag overlay) | 6 |
| M4 | Auth (Firebase or local), roles, audit log, node admin | 8 |
| M5 | Labelling, timetable, export with manifest | 9 |
| M6 | Evaluation engine + results page | 12 |
| M7 | Hardening: backup/restore, load, security tests, acceptance run | 8 |
| S1-S4 | Stretch: read-only MCP server, LLM report, firmware milestone, Half 2 control | not planned |

Stretch items start only after M7 passes. Half 2 control additionally needs the go/no-go in 10_ACCEPTANCE.md.

## 8. Open decisions (defaults apply until answered)
| ID | Question | Default |
|---|---|---|
| O-1 | Are JECRC emails Google accounts (Workspace)? Firebase or local login? | Firebase Auth, no local fallback (owner ruling 2026-10-05, MEMORY D-016) |
| O-2 | Which framework does `fleet_gateway.py` use? | None existed; Flask thin shim [DEFAULT] reversible (MEMORY D-017); owner may still provide one |
| O-3 | TLS to ESP32: pinned certificate, or isolated network + signed requests? | Pinned certificate; HMAC-signing mode specified in SSD but off |
| O-4 | Second presence sensor: mmWave or CO2? | Schema supports both; pick one for the pilot |
| O-5 | Timetable source, format, and permission to use it | CSV import; no instructor names |
| O-6 | Mini-PC OS and who administers it | Linux, systemd |
| O-7 | Pilot rooms and node count | 3-5 rooms |
| O-8 | Facilities/mentor approval for any mains-side work | Required before any wiring |
| O-9 | Is the old "shared read-only token" retired in favour of user login? | Retired (see D-006 in MEMORY.md) |
| O-10 | LLM provider for the stretch report | None; template-only until chosen |

## 9. Kickoff prompt for OpenCode
> ~~Start Milestone M0 only …~~ DONE 2026-10-05: `fleet_gateway.py` did not exist, so M0 created it as a thin Flask shim; owner rulings D-015 (Firestore), D-016 (Firebase Auth), D-017 (Flask, owner may still provide framework). M0–M7 code-complete in dev seams (MEMORY.md board); field evidence (AC-17..AC-23) pending hardware/mini-PC.

## 10. Honest notes
- Nothing here is "perfect"; it is scoped to be finishable and defensible.
- Targets marked [DEFAULT] are starting points, not measured facts.
- Firmware is specified as a contract only; the agent builds a simulator, not hardware drivers, in v1.
