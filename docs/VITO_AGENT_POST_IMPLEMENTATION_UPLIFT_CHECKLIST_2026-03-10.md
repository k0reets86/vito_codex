# VITO Agent Post-Implementation Uplift Checklist — 2026-03-10

Статусы:
- `not_started`
- `in_progress`
- `done`

Общий прогресс: `55%`

Текущий baseline:
- previous benchmark matrix: `6.89 / 10`
- current benchmark matrix: `7.41 / 10`

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
- [ ] `partnership_agent` richer candidate search + scoring inputs
- Status: `in_progress`

## Package 3 — Outcome-Changing Collaboration
- [ ] workflow collaboration assertions
- [ ] degraded outcome when required support/verify is missing
- [ ] cross-agent benchmark tasks for collaboration impact
- Status: `not_started`

## Package 4 — Commerce Execution Hardening
- [x] `browser_agent` recovery packs deepen runtime behavior
- [x] `account_manager` auth remediation packs deepen runtime behavior
- [ ] `ecommerce_agent` deeper platform rule/runbook execution
- [ ] `publisher_agent` richer evidence + retry/escalation behavior
- [ ] family score `commerce_execution >= 8.0`
- Status: `in_progress`

## Package 5 — Family Re-Benchmark and Kill List
- [x] rerun benchmark matrix after uplift package
- [x] maintain kill-list for agents below `7.0`
- [ ] continue uplift until no priority agent remains below `7.0`
- Status: `in_progress`

## Current verified deltas
- overall benchmark: `6.89 -> 7.30 -> 7.41`
- `intelligence_research`: `6.92 -> 7.56`
- `research_agent`: `7.16 -> 7.58`
- `trend_scout`: `6.87 -> 7.45`
- `analytics_agent`: `6.96 -> 7.55`
- `document_agent`: `6.67 -> 7.65`

## Current kill-list (< 7.0)
- `partnership_agent`
- `marketing_agent`
- `risk_agent`
- `email_agent`
