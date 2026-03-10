# VITO Agent Uplift Package 3 Report — 2026-03-10

## Scope

Priority kill-list agents below `7.0`:
- `marketing_agent`
- `risk_agent`
- `email_agent`
- `partnership_agent`

## What changed

### New runtime module
- [growth_runtime.py](/home/vito/vito-agent/modules/growth_runtime.py)

### Agent behavior changes
- `marketing_agent`
  - budget-aware runtime profile
  - next actions for lean / test-and-scale / growth modes
- `risk_agent`
  - explicit block recommendation runtime
  - actionable next steps for high-risk and anti-abuse scenarios
- `email_agent`
  - runtime send/sequence profile
  - subscriber management now emits operational metadata
- `partnership_agent`
  - candidate scoring
  - top-candidate shortlist
  - partnership runtime profile for outreach sequencing

### Contract/skill changes
- richer packs and contracts for:
  - `marketing_agent`
  - `risk_agent`
  - `email_agent`
  - `partnership_agent`

## Validation

Targeted tests:
- `22 passed`

Benchmark rerun:
- source: [VITO_AGENT_BENCHMARK_MATRIX_2026-03-10_0013UTC.json](/home/vito/vito-agent/reports/VITO_AGENT_BENCHMARK_MATRIX_2026-03-10_0013UTC.json)

## Score changes

- overall: `7.41 -> 7.52`
- `marketing_agent`: `6.86 -> 7.44`
- `risk_agent`: `6.86 -> 7.44`
- `email_agent`: `6.96 -> 7.54`
- `partnership_agent`: `6.53 -> 7.25`

## Family changes

- `content_growth`: `7.24 -> 7.47`
- `governance_resilience`: `7.25 -> 7.40`

## Kill-list result

- agents below `7.0`: `none`

## Remaining weak points

- `commerce_execution` still below target `8.0`
- `core_control` unchanged at `7.26`
- `Outcome-Changing Collaboration` package not started yet
