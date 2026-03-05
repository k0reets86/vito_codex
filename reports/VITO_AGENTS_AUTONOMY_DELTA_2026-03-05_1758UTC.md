# VITO Agents Retest Delta

Source: reports/VITO_TG_GLOBAL_COMBAT_2026-03-05_1758UTC.json

## Summary
- tg_smoke_passed: True
- tg_platform_context_passed: True
- agent_audit_responding_percent: 71.43%

## Publish matrix
- twitter: auth_ok=False status=not_authenticated error=
- reddit: auth_ok=False status=not_authenticated error=
- etsy: auth_ok=True status=prepared error=
- printful: auth_ok=True status=needs_browser_flow error=Store type 'etsy' does not support create via /store/products API. Use browser flow in Printful dashboard (linked Etsy store).
- kofi: auth_ok=True status=prepared error=
- wordpress: auth_ok=False status=not_configured error=Set WORDPRESS_URL and WORDPRESS_APP_PASSWORD in .env

## Social auth
- threads: auth_ok=False skipped=False
- reddit: auth_ok=False skipped=False
- tiktok: auth_ok=False skipped=False
- twitter: auth_ok=False skipped=True

## Notes
- Core Telegram orchestration remains stable (pass).
- Main blockers are still external auth/quota constraints (Twitter/Threads/TikTok/Reddit keys and quotas).
- Printful->Etsy create requires browser flow by platform design.