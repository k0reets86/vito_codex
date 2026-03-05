# VITO Agents Autonomy + Interaction Report

Generated: 2026-03-05T17:33:28.703033Z
Source reports:
- reports/VITO_AGENT_MEGATEST_2026-03-05_1717UTC.json
- reports/VITO_TG_GLOBAL_COMBAT_2026-03-05_1722UTC.json

## 1) 23-agent runtime audit
- Combat readiness (static): 23/23 = 100.0%
- Full runtime capability success (all checked capabilities per agent): 16/23 agents

### Per-agent runtime results
- account_manager: 1/2 capability checks passed; issues: b'[ALERT] Application-specific password required: https://support.google.com/accounts/answer/185833 (Failure)'
- analytics_agent: 3/3 capability checks passed
- browser_agent: 2/4 capability checks passed; issues: unknown; unknown
- content_creator: 7/7 capability checks passed
- devops_agent: 3/4 capability checks passed; issues: Команда 'Mega' не в whitelist. Допустимые: df, free, journalctl, kill, sqlite3, swapoff, swapon, systemctl
- document_agent: 3/5 capability checks passed; issues: Файл не найден: /home/vito/vito-agent/README.md; Файл не найден: /home/vito/vito-agent/README.md
- ecommerce_agent: 1/3 capability checks passed; issues: Preview files required before publication; Preview files required before publication
- economics_agent: 2/2 capability checks passed
- email_agent: 2/2 capability checks passed
- hr_agent: 3/4 capability checks passed; issues: LLM Router или Registry недоступны
- legal_agent: 3/3 capability checks passed
- marketing_agent: 2/2 capability checks passed
- partnership_agent: 2/2 capability checks passed
- publisher_agent: 2/2 capability checks passed
- quality_judge: 2/2 capability checks passed
- research_agent: 3/3 capability checks passed
- risk_agent: 2/2 capability checks passed
- security_agent: 2/2 capability checks passed
- seo_agent: 3/3 capability checks passed
- smm_agent: 3/3 capability checks passed
- translation_agent: 2/2 capability checks passed
- trend_scout: 5/5 capability checks passed
- vito_core: 3/4 capability checks passed; issues: code_generator или llm_router недоступен

## 2) Telegram owner scenarios (acting as owner commands)
- owner_full_pipeline: 8/8 passed
- phase2_lifecycle: 9/9 passed
- phase3_approvals: 6/6 passed
- phase4_prefs: 2/2 passed
- phase6_webop: 2/2 passed
- phase7_observability: 6/6 passed
- phase8_brainstorm: 1/1 passed

## 3) Platform + social live status (from global combat suite)
- TG smoke: True
- TG platform context: True
- Agent->platform responding percent: 71.43%

### Publish matrix
- twitter: auth_ok=False status=not_authenticated error=
- reddit: auth_ok=False status=not_authenticated error=
- etsy: auth_ok=True status=prepared error=
- printful: auth_ok=True status=needs_browser_flow error=Store type 'etsy' does not support create via /store/products API. Use browser flow in Printful dashboard (linked Etsy store).
- kofi: auth_ok=True status=prepared error=
- wordpress: auth_ok=False status=not_configured error=Set WORDPRESS_URL and WORDPRESS_APP_PASSWORD in .env

### Social auth
- threads: auth_ok=False skipped=False
- reddit: auth_ok=False skipped=False
- tiktok: auth_ok=False skipped=False
- twitter: auth_ok=False skipped=True

## 4) Key blockers observed
- Twitter API auth returns 401 Unauthorized.
- Perplexity key/quota returns insufficient_quota (401) in brainstorm rounds.
- Claude key returns invalid x-api-key (401) in brainstorm rounds.
- Gemini free-tier request quota exhausted (429 RESOURCE_EXHAUSTED) during fallback-heavy brainstorm.
- Printful linked Etsy store requires browser flow for create, API path intentionally blocked by platform constraints.

## 5) Fixes applied in this run
- judge_protocol brainstorm fallback added: auth/quota errors now degrade to gemini-flash instead of hard-failing the round.
- Added timeout guard for brainstorm rounds (35s) to avoid long hangs on dead providers.
- Added fallback cooldown when Gemini quota exhausted to prevent repetitive fallback spam.
- Added tests covering brainstorm fallback and cooldown behavior.

## 6) Practical readiness
- Core orchestration + TG command flows: PASS.
- Agent autonomy in local owner-sim flows: PASS (all phase scenarios passed).
- Full external autonomy is PARTIAL due to provider auth/quota and social auth blockers above.