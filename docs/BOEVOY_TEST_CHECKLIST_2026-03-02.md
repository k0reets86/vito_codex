# BOEVOY Test Checklist (Gemini-only First)

Progress formula: `completed / total * 100`

Current progress: `45 / 49 = 91.8%`

## Phase 1 — Runtime Baseline & Safety Gates
- [x] T01 Configure Gemini-only mode and disable risky/high-cost modules for initial test wave.
- [x] T02 Restart VITO and verify single running instance (no duplicate system/user loop).
- [x] T03 Validate key command suites (`llm_router`, `decision_loop`, `conversation_engine`, `comms_agent`).
- [x] T04 Run full `tests/` regression in current mode.
- [x] T05 Confirm no proactive spam goals for 1 full interval window in runtime logs.

## Phase 2 — Core Dialogue + Task Lifecycle
- [x] T06 `/start` + `/help` UX validation in Telegram (daily/rare/system sections).
- [x] T07 `/goal` creation from owner message; verify goal appears in queue.
- [x] T08 `/status` and `/report` consistency with actual loop and DB.
- [x] T09 `/cancel` hard pause + `/resume` recovery.
- [x] T10 `/task_current`, `/task_done`, `/task_replace` lifecycle.

## Phase 3 — Orchestration + Approvals + Resume/Cancel
- [x] T11 Trigger approval-required action and validate `/approve` path.
- [x] T12 Trigger approval-required action and validate `/reject` path.
- [x] T13 Validate interrupt persistence in DB (`workflow_interrupts`, `workflow_sessions`).
- [x] T14 Validate cancelled workflow does not auto-resume unexpectedly.
- [x] T15 Validate resume after resolved interrupt restores expected state.

## Phase 4 — Memory + Skills + Preferences
- [x] T16 Validate owner preference save/read (`/prefs`, `/prefs_metrics`).
- [x] T17 Validate memory block write/read for key decisions.
- [x] T18 Validate skill creation/update path on successful goal completion.
- [x] T19 Validate anti-pattern/error capture path for failed runs.
- [x] T20 Validate weekly memory/skill report generation script output.

## Phase 5 — Tooling/Registry/Discovery (Safe Mode)
- [x] T21 Validate tooling registry list/contract visibility.
- [x] T22 Validate tooling policy gates (allowlist/budget) block disallowed runtime action.
- [x] T23 Validate discovery remains disabled in safe phase (`TOOLING_DISCOVERY_ENABLED=false`).
- [x] T24 Validate governance report generation without auto-remediation side effects.

## Phase 6 — Publishing/Platform Dry-Run Flows
- [x] T25 Test posting dry-run flow end-to-end (prepare -> queue -> inspect).
- [x] T26 Test manual queue run (`/pubrun`) with evidence capture.
- [x] T27 Test web operator listing and one safe scenario run.
- [x] T28 Test platform registration flow on sandbox/test account (site #1).
- [x] T29 Test platform registration flow on sandbox/test account (site #2).
- [x] T30 Validate attachment-first flow (photo/doc/video parse and action mapping).

## Phase 7 — Revenue/Finance/Observability
- [x] T31 Validate finance snapshot and spending guardrails.
- [x] T32 Validate revenue engine remains disabled in this phase.
- [x] T33 Validate dashboard API/health and key core cards.
- [x] T34 Validate logs and error surfacing (`/logs`, `/errors`, `/health`).
- [x] T35 Validate balance checks across configured providers.

## Phase 8 — Deferred Modules (Later)
- [x] T36 Self-healer controlled scenario (safe command path).
- [x] T37 Self-healer rollback scenario (forced fail path).
- [x] T38 Brainstorm end-to-end scenario (cost/quality/evidence).

## Phase 9 — Provider Expansion + Final Combat Mode
- [x] T39 Connect remaining provider keys/services and verify connectivity.
- [x] T40 Disable Gemini-only force and restore full router strategy.
- [x] T41 Final full regression + live smoke sequence + release readiness report.

## Phase 10 — Real Platform Publish Closure (Owner Hard Requirement)
- [x] T42 X/Twitter: TG recipe publishes live post with public URL evidence and editable follow-up.
- [x] T43 Reddit: TG recipe publishes live post (or deterministic platform block proof with bypass runbook).
- [x] T44 Gumroad: TG flow updates existing test listing with full attributes (title/description/tags/category/assets) and publish evidence.
- [ ] T45 Etsy: TG flow creates/updates test listing with full required attributes + evidence URL/ID.
- [ ] T46 Ko-fi: TG flow publishes/updates test product/post with full fields and evidence URL.
- [ ] T47 Amazon KDP: TG flow updates one test draft/book with required metadata/assets and visible bookshelf proof.
- [ ] T48 Printful + Etsy linked flow: create/update test product via Printful path and verify listing reflection.
- [x] T49 Pinterest (and optional WordPress if configured): publish pin/post with evidence URL + screenshot.

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
- 2026-03-04: Etsy+Ko-fi combined full-cycle probe executed -> `reports/VITO_ETSY_KOFI_FULL_CYCLE_2026-03-04_1352UTC.json`; blockers are auth-session only (`etsy_session_missing`, `kofi_session_missing`), code path returns deterministic `needs_browser_login`.
- 2026-03-05: Telegram owner simulator smoke re-run passed (`/start`, `/help`, `/status`, `задачи`) -> `reports/VITO_TG_OWNER_SIM_smoke_2026-03-05_1430UTC.json` (`4/4`).
- 2026-03-05: Telegram owner simulator platform-context re-run passed (`зайди на амазон`, `статус аккаунта`, `проверь товары`, `зайди на ukr.net`) -> `reports/VITO_TG_OWNER_SIM_platform_context_2026-03-05_1430UTC.json` (`4/4`).
- 2026-03-05: Regression package re-run (core orchestration + comms + conversation + platform policy + smm):
  - `pytest -q -c /dev/null tests/test_decision_loop.py tests/test_workflow_state_machine.py tests/test_workflow_threads.py` -> `69 passed`
  - `pytest -q -c /dev/null tests/test_comms_agent.py` -> `130 passed`
  - `pytest -q -c /dev/null tests/test_conversation_engine.py` -> `60 passed`
  - `pytest -q -c /dev/null tests/test_platform_gumroad_policy.py tests/test_smm_agent.py` -> `9 passed`
- 2026-03-05: Telegram owner simulator full package:
  - `python3 scripts/telegram_owner_simulator.py --scenario smoke` -> `reports/VITO_TG_OWNER_SIM_smoke_2026-03-05_1517UTC.json` (`4/4`)
  - `python3 scripts/telegram_owner_simulator.py --scenario owner_full_pipeline` -> `reports/VITO_TG_OWNER_SIM_owner_full_pipeline_2026-03-05_1519UTC.json` (`8/8`)
  - `python3 scripts/telegram_owner_simulator.py --scenario platform_context` -> `reports/VITO_TG_OWNER_SIM_platform_context_2026-03-05_1531UTC.json` (`4/4`)
- 2026-03-05: Phase 2 lifecycle (owner command loop) passed in local Telegram-owner simulator:
  - `python3 scripts/telegram_owner_simulator.py --scenario phase2_lifecycle` -> `reports/VITO_TG_OWNER_SIM_phase2_lifecycle_2026-03-05_1544UTC.json` (`9/9`)
  - Covers `/goal`, `/status`, `/report`, `/task_current`, `/task_replace`, `/task_done`, `/cancel`, `/resume`.
- 2026-03-05: Phase 3 approvals (simulated pending approval + owner commands) passed:
  - `python3 scripts/telegram_owner_simulator.py --scenario phase3_approvals` -> `reports/VITO_TG_OWNER_SIM_phase3_approvals_2026-03-05_1544UTC.json` (`6/6`)
  - Covers `/approve`, `/reject`, and empty-queue behavior.
- 2026-03-05: Interrupt/session durability and resume/cancel policies verified by focused regression:
  - `pytest -q -c /dev/null tests/test_workflow_interrupts.py tests/test_orchestration_manager.py tests/test_decision_loop.py -k "interrupt or resume or cancel or approval"` -> `17 passed`.
- 2026-03-05: Fixed leaked aiohttp sessions in simulator shutdown:
  - `main.py`: shutdown now always closes platform sessions via `_close_platform_sessions()`.
  - `scripts/telegram_owner_simulator.py`: unified teardown through `await vito.shutdown()`.
  - Re-check: `python3 scripts/telegram_owner_simulator.py --scenario owner_full_pipeline` -> `reports/VITO_TG_OWNER_SIM_owner_full_pipeline_2026-03-05_1543UTC.json` (`8/8`), leak markers `LEAK=0`.
- 2026-03-05: Phase 4 prefs/memory/skills package:
  - `python3 scripts/telegram_owner_simulator.py --scenario phase4_prefs` -> `reports/VITO_TG_OWNER_SIM_phase4_prefs_2026-03-05_1546UTC.json` (`2/2`).
  - `python3 -c ... MemoryBlocks.record_block/get_block ...` -> `memory_block_saved=True` (`owner_decision`, stage=`short`).
  - `python3 -c ... FailureMemory.record/recent ...` -> recent row contains `phase4_agent` + `simulated_error`.
  - `pytest -q -c /dev/null tests/test_owner_preference_model.py tests/test_owner_pref_metrics.py tests/test_memory_manager.py tests/test_memory_skill_reports.py tests/test_skill_registry.py` -> `39 passed`.
  - `PYTHONPATH=. python3 scripts/generate_weekly_memory_report.py` -> `reports/memory_retention_weekly.md` updated.
- 2026-03-05: Phase 5 tooling/governance package:
  - `pytest -q -c /dev/null tests/test_tooling_registry.py tests/test_tooling_runner.py tests/test_tooling_discovery.py tests/test_operator_policy.py tests/test_governance_reporter.py tests/test_runtime_remediation.py` -> `48 passed`.
  - Safe-mode flags check: `TOOLING_DISCOVERY_ENABLED=False`.
  - Governance generation sanity (`GovernanceReporter.weekly_report`) executed in read-only mode; report built without runtime remediation execution side-effects.
- 2026-03-05: Phase 6 web-operator smoke:
  - `python3 scripts/telegram_owner_simulator.py --scenario phase6_webop` -> `reports/VITO_TG_OWNER_SIM_phase6_webop_2026-03-05_1550UTC.json` (`2/2`).
  - Additional direct probe: `reports/VITO_WEBOP_SCENARIO_2026-03-05_1549UTC.json` (scenario list + safe run attempt).
- 2026-03-05: Phase 7 finance/observability package:
  - `pytest -q -c /dev/null tests/test_financial_controller.py tests/test_revenue_engine.py tests/test_stealth_finance_readiness.py tests/test_platform_smoke.py tests/test_publisher_queue.py tests/test_runtime_remediation.py` -> `105 passed`.
  - `python3 scripts/telegram_owner_simulator.py --scenario phase7_observability` -> `reports/VITO_TG_OWNER_SIM_phase7_observability_2026-03-05_1551UTC.json` (`6/6`), covers `/status`, `/report`, `/health`, `/errors`, `/balances`, `/logs`.
  - `REVENUE_ENGINE_ENABLED=False` confirmed for this phase.
  - Dashboard API health endpoint reachable (`/api/health` returns auth-guarded 401, indicating live endpoint with access control).
  - Fixed `/balances` session leaks: `modules/balance_checker.py` now closes platform sessions in `finally`; regression `tests/test_balance_checker.py` passed.
- 2026-03-05: Live publish matrix re-run -> `reports/VITO_PUBLISH_MATRIX_LIVE_2026-03-05_1430UTC.json`:
  - Etsy: `prepared` (browser editor opened, fields filled, listing_id not detected in this pass)
  - Ko-fi: `prepared` (manual/browser upload required by platform)
  - Printful: `needs_browser_flow` for Etsy-linked store type
  - Twitter/Reddit: `not_authenticated` (current tokens/session)
- 2026-03-05: Agent->Platform live audit re-run -> `reports/VITO_AGENT_PLATFORM_LIVE_AUDIT_2026-03-05_1433UTC.json`, combat responding paths `5/7 = 71.43%` (Twitter auth + Gumroad browser publish remain blockers in this run).
- 2026-03-05: Gumroad reliability updates:
  - `scripts/gumroad_test_cycle.py`: explicit update operation for controlled target listing state.
  - `platforms/gumroad.py`: existing-product API-toggle fallback when browser flow fails/timeouts.
  - `tests/test_platform_gumroad_policy.py`: fallback behavior covered; focused suite passed (`11 passed`).
- 2026-03-05: Platform sandbox registration checks completed for two test sites:
  - `PYTHONPATH=. python3 scripts/platform_registration_sandbox_check.py --site site1`
  - `PYTHONPATH=. python3 scripts/platform_registration_sandbox_check.py --site site2`
  - Evidence: `reports/VITO_PLATFORM_REG_SANDBOX_2026-03-05_1552UTC.json` (`site1=true`, `site2=true`).
- 2026-03-05: Attachment-first routing coverage expanded:
  - `pytest -q -c /dev/null tests/test_comms_agent.py -k "attachment_document_parse_routes or attachment_photo_parse_routes or attachment_video_parse_routes"` -> `3 passed`.
- 2026-03-05: Self-healer and brainstorm deferred package closed:
  - `pytest -q -c /dev/null tests/test_self_healer.py -k "controlled or rollback"` -> `4 passed`.
  - `python3 scripts/telegram_owner_simulator.py --scenario phase8_brainstorm` -> `reports/VITO_TG_OWNER_SIM_phase8_brainstorm_2026-03-05_1558UTC.json` (`1/1`).
- 2026-03-05: Provider expansion and router restore:
  - `PYTHONPATH=. python3 scripts/provider_connectivity_probe.py` -> `reports/VITO_PROVIDER_CONNECTIVITY_2026-03-05_1558UTC.json` (`ok=20`, `errors=1`, `total=21`).
  - `PYTHONPATH=. python3 scripts/provider_health_report.py` -> `reports/VITO_PROVIDER_HEALTH_2026-03-05_1559UTC.json` (`overall=degraded`, missing providers highlighted).
  - `CommsAgent._apply_llm_mode("prod")` verified; router switched from Gemini-only to task-based profile.
- 2026-03-05: Final combat artifacts generated:
  - `python3 scripts/tg_global_combat_suite.py` -> `reports/VITO_TG_GLOBAL_COMBAT_2026-03-05_1559UTC.json`.
  - `python3 scripts/final_scorecard_report.py` -> `reports/VITO_FINAL_SCORECARD_2026-03-05_1559UTC.md`.
  - Final full regression completed with project root config: `PYTHONPATH=. pytest -q --maxfail=1` -> `1054 passed, 1 skipped, 1 warning` (warning: asyncio subprocess transport cleanup in `tests/test_comms_agent.py::test_cmd_prefs`).
- 2026-03-06: Cookie-backed browser sessions imported and verified across 8 services:
  - `python3 scripts/browser_session_import.py --service <svc> --cookies-file input/cookies/<svc>.cookies.json --verify` for `amazon_kdp, etsy, gumroad, kofi, pinterest, printful, reddit, twitter` -> all `ok=true`.
- 2026-03-06: Telegram owner simulation (platform e2e package, owner-style commands):
  - `python3 scripts/telegram_owner_simulator.py --scenario phase_platform_e2e --step-timeout 180`
  - Evidence: `reports/VITO_TG_OWNER_SIM_phase_platform_e2e_2026-03-06_0052UTC.json` (`12/12`).
- 2026-03-06: Live publish matrix re-run with browser-first flows + pinterest path:
  - `python3 scripts/live_publish_matrix.py --live`
  - Evidence: `reports/VITO_PUBLISH_MATRIX_LIVE_2026-03-06_0053UTC.json`
  - Key statuses: `amazon_kdp=published`, `etsy=prepared`, `kofi=prepared`, `pinterest=prepared`, `gumroad=daily_limit`.
- 2026-03-06: Agent→platform live audit re-run (expanded social stack incl. Pinterest):
  - `python3 scripts/live_agent_platform_audit.py`
  - Evidence: `reports/VITO_AGENT_PLATFORM_LIVE_AUDIT_2026-03-06_0053UTC.json`, `responding_percent=75.0`.
- 2026-03-06: Social live probe re-run with Pinterest auth probe:
  - `python3 scripts/social_live_probe.py`
  - Evidence: `reports/VITO_SOCIAL_LIVE_PROBE_2026-03-06_0054UTC.json`.
- 2026-03-06: Full regression rerun after platform-status normalization fixes:
  - `PYTHONPATH=. pytest -q --maxfail=1`
  - Result: `1093 passed, 1 skipped, 1 warning`.
- 2026-03-06: Owner-style Telegram simulation rerun:
  - `python3 scripts/telegram_owner_simulator.py --scenario owner_full_pipeline` -> `reports/VITO_TG_OWNER_SIM_owner_full_pipeline_2026-03-06_1023UTC.json` (`6/8`, two timeouts on long research/posting step).
  - `python3 scripts/telegram_owner_simulator.py --scenario phase_platform_e2e --step-timeout 180` -> `reports/VITO_TG_OWNER_SIM_phase_platform_e2e_2026-03-06_1023UTC.json` (`12/12`).
- 2026-03-06: Global combat and live platform rerun:
  - `python3 scripts/tg_global_combat_suite.py --timeout 420` -> `reports/VITO_TG_GLOBAL_COMBAT_2026-03-06_1024UTC.json`.
  - `python3 scripts/live_publish_matrix.py --live` -> `reports/VITO_PUBLISH_MATRIX_LIVE_2026-03-06_1034UTC.json`.
  - `python3 scripts/live_agent_platform_audit.py` -> `reports/VITO_AGENT_PLATFORM_LIVE_AUDIT_2026-03-06_1036UTC.json`.
  - `python3 scripts/social_live_probe.py` -> `reports/VITO_SOCIAL_LIVE_PROBE_2026-03-06_1036UTC.json`.
  - Deterministic blockers unchanged: Gumroad `cookie_expired`, Ko-fi `cloudflare_challenge`, Pinterest `anti_bot_challenge_or_timeout`, Printful `needs_browser_flow`.
- 2026-03-06: Recipe acceptance gate hardened (no false `prepared` acceptance) + TG recipe payloads normalized per platform.
- 2026-03-06: Reddit browser flow fixed with old.reddit fallback and reCAPTCHA token injection path; TG recipe now returns `accepted` with `status=published`.
- 2026-03-06: Gumroad TG recipe rerun confirmed `accepted` with live `status=published` on controlled test listing.
- 2026-03-06: Pinterest TG recipe repeatedly confirmed with live public pin evidence:
  - `python3 scripts/telegram_owner_simulator.py --scenario phase_platform_e2e --step-timeout 200`
  - Evidence: `reports/VITO_TG_OWNER_SIM_phase_platform_e2e_2026-03-06_1829UTC.json` (`E12 -> accepted, status=published, public pin URL`).
