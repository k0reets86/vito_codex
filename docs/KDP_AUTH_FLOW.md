# Amazon KDP Auth Flow (Browser-Only)

## Why this flow
- KDP in this project is browser-based.
- 2FA/challenge is mandatory and handled manually by owner.
- No bypass of Amazon security controls.

## Required env
- `KDP_EMAIL`
- `KDP_PASSWORD`
- `KDP_STORAGE_STATE_FILE` (default: `runtime/kdp_storage_state.json`)

## Capture session (one-time or when session expires)
```bash
python3 scripts/kdp_auth_helper.py browser-capture --timeout-sec 900
```

What to do in browser:
1. Sign in to Amazon/KDP.
2. Complete 2FA/code challenge.
3. Wait until Bookshelf loads.
4. Script saves storage state.

## Probe session
```bash
python3 scripts/kdp_auth_helper.py probe
```

Expected output:
- `{"ok": true, ...}` means KDP session is valid.

## Runtime behavior
- `AmazonKDPPlatform.authenticate()` first checks saved storage-state session.
- If valid, platform is considered connected.
- If invalid/missing, it falls back to browser probe and returns not authenticated until session is restored.

## Quiet Watchdog (low-noise)
- Enabled by default via env:
  - `KDP_WATCHDOG_ENABLED=true`
  - `KDP_WATCHDOG_BASE_HOURS=8`
  - `KDP_WATCHDOG_JITTER_MINUTES=30`
  - `KDP_WATCHDOG_STOP_ON_FAIL=true`
- Behavior:
  - Rare probe every ~8h with jitter (not fixed bot-like cadence).
  - Single auth-fail triggers `reauth_required` and pauses further probes.
  - When owner refreshes `KDP_STORAGE_STATE_FILE`, watchdog auto-detects new mtime and resumes checks.
  - Telegram notifications only on status transitions (`connected` ↔ `reauth_required`).

## Session refresh
- Re-run `browser-capture` when:
  - probe returns `ok=false`
  - KDP redirects to sign-in
  - Amazon invalidates cookies after security event/password change
