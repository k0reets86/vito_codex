# Service Connect Audit — 2026-03-03

## Environment Sync
- Source file used: `input/to_review/обновление переменных.txt`
- `.env` updated with missing keys and aliases required by current project.
- Twitter credentials replaced with values from source file.
- Added/updated: `KDP_EMAIL`, `KDP_PASSWORD`, `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`, `ETSY_SHOP_ID`, `PRINTFUL_STORE_ID`, `GUMROAD_APPLICATION_ID`, `GUMROAD_APPLICATION_SECRET`, `GUMROAD_ACCESS_TOKEN`.
- Reddit switched to browser-only mode in env:
  - `REDDIT_API_DISABLED=true`
  - `REDDIT_MODE=browser_only`

## Runtime Auth Probes
- Gumroad: `auth_ok=true`
- Etsy API: `auth_ok=false` (403: key/secret not active or mismatch)
- Printful: `auth_ok=true`, store bound: `id=17803130`, `type=etsy`, `name=VITOKI`
- Twitter/X API: `auth_ok=false` (401 Unauthorized)
- Ko-fi: `auth_ok=true`
- YouTube Data API key check: `403` (API not enabled in Google Cloud project)
- Amazon KDP endpoint reachability: reachable (`https://kdp.amazon.com` returns 200)

## Critical Notes
- Amazon 2FA/challenge cannot and must not be bypassed by automation.
- Reddit API disabled by owner request and now enforced in config/runtime.
- Etsy and Twitter require credential/app-side remediation before live API use.
