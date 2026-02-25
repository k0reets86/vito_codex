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

    # Notifications
    NOTIFY_MODE: str = os.getenv("NOTIFY_MODE", "minimal")  # minimal|all

    # Browser behavior
    BROWSER_DEFAULT_ON_URL: bool = os.getenv("BROWSER_DEFAULT_ON_URL", "true").lower() in ("1", "true", "yes", "on")

    # Owner inbox (file-based comms)
    OWNER_INBOX_ENABLED: bool = os.getenv("OWNER_INBOX_ENABLED", "true").lower() in ("1", "true", "yes", "on")

    # Dashboard
    DASHBOARD_ENABLED: bool = os.getenv("DASHBOARD_ENABLED", "true").lower() in ("1", "true", "yes", "on")
    DASHBOARD_HOST: str = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    DASHBOARD_PORT: int = int(os.getenv("DASHBOARD_PORT", "8787"))
    DASHBOARD_TOKEN: str = os.getenv("DASHBOARD_TOKEN", "")

    # Time sync
    TIME_SYNC_URL: str = os.getenv("TIME_SYNC_URL", "https://worldtimeapi.org/api/ip")
    TIME_SYNC_URLS: str = os.getenv("TIME_SYNC_URLS", "")
    TIME_SYNC_MAX_SKEW_SEC: int = int(os.getenv("TIME_SYNC_MAX_SKEW_SEC", "5"))

    # Calendar update
    CALENDAR_UPDATE_LLM: bool = os.getenv("CALENDAR_UPDATE_LLM", "false").lower() in ("1", "true", "yes", "on")

    # Workflow resume
    RESUME_FROM_CHECKPOINT: bool = os.getenv("RESUME_FROM_CHECKPOINT", "false").lower() in ("1", "true", "yes", "on")
    SELF_REFINE_ENABLED: bool = os.getenv("SELF_REFINE_ENABLED", "false").lower() in ("1", "true", "yes", "on")
    SELF_REFINE_MAX_PASSES: int = int(os.getenv("SELF_REFINE_MAX_PASSES", "1") or 1)
    SELF_LEARNING_ENABLED: bool = os.getenv("SELF_LEARNING_ENABLED", "false").lower() in ("1", "true", "yes", "on")
    SELF_LEARNING_SKILL_SCORE_MIN: float = float(os.getenv("SELF_LEARNING_SKILL_SCORE_MIN", "0.78") or 0.78)

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
    TOOLING_BLOCK_WITH_PENDING_ROTATION: bool = os.getenv("TOOLING_BLOCK_WITH_PENDING_ROTATION", "true").lower() in ("1", "true", "yes", "on")
    TOOLING_LIVE_REQUIRED_STAGE: str = os.getenv("TOOLING_LIVE_REQUIRED_STAGE", "production")
    TOOLING_REQUIRE_PRODUCTION_APPROVAL: bool = os.getenv("TOOLING_REQUIRE_PRODUCTION_APPROVAL", "true").lower() in ("1", "true", "yes", "on")
    TOOLING_REQUIRE_ROLLBACK_APPROVAL: bool = os.getenv("TOOLING_REQUIRE_ROLLBACK_APPROVAL", "true").lower() in ("1", "true", "yes", "on")
    TOOLING_RELEASE_SECRET: str = os.getenv("TOOLING_RELEASE_SECRET", "tooling-release-local")


settings = Settings()
