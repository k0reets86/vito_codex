# VITO E4 Progress

## Done in this iteration
- Added Telegram commands for orchestration observability:
  - `/workflow` — workflow state health + recent transitions
  - `/handoffs` — handoff summary + recent transfer traces
- Added offline-text shortcuts in owner inbox mode for `workflow/handoffs`.
- Extended bot command menu with new commands.
- Added tests for new comms commands in `tests/test_comms_agent.py`.

## Validation
- Targeted tests: `48 passed`
- Full tests: `492 passed, 1 skipped, 67 deselected`
- Final scorecard regenerated: `reports/VITO_FINAL_SCORECARD_2026-02-25_0126UTC.md`

## Effect
- Owner now has direct visibility into orchestrator durability and multi-agent transfers from Telegram.
- This improves debuggability of “почему не сделал/где зависло”.
