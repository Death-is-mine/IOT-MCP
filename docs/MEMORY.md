# MEMORY — Living project log

Read this at the start of every session. Update it at the end of every session. Keep it short and current; delete stale facts instead of piling them up. Never remove a **[DECIDED]** entry without the owner's instruction.

## 1. Protocol
1. Start: read AGENTS.md, this file, then the docs listed for the current milestone.
2. During: when you learn something durable (framework, command, constraint, decision), write it here immediately.
3. End: update the milestone board, add a session-log entry (newest first), list open questions.
4. Never store secrets, tokens, personal data, or contact details here.
5. If this file conflicts with a document, follow the precedence in docs/00_INDEX.md §4 and record the resolution under Decisions.

## 2. Decisions
| ID | Decision | Status | Date |
|---|---|---|---|
| D-001 | Build Half 1 first (fleet view, quality flags, labelling, export, evaluation); Half 2 (control) later | DECIDED | 2026-10 |
| D-002 | Keep existing `fleet_gateway.py`; extend it, add `/poll` | DECIDED | 2026-10 |
| D-003 | Campus-only, behind HTTPS, no public internet exposure | DECIDED | 2026-10 |
| D-004 | Plain HTML page, no build step | DECIDED | 2026-10 |
| D-005 | Nodes push data; the gateway never commands nodes; any future control is pull via `/poll` | DECIDED | 2026-10 |
| D-006 | Earlier idea of a shared read-only token is superseded by per-user login; confirm with owner (O-9) | DEFAULT | 2026-10 |
| D-007 | Control design (future): command whitelist, audit log of everything, HMAC-signed commands with timestamp and nonce/counter, expiry, nothing left stuck | DECIDED | 2026-10 |
| D-008 | Owner prefers Firebase Authentication (free tier) over Supabase; build auth behind an interface with a local fallback until O-1 is answered | DECIDED (preference) / OPEN (mode) | 2026-10 |
| D-009 | Transport: HTTP push with sequence numbers, not MQTT | DEFAULT | 2026-10 |
| D-010 | SQLite WAL as the only datastore | DECIDED | 2026-10 |
| D-011 | Charts: uPlot, vendored locally | DEFAULT | 2026-10 |
| D-012 | v1 contains no actuation code; `CEM_CONTROL_ENABLED=false` | DECIDED | 2026-10 |
| D-013 | The project is positioned as measurement and comparison, not invention; no hype in code or copy | DECIDED | 2026-10 |
| D-014 | Owner wants honest pushback and calibrated verdicts, no flattery | DECIDED | 2026-10 |
| D-015 | Datastore is Firestore (asia-south1); MEMORY D-010 SQLite overturned by owner ruling 2026-10-05 in favour of ADR-013/TRD | DECIDED | 2026-10 |
| D-016 | Auth mode is Firebase Auth (users) + Firebase Custom Tokens (nodes), no local fallback, per owner ruling 2026-10-05 (resolves D-008 mode + O-1 default) | DECIDED | 2026-10 |
| D-017 | Web framework: Flask (owner deferred choice, told agent to continue; thin shim + pure `cem_gw/` so swap is cheap; revisit when owner provides) | DEFAULT | 2026-10 |
| D-018 | Dev/test seams (reversible, never production): `CEM_DB_MODE=memory|firestore` (default firestore) and `CEM_AUTH_MODE=dev|firebase` (default firebase); memory/dev used for local dev + tests until Firebase project exists | DEFAULT | 2026-10 |

## 3. Open questions
O-1 Google Workspace emails? Firebase or local login · O-2 framework of `fleet_gateway.py` · O-3 TLS pinning vs isolated network + signing · O-4 mmWave or CO2 · O-5 timetable source and permission · O-6 mini-PC OS and admin · O-7 pilot rooms and node count · O-8 facilities/mentor approvals · O-9 confirm shared token retired · O-10 LLM provider (stretch). Details and defaults in docs/00_INDEX.md §8.

## 4. Environment facts (M0 discovery 2026-10-05)
- `fleet_gateway.py`: DOES NOT EXIST in workspace or in GitHub repo (empty repo `Death-is-mine/IOT-MCP` created public 2026-10-05). Nothing to preserve; M0 plan creates it as a minimal thin shim.
- Local dir linked + pushed 2026-10-05: commit 67aaaf3 on `main`, tracks `origin/main` (was: not a git repo).
- Python: 3.11.9 (`python`, meets NFR-006 ≥3.11) + pip 24.0; `python3` is 3.14.0. Use 3.11 for dev.
- OS dev machine: Windows (win32). Mini-PC OS/admin: unknown → [DEFAULT] Linux + systemd per docs (O-6).
- Existing endpoints/behaviours to preserve: none.
- Integration seam for `cem_gw/`: `fleet_gateway.py` imports and mounts `cem_gw` routes only; all logic in `cem_gw/` pure functions (per TRD §2 layout).
- GitHub: public repo https://github.com/Death-is-mine/IOT-MCP exists (empty, no README).
- Commands (confirmed): Test `pytest -q` · Lint `ruff check .` · Coverage `coverage run -m pytest tests/ -q` · Simulate `python tools/simulator.py --scenario normal_day --nodes 3 --days 2 --seed 1` · Run `python fleet_gateway.py` (dev: CEM_DB_MODE=memory CEM_AUTH_MODE=dev CEM_DEV_SECRET=... CEM_DEV_ADMIN=you@x)
- Dev runbook (2026-10-05, smoke-verified): boot with dev env → `python tools/create_node.py --gateway ... --admin-token dev-user:<admin>:<secret> --node-id <id> --room <room>` → post history with simulator (`--bearer dev-node:<id>:<secret>`; one simulator run per node-id; day replays flag BACKFILLED/CLOCK_DRIFT by design) → near-live demo via `--minutes N --end-now` on a fresh node-id → browse `/fleet /node /label /export /eval /admin` (paste token). Simulator honours 429/Retry-After; `--node-id/--room/--labels-out/--dry` available.
- Dependencies added (with reason): flask (web shim, thin handlers), firebase-admin (Firestore + Firebase Auth, DECIDED), waitress (prod WSGI), tzdata (ZoneInfo on Windows), pytest/ruff/coverage (test/lint), numpy (already present; eval stats use stdlib only for now), playwright + pytest-playwright (E2E suite `tests/e2e/`: live-server agent flows + Chromium human flows; browsers via `playwright install chromium`, pinned like the rest), mcp + uvicorn (read-only MCP server AIRD S1: official MCP SDK Streamable HTTP + local runner; env needed `typing_extensions` bump for pydantic-core)
- vendored uPlot 1.6.32 (npm tarball): uPlot.iife.min.js sha256:19c8d4c6…f1f, uPlot.min.css sha256:df630c6a…35fa (full hashes in tests/contract/test_node_ui.py; changing uPlot breaks that test by design)
- vendored Firebase Auth 10.12.2 compat builds (`static/vendor/firebase-app-compat.js` 31KB + `firebase-auth-compat.js` 140KB, gstatic; reason: no runtime CDN per AGENTS/SEC-11; compat UMD chosen because modular ESM files pull further CDN chunks at runtime and are blocked by CSP; web apiKey in `static/login.js` is a public client identifier, not a secret)
- CONFLICT noted at M0 (needs owner ruling, precedence 00_INDEX §4 says TRD/ARD beat MEMORY, but AGENTS.md forbids changing [DECIDED] without asking): MEMORY D-010 says SQLite WAL DECIDED, but ADR-013 (04_ARD) + TRD §1 say Firestore asia-south1 DECIDED. Likewise D-008 local-fallback OPEN vs ADR-005 no-local-fallback DECIDED.
- RESOLVED 2026-10-05 by owner: Firestore (D-015), Firebase Auth no-local-fallback (D-016), framework Flask DEFAULT reversible (D-017), dev seams memory/dev (D-018) + CEM_DEV_ADMIN bootstrap (dev only)

## 5. Milestone board
| MS | Status | Notes |
|---|---|---|
| M0 Discovery | done | fleet_gateway.py was missing; Flask DEFAULT (D-017); AC-01 met |
| M1 Ingest + DB + simulator | done | TC-ING-01..10, TC-OP-05; idempotent atomic ingest; 429+413 Level |
| M2 Flags + Fleet page | done | TC-QF-01..12; incremental engine O(new); fleet columns per FR-030 |
| M3 Node page | done | uPlot 1.6.32 vendored+hashed; aligned series; flag bands; TC-UI-02/03/05 |
| M4 Auth + audit + node admin | done | role matrix; hash-chained audit; one-time node tokens; 2 Firebase TCs skipped (need test project) |
| M5 Labelling + export | done | immutable+supersede; conflicts; coverage; deterministic zip+manifest; TC-LB/EX |
| M6 Evaluation | done | 5 rule configs x holds; hand-computed goldens; bootstrap CIs; labelled hours everywhere |
| M7 Hardening + acceptance | done (code) / open (field) | 81 passed 2 skipped, ruff clean, flags+eval coverage 90%; memory backup/restore OK; live HTTP smoke OK; PENDING owner/prod: Firebase project, gcloud backup drill, 7-day run, calibration + 30/30 ground-truth hours |

## 6. Known issues and risks
- RESOLVED 2026-10-05: local dir initialized, committed (67aaaf3), pushed to `main` on GitHub (was: not a git repo, empty remote).
- Simulator replays share seqs per seed: one simulator run per node-id, else duplicates (correctly deduped). Use fresh node-ids or accept.
- Day-long replay is honestly flagged BACKFILLED/CLOCK_DRIFT; `--minutes N --end-now` demos near-live data.
- Standing risks: scarce ground truth, ESP32 ADC accuracy, prod ingest/auth untested against real backend (owner provided Firebase project `iot-mcp` + web app config 2026-10-06; console providers Email/Google/Phone still need enabling by owner; service-account + prod smoke pending), no 7-day unattended run yet.

## 7. Session log (newest first)
2026-10-06 · Reconcile + push · found concurrent session's uncommitted work (login/e2e/MCP/CI); my fresh login.html/login.js had overwritten theirs — reconstructed to e2e contracts (4 tabs, dev-token IDs, vendored SDK, placeholder web config) and verified: 105 passed 2 skipped incl. 18 e2e in real Chromium, ruff clean · STILL NEEDS owner: Firebase web apiKey/authDomain/projectId to paste into static/login.js + enable Email/Google/Phone providers, then firebase-mode prod smoke · next: push + watch CI green
2026-10-06 · Human walkthrough + MCP server · screenshots of all 9 pages as a real user (seeded day: 2 nodes, labels, eval run), 0 JS errors; walkthrough caught 3 real bugs, all fixed: (1) ingest never recorded `fw_version` (fleet FW column always empty; `apply_batch(..., fw_version=None)` default, handler passes batch value), (2) node chart x-axis showed epoch dates (uPlot treats numbers as unix-ts; explicit min-formatter now), (3) export GET 500 with default relative dir (POST wrote cwd-relative, `send_file` resolved against Flask root `cem_gw/`; both handlers now `abspath`; regression TC-EX-05) · MCP server A-5/FR-100 shipped (`mcp_server.py` + `cem_gw/mcp_server.py`: official SDK, Streamable HTTP `/mcp` stateless, 6 read-only tools over gateway GETs, Bearer gate + per-caller rate limit, outputs stripped of notes/labellers/emails, per-invocation logging with caller hash; AIRD "SQLite read-only" superseded by D-015 Firestore→HTTP) · tests: 10 new (TC-MCP-01..05 unit, TC-MCP-10..14 live-client e2e incl. 401/429 paths; MCP client calls run on an isolated thread — browser tests leave main loop running) · 105 passed 2 skipped, ruff clean · untested: CI run on GitHub (needs push), real-Firebase sign-in, MCP against prod gateway (needs viewer token + hourly-refresh loop for Firebase ID tokens) · next: push + watch CI green · blocked: Firebase console access, mini-PC, hardware
2026-10-06 · E2E suite (Playwright) · `tests/e2e/` (13 tests: agent register/ingest-idempotent/poll-empty-commands/reject-states/allowlist-deny + human auth-gate/login/fleet/node-charts/label/export-zip/eval-run/admin/logout/CSP headers) on session live server (ephemeral port; `CEM_E2E_BASE_URL` override, no hardcoded host); `pytest -m "not e2e"` vs `-m e2e` split; CI `.github/workflows/ci.yml` (test job + e2e job with chromium + trace artifacts) · bugfixes found by E2E: inline module scripts blocked by CSP (auth gate never ran; `static/auth.js` now classic auto-init, TC-UI-05 test hardened to reject any inline script/style), export download link lacked Bearer token (now authorized fetch→blob), hidden `<option>` waits need `state="attached"` · 94 passed 2 skipped, ruff clean · untested: CI run on GitHub (needs push), real-Firebase sign-in still pending owner console setup · next: push + watch CI green, then firebase-mode prod smoke
2026-10-06 · Firebase login UI · `/login` (Email+Password, Google popup, Phone+invisible reCAPTCHA, Dev-token tab for dev seam) backed by vendored compat SDK; token stored as `cem_token`; all pages redirect to `/login` when absent; dead token inputs removed from page JS; CSP carved per SSD SEC-11 (`csp_for()`: firebase origins only in firebase mode, dev stays self-only); fixed `tools/simulator.py` missing `urllib.request` import + ruff I001s · 81 passed 2 skipped (Firebase TCs), ruff clean, live dev smoke OK (/login, compat SDK + login.js serve, dev CSP strict) · untested: real Firebase sign-in against `iot-mcp` (needs console providers + allowlisted user + prod smoke) · next: owner enables Email/Google/Phone providers, allowlists first admin, then firebase-mode prod smoke · blocked: Firebase console access, mini-PC, hardware
2026-10-05 · M0-M7 build · full v1 app built in memory/dev seams: 81 passed, 2 skipped (Firebase TCs), ruff clean, flags+eval coverage 90%; live HTTP smoke (register→ingest 17k→fleet ONLINE→flags→readings) passed; decisions D-015..D-018 recorded · next: owner creates Firebase project + git link/push, then prod evidence (gcloud drill, 7-day run, calibration, 30/30 label hours) · blocked: Firebase project, mini-PC, hardware
2026-10-05 · M0 · owner ruled Firestore (D-015) + Firebase Auth, no local fallback (D-016); framework deferred — owner will provide (D-017, O-2 OPEN); no code written per kickoff rule · next: owner provides framework/file, then scaffold + link local→remote + M1 · blocked: web framework
