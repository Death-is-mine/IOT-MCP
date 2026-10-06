# 07 — Security & Safety Design (SSD)

Version 0.1 draft · 2026-10-05. This document has the highest precedence. v1 is **monitor-only**: it never switches a circuit.

## 1. Assets and actors
Assets: occupancy and power data, node keys, user accounts, audit log, labels. Later (not v1): control path to a mains-adjacent relay.
Actors: owner/admin, labellers, viewers, nodes, other campus-network users (untrusted), outsiders (should not reach the service).

## 2. Threats and controls (STRIDE-lite)
| Threat | Control | ID |
|---|---|---|
| Unauthenticated access to data | Every data route requires auth; deny by default | SEC-01 |
| Node impersonation | Per-node 256-bit token; SHA-256 hash at rest; constant-time compare; shown once | SEC-02 |
| Traffic sniffing/tampering | TLS in production; ESP32 pins the gateway certificate (O-3); fallback mode below | SEC-03 |
| Injection (SQL, XSS, CSV) | Parameterised SQL only; output encoding; strict schema validation; CSV formula neutralisation | SEC-04, SEC-08 |
| Abuse/DoS from a node or client | Body-size cap, per-node rate limit, request timeouts | SEC-05 |
| Privilege escalation | Role checks server-side on every route; UI hiding is cosmetic | SEC-06 |
| Repudiation / tampering with history | Append-only audit log (DB triggers + hash chain); labels immutable | SEC-07 |
| Secret leakage | No secrets in repo, logs, or error messages; `.env` ignored; secret scan in CI | SEC-09 |
| Session theft / CSRF | No session cookies are issued in any mode: every request carries a Bearer token, so there is no cookie to steal and no CSRF surface; tokens expire per Firebase/issuer policy; dev tokens require `CEM_DEV_SECRET` | SEC-10 |
| Cross-origin and script injection | No CORS; CSP without inline scripts; local vendored scripts; Firebase origins allowed only in firebase mode | SEC-11 |
| Unintended actuation | No actuation code in v1; `CEM_CONTROL_ENABLED=false`; `/poll` returns no commands; module for control absent | SEC-12 |
| Privacy harm | No cameras/audio/identifiers; occupancy boolean per room; initials only; notice posted; retention below | SEC-13 |
| Data loss/disclosure via backups | Backups on separate disk, restricted permissions, restore tested | SEC-14 |
| Prompt injection via AI tools | AIRD §6 read-only MCP, no free text returned | SEC-15 |

## 3. Roles and permissions
| Capability | viewer | labeller | admin |
|---|---|---|---|
| Fleet, node, results, label coverage | ✓ | ✓ | ✓ |
| Create/supersede labels | | ✓ | ✓ |
| Export | ✓ | ✓ | ✓ |
| Run evaluation, import timetable | | | ✓ |
| Manage users/nodes/keys, view audit, backup/restore | | | ✓ |

## 4. Transport options
**Default:** HTTPS via reverse proxy (standard CA cert); node verifies server cert normally. Firebase Custom Tokens provide authentication (no per-request HMAC needed). **Fallback (lab only):** HTTP on isolated VLAN with per-request HMAC-SHA256 over `node_id | batch_id | SHA-256(body)` using per-node secret. The fallback is specified but not implemented unless required.

## 5. Authentication details
**Firebase Auth (Email/Google/Phone):** verify ID token signature and claims via Firebase Admin SDK; require verified email; role from custom claims (`viewer`/`labeller`/`admin`); the caller must ALSO be allowlisted and active in the `users` table (deny by default). No local fallback in v1.

**Nodes (Firebase Custom Tokens):** backend mints a custom token via `firebase_admin.auth.create_custom_token("node:<node_id>", …)` and shows it once; the node exchanges it for an ID token and presents that as `Bearer`; gateway verifies via Admin SDK `verify_id_token()` and extracts `node_id` from the `uid` claim. No token stored on server; rotation = mint new token; disabled nodes are rejected.

## 6. Privacy and consent
- Collect: power/current, PIR/mmWave presence, CO2, lux, temperature, humidity per room. Do not collect: images, audio, device identifiers, names of students or staff.
- Labels carry labeller initials only; timetable carries course code only, no instructor names.
- Post a notice in pilot rooms describing what is sensed and why; obtain facilities/mentor approval (O-8).
- Retention: raw data kept for the practicum and report period, then deleted or anonymised as agreed; exports contain no personal data.
- **Occupancy data stored in Firestore (asia-south1, Google Cloud).** Firebase Auth receives only authentication traffic (ID tokens, custom tokens). Mentor/facilities sign-off required for cloud residency (ADR-013).

## 7. Safety (mains)
| ID | Rule |
|---|---|
| SAF-01 | v1 is monitoring only. No relay is driven by any v1 software. |
| SAF-02 | Any future switching requires the go/no-go in 10_ACCEPTANCE.md §6, mentor and facilities sign-off, and a separate milestone. |
| SAF-03 | Sensing uses split-core current clamps (no cutting wires) and an isolated voltage module; all mains-side parts in an enclosure with fusing; no exposed mains on a bench or demo table. |
| SAF-04 | Mains-side installation is done or supervised by a qualified electrician with mentor approval. |
| SAF-05 | If switching is ever added: fail-safe default is power ON; hardware watchdog; manual override; relay/contactor rated for inductive loads; local node enforces command expiry and reverts to safe default. |
| SAF-06 | Scope limited to classroom lights and fans; never emergency lighting, sockets, projectors, IT equipment, or labs. |
| SAF-07 | The system is a diagnostic aid, not a safety device. No arc-fault, fire, or protection claims anywhere. |
| SAF-08 | Demos use low-voltage AC from an isolation transformer or recorded data, not live mains on a table. |

## 8. Future control design (Half 2, specification only — do not implement in v1)
Pull model: the node polls; the gateway never connects to the node. Commands are drawn from a whitelist (e.g., `set_mode shadow|active`); raw relay toggling is not allowed. Each command carries `cmd_id`, `counter`, `issued_ts`, `expires_ts`, `cmd`, `params`, and `HMAC-SHA256` over their canonical form with a per-node key. The node verifies: signature, counter greater than its stored counter (persisted in flash), not expired, command whitelisted, parameters within bounds. The node enforces expiry locally and returns to its safe default; nothing is left stuck. Everything is audit-logged on both sides.

## 9. Security testing
See 09_TEST_PLAN.md: TC-SEC-01..12 and the authorisation matrix tests TC-AU-*.
