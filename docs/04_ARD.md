# 04 — Architecture Requirements Document (ARD)

Version 0.1 draft · 2026-10-05

## 1. Architectural drivers
1. Data trustworthiness matters more than features: the evaluation is only as good as the data.
2. Few nodes (3-5), one small server, one developer: simplicity beats scalability.
3. Campus-only deployment with limited IT involvement.
4. A mains-adjacent system must not be remotely actuated by a web application in v1.
5. Results must be reproducible by someone else.

## 2. Constraints
| ID | Constraint | Status |
|---|---|---|
| C-1 | `fleet_gateway.py` is the thin entry point; all logic in `cem_gw/` (M0: the file did not exist, so it was created as a shim — nothing to preserve) | DECIDED |
| C-2 | Campus-only, no public internet exposure | DECIDED |
| C-3 | HTTPS for transport where possible | DECIDED |
| C-4 | Plain HTML, no frontend build step | DECIDED |
| C-5 | Nodes push; the gateway never opens connections to nodes | DECIDED |
| C-6 | Occupancy data in Firestore (asia-south1); mentor/facilities approval for cloud residency | DECIDED (ADR-013) |
| C-7 | 120 practicum hours total | DECIDED |

## 3. Quality attribute scenarios
| ID | Attribute | Scenario | Measure |
|---|---|---|---|
| Q-1 | Reliability | Gateway restarts while a node is sending | No acknowledged sample lost; node retries and duplicates are ignored (NFR-003) |
| Q-2 | Reliability | Wi-Fi down for 6 h | Node buffers locally, backfills on return, gateway marks backfill and gap flags correctly |
| Q-3 | Integrity | Same batch sent twice | Stored once; counted as duplicate |
| Q-4 | Performance | 5 nodes post every 30 s | p95 ingest < 200 ms (NFR-001) |
| Q-5 | Performance | Open 24 h node page | < 3 s, ≤ 2000 points per series (NFR-002) |
| Q-6 | Security | Unauthenticated request to any data route | 401, nothing leaked; logged |
| Q-7 | Security | Node key leaks | Rotate key; other nodes unaffected |
| Q-8 | Maintainability | New flag rule added | One file + one test + one rule-version bump; no schema change |
| Q-9 | Reproducibility | Re-run an evaluation next month | Identical numbers from same data hash and params |
| Q-10 | Observability | Node silently stops | Fleet page shows OFFLINE within 3 batch intervals |
| Q-11 | Recoverability | Disk failure | Restore from last daily backup; loss ≤ 24 h of gateway-side data (node backfill recovers much of it) |
| Q-12 | Safety | Any software defect | Cannot switch a circuit: no actuation code exists in v1 (SEC/SAF in 07_SSD) |

## 4. Architecture decision records
| ID | Decision | Status | Why | Consequences |
|---|---|---|---|---|
| ADR-001 | ~~SQLite in WAL mode as the only datastore~~ | **OVERTURNED** (ADR-013) | Replaced by Firestore for Firebase Auth integration, managed scaling, real-time listeners | See ADR-013 |
| ADR-002 | HTTP push with sequence numbers instead of MQTT | DEFAULT | Fewer services to secure and run; idempotent ingest plus backfill gives delivery guarantees | No broker last-will; offline detection via last-seen timeout |
| ADR-003 | Pull-based `/poll` for any future control | DECIDED | Gateway never reaches into the node; node can refuse | Latency equals poll interval |
| ADR-004 | Plain HTML + vanilla JS + vendored uPlot | DECIDED/DEFAULT | No build tooling; works offline on campus | Less UI polish; hand-written state handling |
| ADR-005 | Firebase Auth (Email/Google/Phone) + custom claims; Firebase Custom Tokens for nodes | DECIDED | Owner preference; unified auth for users and nodes | No local fallback; outage blocks login but not data collection |
| ADR-006 | Per-node Firebase Custom Tokens (not stored) | DECIDED | Compromise of one node contained; tokens minted on demand | Rotation via new custom token; no hash storage needed |
| ADR-007 | Raw data append-only; flags and metrics derived and versioned | DEFAULT | Rule changes never destroy history; reproducibility | More storage; recompute jobs |
| ADR-008 | Evaluation is an offline replay job, not a web feature | DEFAULT | Deterministic, testable, no request timeouts | Results page only displays stored runs |
| ADR-009 | v1 has no actuation code | DECIDED (Half 2 deferred) | Mains safety; scope | Control must be a separate, approved milestone |
| ADR-010 | Rule-based decision engine first; ML only if it beats it | DEFAULT | Honest baseline; small data | Learned model is optional |
| ADR-011 | MCP/LLM are read-only presentation layers outside the critical path | DEFAULT | Prompt-injection and safety risk | Stretch only; see 06_AIRD |
| ADR-012 | New code in `cem_gw/` package; `fleet_gateway.py` is a thin shim (M0: file was missing, so the shim was created; seam = mount routes only) | DEFAULT | Nothing to preserve; easy review | Swap-cost stays low (pure functions, thin handlers) |
| ADR-013 | **Firestore (asia-south1) as the only datastore** — replaces SQLite | DECIDED | Firebase Auth integration, managed scaling, real-time listeners for fleet page, no local DB ops | Occupancy data in Google Cloud (mentor/facilities approval required); cost monitoring; backup via gcloud export |
| ADR-014 | Flask as the web shim | DEFAULT (D-017) | Owner deferred the framework choice but ordered continuation; Flask is minimal/sync; swap stays cheap | Revisit if the owner provides a framework |
| ADR-015 | Reversible dev/test seams: `CEM_DB_MODE=memory\|firestore`, `CEM_AUTH_MODE=dev\|firebase` (prod defaults), `CEM_DEV_ADMIN` bootstrap | DEFAULT (D-018) | Unblocks local dev/tests until the Firebase project exists | Never production; dev mode warns on boot |

## 5. Technology risks
| Risk | Mitigation |
|---|---|
| ESP32 HTTPS with pinned/self-signed certificate is fiddly | Spike early; Firebase Custom Tokens over standard HTTPS (no custom cert pinning needed) |
| Browser warnings for self-signed certificates | Ask campus IT for a certificate or install a CA on lab machines |
| Firestore cost / quota limits | Monitor reads/writes/deletes; budget alerts; batch writes; cache fleet page data |
| Firebase Auth outage blocks login | Data collection unaffected (nodes use custom tokens); admin can create local emergency user if needed |
| Data residency compliance | Mentor/facilities sign-off for asia-south1 region before M1 |

## 6. Out of scope architecture
Multi-tenant hosting, horizontal scaling, message brokers, container orchestration. (Firestore is in scope per ADR-013.)
