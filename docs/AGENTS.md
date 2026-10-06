# AGENTS.md — CEM (Classroom Energy Monitor) fleet gateway

Keep this file short. Details live in `docs/`. If anything here conflicts with `docs/07_SSD.md`, the SSD wins.

## What we are building
A campus-only gateway and web UI for ESP32 energy/presence nodes: ingest, data-quality flags, ground-truth labelling, reproducible export, and an offline evaluation of energy saved vs wrong cut-offs. Entry point `fleet_gateway.py` (created at M0 — it did not exist) mounts `cem_gw/` routes. It is a measurement project, **not** a smart switch and **not** a safety device.

## Start every session
1. Read `docs/MEMORY.md` (decisions, environment facts, milestone board).
2. Read the docs for the current milestone (`docs/00_INDEX.md` lists them). SRD requirement IDs are your task list.
3. Work on **one milestone at a time**. Stop for owner review at the end of each milestone.

## Hard rules (never)
- Never add code that switches, commands, or actuates anything. v1 is monitor-only. `/poll` returns an empty `commands` list. `CEM_CONTROL_ENABLED` stays `false`.
- Never expose the service to the public internet.
- Never commit or log secrets, tokens, `.env`, or personal data. Never hard-code credentials.
- Never rewrite `fleet_gateway.py`; make minimal edits and put new code in `cem_gw/`.
- Never use string-built queries; use Firestore SDK methods with parameter binding.
- Never add a frontend build step, a CDN script at runtime, or a dependency without recording the reason in `docs/MEMORY.md`.
- Never edit or delete raw readings, labels, or audit rows.
- Never change a **[DECIDED]** item; ask the owner.
- Never invent numbers, benchmarks, or claims in code, UI text, or reports. Any figure comes from the platform's own data and states its method and sample size.

## Always
- Write tests first for flag rules and evaluation metrics, using hand-computed golden data (`tests/golden/`).
- Store time as UTC epoch milliseconds; display Asia/Kolkata.
- Use the simulator (`tools/simulator.py`) for development; no hardware is needed for v1.
- Keep handlers thin; business logic in pure, tested functions.
- Reference SRD/TC IDs in commit messages and tests.
- When a decision is unclear, use the **[DEFAULT]**, put it behind a config flag, and record it in `docs/MEMORY.md`. Ask only when a choice is irreversible or touches safety, security, or privacy.
- Treat every free-text field as untrusted (XSS, CSV injection, prompt injection).

## Commands (confirmed M0, details in `docs/MEMORY.md`)
- Test: `pytest -q` · Lint: `ruff check .` · Coverage: `coverage run -m pytest tests/ -q` · Simulate: `python tools/simulator.py --scenario normal_day --nodes 3 --days 2 --seed 1`
- Run: `python fleet_gateway.py` (dev: `CEM_DB_MODE=memory CEM_AUTH_MODE=dev CEM_DEV_SECRET=... CEM_DEV_ADMIN=you@x`)

## Where things are
`docs/01_PRD` why · `02_SRD` what (tasks) · `03_TRD` schema/API/stack · `04_ARD` quality targets and ADRs · `05_ADD` design · `06_AIRD` AI rules · `07_SSD` security/safety/privacy · `08_DATA_PIPELINE` flags, metrics, export · `09_TEST_PLAN` tests · `10_ACCEPTANCE` done criteria · `MEMORY.md` living log.

## End every session
Update `docs/MEMORY.md`: milestone board, decisions, open questions, session-log entry. Report what changed, what is untested, and what you need from the owner.
