# VITO E4 Progress

## Done in this iteration (Social SDK Pack start)
- Added social adapters:
  - `platforms/reddit.py`
  - `platforms/tiktok.py`
  - upgraded `platforms/threads.py` (dry-run + live Graph flow skeleton)
  - upgraded `platforms/youtube.py` (dry-run evidence + explicit not_supported for live)
- Main orchestration wiring:
  - `main.py` now builds `_platforms_social` and unified `_platforms_queue`
  - `PublisherQueue` uses unified queue map (commerce + social)
- Added social queue dry-run script:
  - `scripts/social_sdk_dryrun.py`
- Added tests:
  - `tests/test_social_sdk_adapters.py`

## Validation
- Full tests: `501 passed, 1 skipped, 67 deselected`
- New scorecard: `reports/VITO_FINAL_SCORECARD_2026-02-25_0143UTC.md`
  - Average: `9.07/10`
  - Publish/commerce: `6.54/10`

## Notes
- Social SDK adapters are integrated under one queue contract and evidence policy.
- Next step: move from dry-run/prepared to real publish e2e where credentials/scopes are present.
