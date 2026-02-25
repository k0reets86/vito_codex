# VITO E4 Progress

## Done in this iteration
- Expanded Social SDK configuration surface:
  - Added settings vars: `THREADS_ACCESS_TOKEN`, `THREADS_USER_ID`, `TIKTOK_ACCESS_TOKEN`, `REDDIT_USERNAME`, `REDDIT_PASSWORD`, `REDDIT_USER_AGENT`
  - Added these keys to Telegram env ingestion allowlist (`_try_set_env_from_text`).
- Stabilized new social adapter paths with test-compatible behavior.
- Verified full regression remains green after integration.

## Tests
- Targeted: `50 passed`
- Full: `501 passed, 1 skipped, 67 deselected`

## Status
- Social SDK Pack is in-progress: adapters wired and test-stable, next step is live (non-dry) e2e where credentials/scopes are present.
