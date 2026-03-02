import os
from pathlib import Path

from dotenv import load_dotenv

ENV_PATH = Path("/home/vito/vito-agent/.env")
load_dotenv(ENV_PATH)


class Settings:
    # LLM API Keys
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    PERPLEXITY_API_KEY: str = os.getenv("PERPLEXITY_API_KEY", "")
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_DEFAULT_MODEL: str = os.getenv("OPENROUTER_DEFAULT_MODEL", "openai/gpt-4o-mini")
    ANTICAPTCHA_KEY: str = os.getenv("ANTICAPTCHA_KEY", "")

    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_OWNER_CHAT_ID: str = os.getenv("TELEGRAM_OWNER_CHAT_ID", "")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    CHROMA_PATH: str = os.getenv("CHROMA_PATH", "/home/vito/vito-agent/memory/chroma_db")
    SQLITE_PATH: str = os.getenv("SQLITE_PATH", "/home/vito/vito-agent/memory/vito_local.db")

    # Platforms
    GUMROAD_API_KEY: str = os.getenv("GUMROAD_API_KEY", "")
    GUMROAD_OAUTH_TOKEN: str = os.getenv("GUMROAD_OAUTH_TOKEN", "")
    GUMROAD_EMAIL: str = os.getenv("GUMROAD_EMAIL", "")
    GUMROAD_PASSWORD: str = os.getenv("GUMROAD_PASSWORD", "")
    ETSY_API_KEY: str = os.getenv("ETSY_API_KEY", "")
    KOFI_API_KEY: str = os.getenv("KOFI_API_KEY", "")
    WORDPRESS_URL: str = os.getenv("WORDPRESS_URL", "")
    WORDPRESS_APP_PASSWORD: str = os.getenv("WORDPRESS_APP_PASSWORD", "")
    MEDIUM_TOKEN: str = os.getenv("MEDIUM_TOKEN", "")

    # Email & Social
    GMAIL_ADDRESS: str = os.getenv("GMAIL_ADDRESS", "")
    GMAIL_PASSWORD: str = os.getenv("GMAIL_PASSWORD", "")
    SENDGRID_API_KEY: str = os.getenv("SENDGRID_API_KEY", "")
    REDDIT_CLIENT_ID: str = os.getenv("REDDIT_CLIENT_ID", "")
    REDDIT_CLIENT_SECRET: str = os.getenv("REDDIT_CLIENT_SECRET", "")
    REDDIT_USERNAME: str = os.getenv("REDDIT_USERNAME", "")
    REDDIT_PASSWORD: str = os.getenv("REDDIT_PASSWORD", "")
    REDDIT_USER_AGENT: str = os.getenv("REDDIT_USER_AGENT", "vito-bot/0.3")

    # X.com (Twitter)
    TWITTER_BEARER_TOKEN: str = os.getenv("TWITTER_BEARER_TOKEN", "")
    TWITTER_CONSUMER_KEY: str = os.getenv("TWITTER_CONSUMER_KEY", "")
    TWITTER_CONSUMER_SECRET: str = os.getenv("TWITTER_CONSUMER_SECRET", "")
    TWITTER_ACCESS_TOKEN: str = os.getenv("TWITTER_ACCESS_TOKEN", "")
    TWITTER_ACCESS_SECRET: str = os.getenv("TWITTER_ACCESS_SECRET", "")

    # Reddit RSS
    REDDIT_RSS_ENTREPRENEUR: str = os.getenv("REDDIT_RSS_ENTREPRENEUR", "")
    REDDIT_RSS_PASSIVE: str = os.getenv("REDDIT_RSS_PASSIVE", "")
    REDDIT_RSS_ECOMMERCE: str = os.getenv("REDDIT_RSS_ECOMMERCE", "")

    # New platforms
    PRINTFUL_API_KEY: str = os.getenv("PRINTFUL_API_KEY", "")
    ETSY_KEYSTRING: str = os.getenv("ETSY_KEYSTRING", "")
    ETSY_SHARED_SECRET: str = os.getenv("ETSY_SHARED_SECRET", "")
    GUMROAD_APP_ID: str = os.getenv("GUMROAD_APP_ID", "")
    GUMROAD_APP_SECRET: str = os.getenv("GUMROAD_APP_SECRET", "")
    KOFI_PAGE_ID: str = os.getenv("KOFI_PAGE_ID", "")
    CLOUDINARY_CLOUD_NAME: str = os.getenv("CLOUDINARY_CLOUD_NAME", "")
    CLOUDINARY_API_KEY: str = os.getenv("CLOUDINARY_API_KEY", "")
    CLOUDINARY_API_SECRET: str = os.getenv("CLOUDINARY_API_SECRET", "")

    # Image Generation
    REPLICATE_API_TOKEN: str = os.getenv("REPLICATE_API_TOKEN", "")
    BFL_API_KEY: str = os.getenv("BFL_API_KEY", "")
    WAVESPEED_API_KEY: str = os.getenv("WAVESPEED_API_KEY", "")

    # Social official APIs
    THREADS_ACCESS_TOKEN: str = os.getenv("THREADS_ACCESS_TOKEN", "")
    THREADS_USER_ID: str = os.getenv("THREADS_USER_ID", "")
    TIKTOK_ACCESS_TOKEN: str = os.getenv("TIKTOK_ACCESS_TOKEN", "")

    # Financial limits (USD)
    # Hierarchy: OPERATION_MAX < OPERATION_NOTIFY < DAILY_LIMIT < OPERATION_APPROVE
    DAILY_LIMIT_USD: float = float(os.getenv("DAILY_LIMIT_USD", "3"))
    OPERATION_NOTIFY_USD: float = float(os.getenv("OPERATION_NOTIFY_USD", "1"))
    OPERATION_APPROVE_USD: float = float(os.getenv("OPERATION_APPROVE_USD", "20"))
    OPERATION_MAX_USD: float = float(os.getenv("OPERATION_MAX_USD", "2"))

    # Autonomy toggles
    PROACTIVE_ENABLED: bool = os.getenv("PROACTIVE_ENABLED", "true").lower() in ("1", "true", "yes", "on")
    BRAINSTORM_WEEKLY: bool = os.getenv("BRAINSTORM_WEEKLY", "true").lower() in ("1", "true", "yes", "on")

    # LLM cache
    LLM_CACHE_TTL_HOURS: int = int(os.getenv("LLM_CACHE_TTL_HOURS", "24"))
    LLM_DISABLED_MODELS: str = os.getenv("LLM_DISABLED_MODELS", "")
    LLM_ENABLED_MODELS: str = os.getenv("LLM_ENABLED_MODELS", "")
    LLM_FORCE_GEMINI_FREE: bool = os.getenv("LLM_FORCE_GEMINI_FREE", "false").lower() in ("1", "true", "yes", "on")
    MODEL_ACTIVE_PROFILE: str = os.getenv("MODEL_ACTIVE_PROFILE", "balanced")

    # Notifications
    NOTIFY_MODE: str = os.getenv("NOTIFY_MODE", "minimal")  # minimal|all
    TELEGRAM_CRON_ENABLED: bool = os.getenv("TELEGRAM_CRON_ENABLED", "false").lower() in ("1", "true", "yes", "on")
    TELEGRAM_STRICT_COMMANDS: bool = os.getenv("TELEGRAM_STRICT_COMMANDS", "true").lower() in ("1", "true", "yes", "on")

    # Browser behavior
    BROWSER_DEFAULT_ON_URL: bool = os.getenv("BROWSER_DEFAULT_ON_URL", "true").lower() in ("1", "true", "yes", "on")

    # Owner inbox (file-based comms)
    OWNER_INBOX_ENABLED: bool = os.getenv("OWNER_INBOX_ENABLED", "true").lower() in ("1", "true", "yes", "on")
    CONVERSATION_HISTORY_PATH: str = os.getenv("CONVERSATION_HISTORY_PATH", "/home/vito/vito-agent/runtime/conversation_history.json")
    CANCEL_STATE_PATH: str = os.getenv("CANCEL_STATE_PATH", "/home/vito/vito-agent/runtime/cancel_state.json")
    OWNER_TASK_STATE_PATH: str = os.getenv("OWNER_TASK_STATE_PATH", "/home/vito/vito-agent/runtime/owner_task_state.json")
    CONVERSATION_CONTEXT_TURNS: int = int(os.getenv("CONVERSATION_CONTEXT_TURNS", "10") or 10)
    REVENUE_ENGINE_ENABLED: bool = os.getenv("REVENUE_ENGINE_ENABLED", "false").lower() in ("1", "true", "yes", "on")
    REVENUE_ENGINE_DRY_RUN: bool = os.getenv("REVENUE_ENGINE_DRY_RUN", "true").lower() in ("1", "true", "yes", "on")
    REVENUE_ENGINE_REQUIRE_APPROVAL: bool = os.getenv("REVENUE_ENGINE_REQUIRE_APPROVAL", "true").lower() in ("1", "true", "yes", "on")
    REVENUE_ENGINE_DAILY_HOUR_UTC: int = int(os.getenv("REVENUE_ENGINE_DAILY_HOUR_UTC", "15") or 15)
    REVENUE_ENGINE_LIVE_REQUIRE_AUTH: bool = os.getenv("REVENUE_ENGINE_LIVE_REQUIRE_AUTH", "true").lower() in ("1", "true", "yes", "on")
    REVENUE_ENGINE_LIVE_CHECK_ADAPTER_AUTH: bool = os.getenv("REVENUE_ENGINE_LIVE_CHECK_ADAPTER_AUTH", "true").lower() in ("1", "true", "yes", "on")
    REVENUE_ENGINE_LIVE_AUTH_TIMEOUT_SEC: int = int(os.getenv("REVENUE_ENGINE_LIVE_AUTH_TIMEOUT_SEC", "12") or 12)
    REVENUE_ENGINE_LIVE_MAX_QUEUE_FAILED: int = int(os.getenv("REVENUE_ENGINE_LIVE_MAX_QUEUE_FAILED", "0") or 0)
    REVENUE_ENGINE_LIVE_MAX_QUEUE_QUEUED: int = int(os.getenv("REVENUE_ENGINE_LIVE_MAX_QUEUE_QUEUED", "20") or 20)
    REVENUE_ENGINE_LIVE_MAX_QUEUE_RUNNING: int = int(os.getenv("REVENUE_ENGINE_LIVE_MAX_QUEUE_RUNNING", "10") or 10)
    REVENUE_ENGINE_LIVE_MAX_QUEUE_TOTAL: int = int(os.getenv("REVENUE_ENGINE_LIVE_MAX_QUEUE_TOTAL", "40") or 40)
    REVENUE_ENGINE_LIVE_MAX_QUEUE_FAIL_RATE: float = float(os.getenv("REVENUE_ENGINE_LIVE_MAX_QUEUE_FAIL_RATE", "0.0") or 0.0)
    REVENUE_ENGINE_LIVE_FAIL_RATE_MIN_TOTAL: int = int(os.getenv("REVENUE_ENGINE_LIVE_FAIL_RATE_MIN_TOTAL", "1") or 1)
    REVENUE_ENGINE_LIVE_MAX_QUEUED_AGE_SEC: int = int(os.getenv("REVENUE_ENGINE_LIVE_MAX_QUEUED_AGE_SEC", "0") or 0)
    REVENUE_ENGINE_LIVE_MAX_RUNNING_AGE_SEC: int = int(os.getenv("REVENUE_ENGINE_LIVE_MAX_RUNNING_AGE_SEC", "0") or 0)
    REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS: bool = os.getenv("REVENUE_ENGINE_LIVE_REQUIRE_QUEUE_STATS", "true").lower() in ("1", "true", "yes", "on")
    REVENUE_ENGINE_LIVE_REQUIRE_BROWSER_RUNTIME: bool = os.getenv("REVENUE_ENGINE_LIVE_REQUIRE_BROWSER_RUNTIME", "false").lower() in ("1", "true", "yes", "on")
    REVENUE_ENGINE_LIVE_REQUIRE_SESSION_COOKIE: bool = os.getenv("REVENUE_ENGINE_LIVE_REQUIRE_SESSION_COOKIE", "false").lower() in ("1", "true", "yes", "on")
    GUMROAD_SESSION_COOKIE_FILE: str = os.getenv("GUMROAD_SESSION_COOKIE_FILE", "/tmp/gumroad_cookie.txt")
    REVENUE_ENGINE_PUBLISH_TIMEOUT_SEC: int = int(os.getenv("REVENUE_ENGINE_PUBLISH_TIMEOUT_SEC", "45") or 45)
    REVENUE_ENGINE_AUTO_REPORT_ENABLED: bool = os.getenv("REVENUE_ENGINE_AUTO_REPORT_ENABLED", "true").lower() in ("1", "true", "yes", "on")
    REVENUE_ENGINE_REPORT_DIR: str = os.getenv("REVENUE_ENGINE_REPORT_DIR", "runtime/reports/revenue")
    SELF_HEALER_QUARANTINE_SEC: int = int(os.getenv("SELF_HEALER_QUARANTINE_SEC", "600") or 600)
    SELF_HEALER_QUARANTINE_MAX_MULT: int = int(os.getenv("SELF_HEALER_QUARANTINE_MAX_MULT", "3") or 3)
    SELF_HEALER_MAX_CHANGED_FILES: int = int(os.getenv("SELF_HEALER_MAX_CHANGED_FILES", "3") or 3)
    SELF_HEALER_MAX_CHANGED_LINES: int = int(os.getenv("SELF_HEALER_MAX_CHANGED_LINES", "180") or 180)
    SELF_HEALER_POLICY_MODE: str = os.getenv("SELF_HEALER_POLICY_MODE", "strict")
    SELF_HEALER_BALANCED_ALLOW_SERVICE_RESTART: bool = os.getenv("SELF_HEALER_BALANCED_ALLOW_SERVICE_RESTART", "false").lower() in ("1", "true", "yes", "on")
    SELF_HEALER_CANARY_ENABLED: bool = os.getenv("SELF_HEALER_CANARY_ENABLED", "false").lower() in ("1", "true", "yes", "on")
    SELF_HEALER_CANARY_COMMAND: str = os.getenv("SELF_HEALER_CANARY_COMMAND", "systemctl is-active vito")
    QUALITY_JUDGE_APPROVAL_THRESHOLD: int = int(os.getenv("QUALITY_JUDGE_APPROVAL_THRESHOLD", "7") or 7)
    AUTONOMOUS_IMPROVEMENT_ENABLED: bool = os.getenv("AUTONOMOUS_IMPROVEMENT_ENABLED", "false").lower() in ("1", "true", "yes", "on")
    AUTONOMOUS_IMPROVEMENT_ALERTS_ENABLED: bool = os.getenv("AUTONOMOUS_IMPROVEMENT_ALERTS_ENABLED", "false").lower() in ("1", "true", "yes", "on")
    AUTONOMOUS_IMPROVEMENT_INTERVAL_TICKS: int = int(os.getenv("AUTONOMOUS_IMPROVEMENT_INTERVAL_TICKS", "288") or 288)
    AUTONOMOUS_IMPROVEMENT_MAX_CANDIDATES: int = int(os.getenv("AUTONOMOUS_IMPROVEMENT_MAX_CANDIDATES", "4") or 4)

    # Dashboard
    DASHBOARD_ENABLED: bool = os.getenv("DASHBOARD_ENABLED", "true").lower() in ("1", "true", "yes", "on")
    DASHBOARD_HOST: str = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    DASHBOARD_PORT: int = int(os.getenv("DASHBOARD_PORT", "8787"))
    DASHBOARD_TOKEN: str = os.getenv("DASHBOARD_TOKEN", "")
    PROCESS_GUARD_ENABLED: bool = os.getenv("PROCESS_GUARD_ENABLED", "true").lower() in ("1", "true", "yes", "on")
    PROCESS_GUARD_INTERVAL_SEC: int = int(os.getenv("PROCESS_GUARD_INTERVAL_SEC", "90") or 90)

    # Time sync
    TIME_SYNC_URL: str = os.getenv("TIME_SYNC_URL", "https://worldtimeapi.org/api/ip")
    TIME_SYNC_URLS: str = os.getenv("TIME_SYNC_URLS", "")
    TIME_SYNC_MAX_SKEW_SEC: int = int(os.getenv("TIME_SYNC_MAX_SKEW_SEC", "5"))

    # Calendar update
    CALENDAR_UPDATE_LLM: bool = os.getenv("CALENDAR_UPDATE_LLM", "false").lower() in ("1", "true", "yes", "on")

    # Workflow resume
    RESUME_FROM_CHECKPOINT: bool = os.getenv("RESUME_FROM_CHECKPOINT", "false").lower() in ("1", "true", "yes", "on")
    AUTO_RESUME_MAX_PER_INTERRUPT: int = int(os.getenv("AUTO_RESUME_MAX_PER_INTERRUPT", "2") or 2)
    AUTO_RESUME_COOLDOWN_SEC: int = int(os.getenv("AUTO_RESUME_COOLDOWN_SEC", "120") or 120)
    MEMORY_WEEKLY_REPORT_ENABLED: bool = os.getenv("MEMORY_WEEKLY_REPORT_ENABLED", "true").lower() in ("1", "true", "yes", "on")
    MEMORY_WEEKLY_REPORT_ALERTS_ENABLED: bool = os.getenv("MEMORY_WEEKLY_REPORT_ALERTS_ENABLED", "false").lower() in ("1", "true", "yes", "on")
    MEMORY_WEEKLY_REPORT_INTERVAL_TICKS: int = int(os.getenv("MEMORY_WEEKLY_REPORT_INTERVAL_TICKS", "2016") or 2016)
    MEMORY_WEEKLY_REPORT_MIN_QUALITY: float = float(os.getenv("MEMORY_WEEKLY_REPORT_MIN_QUALITY", "0.65") or 0.65)
    MEMORY_WEEKLY_REPORT_MIN_SKILL_HEALTH: float = float(os.getenv("MEMORY_WEEKLY_REPORT_MIN_SKILL_HEALTH", "0.55") or 0.55)
    MEMORY_WEEKLY_REPORT_PATH: str = os.getenv("MEMORY_WEEKLY_REPORT_PATH", "reports/memory_retention_weekly.md")
    WEEKLY_GOVERNANCE_REPORT_ENABLED: bool = os.getenv("WEEKLY_GOVERNANCE_REPORT_ENABLED", "true").lower() in ("1", "true", "yes", "on")
    WEEKLY_GOVERNANCE_REPORT_ALERTS_ENABLED: bool = os.getenv("WEEKLY_GOVERNANCE_REPORT_ALERTS_ENABLED", "true").lower() in ("1", "true", "yes", "on")
    WEEKLY_GOVERNANCE_REPORT_INTERVAL_TICKS: int = int(os.getenv("WEEKLY_GOVERNANCE_REPORT_INTERVAL_TICKS", "2016") or 2016)
    WEEKLY_GOVERNANCE_REPORT_PATH: str = os.getenv("WEEKLY_GOVERNANCE_REPORT_PATH", "reports/governance_weekly.md")
    WEEKLY_GOVERNANCE_SKILL_REMEDIATE_ENABLED: bool = os.getenv("WEEKLY_GOVERNANCE_SKILL_REMEDIATE_ENABLED", "true").lower() in ("1", "true", "yes", "on")
    WEEKLY_GOVERNANCE_SKILL_REMEDIATE_LIMIT: int = int(os.getenv("WEEKLY_GOVERNANCE_SKILL_REMEDIATE_LIMIT", "20") or 20)
    WEEKLY_GOVERNANCE_AUTO_REMEDIATE: bool = os.getenv("WEEKLY_GOVERNANCE_AUTO_REMEDIATE", "false").lower() in ("1", "true", "yes", "on")
    WEEKLY_GOVERNANCE_AUTO_REMEDIATE_ON_WARNING: bool = os.getenv("WEEKLY_GOVERNANCE_AUTO_REMEDIATE_ON_WARNING", "false").lower() in ("1", "true", "yes", "on")
    WEEKLY_GOVERNANCE_AUTO_REMEDIATE_MAX_ACTIONS: int = int(os.getenv("WEEKLY_GOVERNANCE_AUTO_REMEDIATE_MAX_ACTIONS", "2") or 2)
    SELF_REFINE_ENABLED: bool = os.getenv("SELF_REFINE_ENABLED", "false").lower() in ("1", "true", "yes", "on")
    SELF_REFINE_MAX_PASSES: int = int(os.getenv("SELF_REFINE_MAX_PASSES", "1") or 1)
    SELF_LEARNING_ENABLED: bool = os.getenv("SELF_LEARNING_ENABLED", "false").lower() in ("1", "true", "yes", "on")
    SELF_LEARNING_SKILL_SCORE_MIN: float = float(os.getenv("SELF_LEARNING_SKILL_SCORE_MIN", "0.78") or 0.78)
    SELF_LEARNING_AUTO_PROMOTE: bool = os.getenv("SELF_LEARNING_AUTO_PROMOTE", "false").lower() in ("1", "true", "yes", "on")
    SELF_LEARNING_MIN_LESSONS: int = int(os.getenv("SELF_LEARNING_MIN_LESSONS", "3") or 3)
    SELF_LEARNING_OPTIMIZE_INTERVAL_TICKS: int = int(os.getenv("SELF_LEARNING_OPTIMIZE_INTERVAL_TICKS", "72") or 72)
    SELF_LEARNING_TEST_RUNNER_ENABLED: bool = os.getenv("SELF_LEARNING_TEST_RUNNER_ENABLED", "false").lower() in ("1", "true", "yes", "on")
    SELF_LEARNING_TEST_RUNNER_INTERVAL_TICKS: int = int(os.getenv("SELF_LEARNING_TEST_RUNNER_INTERVAL_TICKS", "96") or 96)
    SELF_LEARNING_TEST_RUNNER_MAX_JOBS: int = int(os.getenv("SELF_LEARNING_TEST_RUNNER_MAX_JOBS", "2") or 2)
    SELF_LEARNING_TEST_RUNNER_TIMEOUT_SEC: int = int(os.getenv("SELF_LEARNING_TEST_RUNNER_TIMEOUT_SEC", "120") or 120)
    SELF_LEARNING_MAINTENANCE_INTERVAL_TICKS: int = int(os.getenv("SELF_LEARNING_MAINTENANCE_INTERVAL_TICKS", "168") or 168)
    SELF_LEARNING_MAINTENANCE_DAYS: int = int(os.getenv("SELF_LEARNING_MAINTENANCE_DAYS", "45") or 45)
    SELF_LEARNING_MAINTENANCE_MIN_LESSONS: int = int(os.getenv("SELF_LEARNING_MAINTENANCE_MIN_LESSONS", "4") or 4)
    SELF_LEARNING_REMEDIATION_MAX_ACTIONS: int = int(os.getenv("SELF_LEARNING_REMEDIATION_MAX_ACTIONS", "3") or 3)
    SELF_LEARNING_TEST_JOB_RETENTION_DAYS: int = int(os.getenv("SELF_LEARNING_TEST_JOB_RETENTION_DAYS", "90") or 90)
    SELF_LEARNING_TEST_RETRY_ON_FAIL: bool = os.getenv("SELF_LEARNING_TEST_RETRY_ON_FAIL", "true").lower() in ("1", "true", "yes", "on")
    SELF_LEARNING_TEST_MAX_ATTEMPTS: int = int(os.getenv("SELF_LEARNING_TEST_MAX_ATTEMPTS", "2") or 2)
    SELF_LEARNING_FLAKY_COOLDOWN_HOURS: int = int(os.getenv("SELF_LEARNING_FLAKY_COOLDOWN_HOURS", "72") or 72)
    SELF_LEARNING_FLAKY_RATE_MAX: float = float(os.getenv("SELF_LEARNING_FLAKY_RATE_MAX", "0.3") or 0.3)
    SELF_LEARNING_FLAKY_WINDOW_DAYS: int = int(os.getenv("SELF_LEARNING_FLAKY_WINDOW_DAYS", "30") or 30)
    SELF_LEARNING_FLAKY_DECAY_DAYS: int = int(os.getenv("SELF_LEARNING_FLAKY_DECAY_DAYS", "14") or 14)
    SELF_LEARNING_FLAKY_MIN_WEIGHT: float = float(os.getenv("SELF_LEARNING_FLAKY_MIN_WEIGHT", "0.12") or 0.12)
    SELF_LEARNING_OUTCOME_WINDOW_DAYS: int = int(os.getenv("SELF_LEARNING_OUTCOME_WINDOW_DAYS", "60") or 60)
    SELF_LEARNING_OUTCOME_DECAY_DAYS: int = int(os.getenv("SELF_LEARNING_OUTCOME_DECAY_DAYS", "21") or 21)
    SELF_LEARNING_THRESHOLD_OUTCOME_WEIGHT: float = float(os.getenv("SELF_LEARNING_THRESHOLD_OUTCOME_WEIGHT", "0.02") or 0.02)
    SELF_LEARNING_OUTCOME_MIN_TEST_RUNS: int = int(os.getenv("SELF_LEARNING_OUTCOME_MIN_TEST_RUNS", "2") or 2)
    SELF_LEARNING_OUTCOME_FAIL_RATE_MAX: float = float(os.getenv("SELF_LEARNING_OUTCOME_FAIL_RATE_MAX", "0.35") or 0.35)
    SELF_LEARNING_TEST_TARGET_MAP: str = os.getenv("SELF_LEARNING_TEST_TARGET_MAP", "")

    # Owner preference auto-detect (off by default)
    OWNER_PREF_AUTO_DETECT: bool = os.getenv("OWNER_PREF_AUTO_DETECT", "false").lower() in ("1", "true", "yes", "on")

    # Capability pack gating
    CAPABILITY_PACK_ALLOW_PENDING: bool = os.getenv("CAPABILITY_PACK_ALLOW_PENDING", "false").lower() in ("1", "true", "yes", "on")

    # LLM guardrails
    GUARDRAILS_ENABLED: bool = os.getenv("GUARDRAILS_ENABLED", "true").lower() in ("1", "true", "yes", "on")
    GUARDRAILS_BLOCK_ON_INJECTION: bool = os.getenv("GUARDRAILS_BLOCK_ON_INJECTION", "false").lower() in ("1", "true", "yes", "on")
    LLM_ALERTS_ENABLED: bool = os.getenv("LLM_ALERTS_ENABLED", "true").lower() in ("1", "true", "yes", "on")
    TOOLING_RUN_LIVE_ENABLED: bool = os.getenv("TOOLING_RUN_LIVE_ENABLED", "false").lower() in ("1", "true", "yes", "on")
    TOOLING_HTTP_TIMEOUT_SEC: int = int(os.getenv("TOOLING_HTTP_TIMEOUT_SEC", "8") or 8)
    TOOLING_MCP_TIMEOUT_SEC: int = int(os.getenv("TOOLING_MCP_TIMEOUT_SEC", "12") or 12)
    TOOLING_MCP_MAX_OUTPUT_BYTES: int = int(os.getenv("TOOLING_MCP_MAX_OUTPUT_BYTES", "32768") or 32768)
    TOOLING_MCP_ALLOW_CMDS: str = os.getenv("TOOLING_MCP_ALLOW_CMDS", "python3,node,npx,uv,mcp-server")
    TOOLING_CONTRACT_SECRET: str = os.getenv("TOOLING_CONTRACT_SECRET", "tooling-contract-local")
    TOOLING_CONTRACT_KEYS: str = os.getenv("TOOLING_CONTRACT_KEYS", "")
    TOOLING_CONTRACT_ACTIVE_KEY_ID: str = os.getenv("TOOLING_CONTRACT_ACTIVE_KEY_ID", "")
    TOOLING_BLOCK_WITH_PENDING_ROTATION: bool = os.getenv("TOOLING_BLOCK_WITH_PENDING_ROTATION", "true").lower() in ("1", "true", "yes", "on")
    TOOLING_LIVE_REQUIRED_STAGE: str = os.getenv("TOOLING_LIVE_REQUIRED_STAGE", "production")
    TOOLING_REQUIRE_PRODUCTION_APPROVAL: bool = os.getenv("TOOLING_REQUIRE_PRODUCTION_APPROVAL", "true").lower() in ("1", "true", "yes", "on")
    TOOLING_REQUIRE_ROLLBACK_APPROVAL: bool = os.getenv("TOOLING_REQUIRE_ROLLBACK_APPROVAL", "true").lower() in ("1", "true", "yes", "on")
    TOOLING_KEY_ROTATION_MAX_DAYS: int = int(os.getenv("TOOLING_KEY_ROTATION_MAX_DAYS", "90") or 90)
    TOOLING_KEY_ROTATION_WARN_DAYS: int = int(os.getenv("TOOLING_KEY_ROTATION_WARN_DAYS", "14") or 14)
    TOOLING_GOVERNANCE_ALERT_ENABLED: bool = os.getenv("TOOLING_GOVERNANCE_ALERT_ENABLED", "true").lower() in ("1", "true", "yes", "on")
    TOOLING_GOVERNANCE_INTERVAL_TICKS: int = int(os.getenv("TOOLING_GOVERNANCE_INTERVAL_TICKS", "288") or 288)
    TOOLING_DISCOVERY_ENABLED: bool = os.getenv("TOOLING_DISCOVERY_ENABLED", "false").lower() in ("1", "true", "yes", "on")
    TOOLING_DISCOVERY_ALERTS_ENABLED: bool = os.getenv("TOOLING_DISCOVERY_ALERTS_ENABLED", "true").lower() in ("1", "true", "yes", "on")
    TOOLING_DISCOVERY_INTERVAL_TICKS: int = int(os.getenv("TOOLING_DISCOVERY_INTERVAL_TICKS", "288") or 288)
    TOOLING_DISCOVERY_MAX_PER_TICK: int = int(os.getenv("TOOLING_DISCOVERY_MAX_PER_TICK", "3") or 3)
    TOOLING_DISCOVERY_AUTO_PROMOTE_APPROVED: bool = os.getenv("TOOLING_DISCOVERY_AUTO_PROMOTE_APPROVED", "false").lower() in ("1", "true", "yes", "on")
    TOOLING_DISCOVERY_DEDUP_HOURS: int = int(os.getenv("TOOLING_DISCOVERY_DEDUP_HOURS", "72") or 72)
    TOOLING_DISCOVERY_ROLLOUT_STAGE: str = os.getenv("TOOLING_DISCOVERY_ROLLOUT_STAGE", "canary")
    TOOLING_DISCOVERY_CANARY_PERCENT: int = int(os.getenv("TOOLING_DISCOVERY_CANARY_PERCENT", "34") or 34)
    TOOLING_DISCOVERY_REQUIRE_HTTPS: bool = os.getenv("TOOLING_DISCOVERY_REQUIRE_HTTPS", "true").lower() in ("1", "true", "yes", "on")
    TOOLING_DISCOVERY_ALLOWED_DOMAINS: str = os.getenv("TOOLING_DISCOVERY_ALLOWED_DOMAINS", "")
    TOOLING_DISCOVERY_AUTO_PAUSE_ON_POLICY_BLOCK: bool = os.getenv("TOOLING_DISCOVERY_AUTO_PAUSE_ON_POLICY_BLOCK", "false").lower() in ("1", "true", "yes", "on")
    TOOLING_DISCOVERY_POLICY_BLOCK_THRESHOLD: int = int(os.getenv("TOOLING_DISCOVERY_POLICY_BLOCK_THRESHOLD", "3") or 3)
    TOOLING_DISCOVERY_POLICY_BLOCK_RATE_THRESHOLD: float = float(os.getenv("TOOLING_DISCOVERY_POLICY_BLOCK_RATE_THRESHOLD", "0.8") or 0.8)
    TOOLING_DISCOVERY_POLICY_BLOCK_RATE_MIN_PROCESSED: int = int(os.getenv("TOOLING_DISCOVERY_POLICY_BLOCK_RATE_MIN_PROCESSED", "3") or 3)
    TOOLING_DISCOVERY_SOURCES: str = os.getenv("TOOLING_DISCOVERY_SOURCES", "")
    TOOLING_RELEASE_SECRET: str = os.getenv("TOOLING_RELEASE_SECRET", "tooling-release-local")
    TOOLING_RELEASE_KEYS: str = os.getenv("TOOLING_RELEASE_KEYS", "")
    TOOLING_RELEASE_ACTIVE_KEY_ID: str = os.getenv("TOOLING_RELEASE_ACTIVE_KEY_ID", "")


settings = Settings()
