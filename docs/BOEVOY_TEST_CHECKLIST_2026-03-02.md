# BOEVOY Test Checklist (Gemini-only First)

Progress formula: `completed / total * 100`

Current progress: `7 / 41 = 17.1%`

## Phase 1 — Runtime Baseline & Safety Gates
- [x] T01 Configure Gemini-only mode and disable risky/high-cost modules for initial test wave.
- [x] T02 Restart VITO and verify single running instance (no duplicate system/user loop).
- [x] T03 Validate key command suites (`llm_router`, `decision_loop`, `conversation_engine`, `comms_agent`).
- [x] T04 Run full `tests/` regression in current mode.
- [x] T05 Confirm no proactive spam goals for 1 full interval window in runtime logs.

## Phase 2 — Core Dialogue + Task Lifecycle
- [ ] T06 `/start` + `/help` UX validation in Telegram (daily/rare/system sections).
- [ ] T07 `/goal` creation from owner message; verify goal appears in queue.
- [ ] T08 `/status` and `/report` consistency with actual loop and DB.
- [ ] T09 `/cancel` hard pause + `/resume` recovery.
- [ ] T10 `/task_current`, `/task_done`, `/task_replace` lifecycle.

## Phase 3 — Orchestration + Approvals + Resume/Cancel
- [ ] T11 Trigger approval-required action and validate `/approve` path.
- [ ] T12 Trigger approval-required action and validate `/reject` path.
- [ ] T13 Validate interrupt persistence in DB (`workflow_interrupts`, `workflow_sessions`).
- [ ] T14 Validate cancelled workflow does not auto-resume unexpectedly.
- [ ] T15 Validate resume after resolved interrupt restores expected state.

## Phase 4 — Memory + Skills + Preferences
- [ ] T16 Validate owner preference save/read (`/prefs`, `/prefs_metrics`).
- [ ] T17 Validate memory block write/read for key decisions.
- [ ] T18 Validate skill creation/update path on successful goal completion.
- [ ] T19 Validate anti-pattern/error capture path for failed runs.
- [ ] T20 Validate weekly memory/skill report generation script output.

## Phase 5 — Tooling/Registry/Discovery (Safe Mode)
- [ ] T21 Validate tooling registry list/contract visibility.
- [ ] T22 Validate tooling policy gates (allowlist/budget) block disallowed runtime action.
- [ ] T23 Validate discovery remains disabled in safe phase (`TOOLING_DISCOVERY_ENABLED=false`).
- [ ] T24 Validate governance report generation without auto-remediation side effects.

## Phase 6 — Publishing/Platform Dry-Run Flows
- [x] T25 Test posting dry-run flow end-to-end (prepare -> queue -> inspect).
- [x] T26 Test manual queue run (`/pubrun`) with evidence capture.
- [ ] T27 Test web operator listing and one safe scenario run.
- [ ] T28 Test platform registration flow on sandbox/test account (site #1).
- [ ] T29 Test platform registration flow on sandbox/test account (site #2).
- [ ] T30 Validate attachment-first flow (photo/doc/video parse and action mapping).

## Phase 7 — Revenue/Finance/Observability
- [ ] T31 Validate finance snapshot and spending guardrails.
- [ ] T32 Validate revenue engine remains disabled in this phase.
- [ ] T33 Validate dashboard API/health and key core cards.
- [ ] T34 Validate logs and error surfacing (`/logs`, `/errors`, `/health`).
- [ ] T35 Validate balance checks across configured providers.

## Phase 8 — Deferred Modules (Later)
- [ ] T36 Self-healer controlled scenario (safe command path).
- [ ] T37 Self-healer rollback scenario (forced fail path).
- [ ] T38 Brainstorm end-to-end scenario (cost/quality/evidence).

## Phase 9 — Provider Expansion + Final Combat Mode
- [ ] T39 Connect remaining provider keys/services and verify connectivity.
- [ ] T40 Disable Gemini-only force and restore full router strategy.
- [ ] T41 Final full regression + live smoke sequence + release readiness report.

## Evidence Notes
- For each task store: command, short output, key log line, DB proof (if relevant), pass/fail.
- 2026-03-04: Mega Agent Audit completed (`PYTHONPATH=. python3 scripts/mega_agent_audit.py`) -> `reports/VITO_AGENT_MEGATEST_2026-03-04_1136UTC.json`, combat readiness `23/23 = 100%`.
- 2026-03-04: Validation test passed (`pytest -q -c /dev/null tests/test_agent_megatest.py`) -> `1 passed`.
- 2026-03-04: Live publish matrix executed (`PYTHONPATH=. python3 scripts/live_publish_matrix.py --live`) -> `reports/VITO_PUBLISH_MATRIX_LIVE_2026-03-04_1141UTC.json`.
- 2026-03-04: Social live probe executed (`SOCIAL_LIVE_ALLOW_TWITTER=1 PYTHONPATH=. python3 scripts/social_live_probe.py`) -> `reports/VITO_SOCIAL_LIVE_PROBE_2026-03-04_1141UTC.json`.
- 2026-03-04: Agent->Platform live combat audit executed (`PYTHONPATH=. python3 scripts/live_agent_platform_audit.py`) -> `reports/VITO_AGENT_PLATFORM_LIVE_AUDIT_2026-03-04_1146UTC.json`, responding paths `7/7 = 100%`.
- 2026-03-04: Etsy switched to browser-only mode (`ETSY_MODE=browser_only`), API write-path bypassed in platform layer.
- 2026-03-04: Agent->Platform live audit re-run after Etsy browser-only + auth precheck in ecommerce agent -> `reports/VITO_AGENT_PLATFORM_LIVE_AUDIT_2026-03-04_1156UTC.json`, responding paths `7/7 = 100%` (Etsy status: `needs_browser_login` until storage capture).
- 2026-03-04: Gumroad hard safety policy: no fallback to old listings without explicit target id/slug and owner confirmation (`platforms/gumroad.py`, `agents/ecommerce_agent.py`).
- 2026-03-04: Controlled single-product Gumroad cycle (`python3 scripts/gumroad_test_cycle.py ...`) -> `reports/VITO_GUMROAD_TEST_CYCLE_2026-03-04_1218UTC.json`, result: `daily_limit` (no modifications to existing listing).
- 2026-03-04: Gumroad target-only update cycle (single listing `yupwt`, `target_product_id=PKIVW0rjiJ_L_6ugL_5q7w==`) successfully published with updated fields and assets -> `reports/VITO_GUMROAD_TEST_CYCLE_2026-03-04_1248UTC.json`.
- 2026-03-04: Full-cycle verified on single target listing (`draft profile -> publish -> back to draft`) with browser+API proof and checks = PASS -> `reports/VITO_GUMROAD_FULL_CYCLE_2026-03-04_1333UTC.json`.
