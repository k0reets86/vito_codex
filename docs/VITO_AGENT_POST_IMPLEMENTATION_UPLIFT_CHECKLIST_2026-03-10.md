# VITO Agent Post-Implementation Uplift Checklist — 2026-03-10

Статусы:
- `not_started`
- `in_progress`
- `done`

Общий прогресс: `100%`

Текущий baseline:
- previous benchmark matrix: `6.89 / 10`
- current benchmark matrix: `7.52 / 10`

## Package 1 — Recovery Depth Uplift
- [x] `browser_agent` recovery depth uplift
- [x] `translation_agent` recovery depth uplift
- [x] `economics_agent` recovery depth uplift
- [x] `account_manager` recovery depth uplift
- [x] `legal_agent` recovery depth uplift
- [x] recovery-aware runtime outputs verified by targeted tests
- [x] benchmark rerun confirms uplift
- Status: `done`

## Package 2 — Data/Tool Depth Uplift
- [x] `translation_agent` richer glossary/consistency path
- [x] `economics_agent` market signal / pricing confidence path
- [x] `legal_agent` executable policy packs
- [x] `account_manager` auth remediation packs
- [x] `research_agent` source coverage / judge-driven runtime profile
- [x] `trend_scout` fallback/runtime source profile
- [x] `analytics_agent` anomaly/forecast runtime profile
- [x] `document_agent` recovery-aware source handling
- [x] `partnership_agent` richer candidate search + scoring inputs
- Status: `done`

## Package 3 — Outcome-Changing Collaboration
- [x] workflow collaboration assertions
- [x] degraded outcome when required support/verify is missing
- [x] cross-agent benchmark tasks for collaboration impact
- Status: `done`

## Package 4 — Commerce Execution Hardening
- [x] `browser_agent` recovery packs deepen runtime behavior
- [x] `account_manager` auth remediation packs deepen runtime behavior
- [x] `ecommerce_agent` deeper platform rule/runbook execution
- [x] `publisher_agent` richer evidence + retry/escalation behavior
- [x] family score `commerce_execution >= 8.0`
- Status: `done`

## Package 5 — Family Re-Benchmark and Kill List
- [x] rerun benchmark matrix after uplift package
- [x] maintain kill-list for agents below `7.0`
- [x] continue uplift until no priority agent remains below `7.0`
- Status: `done`

## Current verified deltas
- overall benchmark: `6.89 -> 7.30 -> 7.41 -> 7.52 -> 7.52 -> 7.70`
- `intelligence_research`: `6.92 -> 7.56`
- `research_agent`: `7.16 -> 7.58`
- `trend_scout`: `6.87 -> 7.45`
- `analytics_agent`: `6.96 -> 7.55`
- `document_agent`: `6.67 -> 7.65`
- `marketing_agent`: `6.86 -> 7.44`
- `risk_agent`: `6.86 -> 7.44`
- `email_agent`: `6.96 -> 7.54`
- `partnership_agent`: `6.53 -> 7.25`
- `commerce_execution`: `6.75 -> 7.88 -> 7.88 -> 8.61`
- `publisher_agent`: `7.05 -> 8.55`
- `ecommerce_agent`: `7.62 -> 9.03`
- `vito_core`: `7.28 -> 8.69`
- Package 3 collaboration assertions: `done`
- Package 4 commerce hardening: `done`

## Current kill-list (< 7.0)
- none
