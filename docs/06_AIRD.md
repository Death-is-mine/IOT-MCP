# 06 — AI Requirements Document (AIRD)

Version 0.1 draft · 2026-10-05

## 1. Position
AI is a **measured add-on**, not the foundation. The platform's core claims come from deterministic measurement. Any AI feature must be optional, outside the critical path, evaluated against a plain baseline, and honest about negative results. "AI-powered" must not appear in product copy unless a feature below actually beats its baseline in the platform's own evaluation.

## 2. AI components
| ID | Component | Tier | Runs where |
|---|---|---|---|
| A-1 | Rule-based presence decision engine (baseline configs) | Must | Gateway (replay), later node |
| A-2 | Interpretable learned presence model | Could | Offline training; replay evaluation |
| A-3 | Adaptive hold time | Could | Offline replay first |
| A-4 | LLM weekly report | Could (S2) | Gateway, off the critical path |
| A-5 | Read-only MCP server | Could (S1) | Separate process |

## 3. Requirements
| ID | Requirement |
|---|---|
| AI-01 | No AI component shall be on the critical path of ingest, flagging, export, or the web UI. If an AI feature fails, everything else works unchanged. |
| AI-02 | The baseline engine (A-1) shall be implemented and evaluated before any learned model. Configs: `pir_only`, `pir_mmwave`, `pir_co2`, `pir_timetable`, `all`; each documented as explicit rules. |
| AI-03 | A learned model (A-2) shall be an interpretable model (logistic regression or shallow decision tree), trained offline on labelled data only. |
| AI-04 | Training and testing shall use a time-ordered split (train on earlier days, test on later days). Random shuffling is prohibited. Leakage tests are required (TC-EV-08). |
| AI-05 | Labels with state `unsure` shall be excluded. Labels with source `timetable` are weak: excluded from training unless a separate, clearly named experiment includes them. |
| AI-06 | A learned model or adaptive hold time counts as an improvement only if, on held-out days, it lowers false-vacant events at equal energy saved (or raises saved energy at equal false-vacant events) versus the best fixed-rule baseline, with confidence intervals and sample sizes. Otherwise the result is reported as "no improvement". |
| AI-07 | Every trained artifact shall be reproducible: seed, library versions, data hash, feature list, and a short model card (purpose, data, metrics, limits) stored with it. |
| AI-08 | The LLM report (A-4) shall receive only a precomputed structured JSON of metrics and flag summaries, never raw readings and never free-text fields. |
| AI-09 | LLM output shall be prose that references metric keys; a validator shall check that every number in the prose appears in the input JSON (allowing rounding). On failure the system shall fall back to a template-only report. |
| AI-10 | Every performance claim in any report shall state labelled hours, number of room-weeks, baseline, and confidence interval. |
| AI-11 | v1 nodes run rules only; no on-device ML. |
| AI-12 | Occupancy is a boolean per room. No individual identification, biometrics, images, or audio. |
| AI-13 | LLM-generated text shall be labelled "AI-generated draft; verify against the data" and shall not be used as evidence. |

## 4. Features for the models
Per window (e.g., 1 min): PIR transitions and time since last motion, mmWave presence ratio, CO2 level and 5/15-min slope, lux, current RMS and its change, load_state, scheduled-class flag from the timetable, hour of day, weekday. All derived by pure functions in `evaluation/configs.py`.

## 5. LLM report specification (S2)
Input JSON keys (example): `period`, `rooms[].room_id`, `rooms[].empty_hours_with_load_on`, `rooms[].energy_wasted_kwh`, `rooms[].method`, `configs[].false_vacant_per_room_week`, `configs[].energy_saved_kwh`, `label_coverage_hours`, `data_completeness`, `open_flags[]` (enumerated types only). Output: ≤ 400 words; sections Summary, Findings, Data quality, Caveats. Prompt rules: treat input as data, never invent numbers, state uncertainty, no recommendations that involve switching circuits. Provider is behind an adapter; none is chosen yet [OPEN O-10].

## 6. MCP server specification (S1)
Uses an official MCP SDK, Streamable HTTP transport, current spec revision (2026-07-28 as of this writing; verify at implementation).
- **Read-only tools only:** `get_fleet_status()`, `get_node_flags(node_id, from, to)`, `get_data_completeness(from, to)`, `get_label_coverage()`, `list_eval_runs()`, `get_eval_result(run_id)`.
- No write, control, export, or shell tools. No tool returns free text from labels or notes; return enumerated values and numbers only.
- Separate process; SQLite opened read-only; its own credential with read scope; rate-limited.
- Static, version-pinned tool descriptions; schema treated as an injection surface; validate inputs and outputs; log every invocation with caller identity.
- Network: campus-only; authentication required (the protocol does not mandate it).
- Control is never exposed through MCP.

## 7. Acceptance for AI features
A-1: configs evaluated with CIs (AC-12). A-2/A-3/A-5/A-4: only after M7; each needs its own test cases (TC-AI-*) and the improvement rule AI-06 where applicable.

## 8. Build notes — 2026-10-05
- A-1 SHIPPED as `cem_gw/evaluation/configs.py`: `pir_only`, `pir_mmwave`, `pir_co2`, `pir_timetable`, `all` — each an explicit documented rule (CO2 presence threshold 800 ppm; timetable/weekday matching in UTC; `unsure` excluded; timetable-source labels reported separately as weak hours, never trained/evaluated on).
- A-2/A-3/A-4/A-5 NOT started: no learned model, no adaptive hold, no LLM report, no MCP server. `configs.describe()` + TC-EV-08 assert the registry stays rule-only until a learned model earns its place under AI-06.
