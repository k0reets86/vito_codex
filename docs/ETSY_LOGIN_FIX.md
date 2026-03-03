# Etsy Login Fix

Why login failed:
- Etsy blocks headless login pages with anti-bot checks, so form fields may not appear.

Recommended solution (official):
1. Start OAuth flow:
```bash
python3 scripts/etsy_auth_helper.py oauth-start
```
2. Open printed `auth_url` in normal browser, login, approve.
3. Copy callback URL and complete:
```bash
python3 scripts/etsy_auth_helper.py oauth-complete --code "<FULL_CALLBACK_URL_OR_CODE>"
```

Fallback (browser session capture):
1. Run:
```bash
python3 scripts/etsy_auth_helper.py browser-capture --timeout-sec 420
```
2. Complete login manually in opened browser window.
3. Session files will be saved to:
- `runtime/etsy_storage_state.json`
- `runtime/etsy_storage_state.cookies.json`

Notes:
- `ETSY_EMAIL` and `ETSY_PASSWORD` can be used for prefill only; Etsy may still require captcha/2FA.
- Headless capture is not recommended for Etsy login.
