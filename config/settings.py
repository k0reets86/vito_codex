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

    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_OWNER_CHAT_ID: str = os.getenv("TELEGRAM_OWNER_CHAT_ID", "")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    CHROMA_PATH: str = os.getenv("CHROMA_PATH", "/home/vito/vito-agent/memory/chroma_db")
    SQLITE_PATH: str = os.getenv("SQLITE_PATH", "/home/vito/vito-agent/memory/vito_local.db")

    # Platforms
    GUMROAD_API_KEY: str = os.getenv("GUMROAD_API_KEY", "")
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

    # Financial limits (USD)
    # Hierarchy: OPERATION_MAX < OPERATION_NOTIFY < DAILY_LIMIT < OPERATION_APPROVE
    DAILY_LIMIT_USD: float = float(os.getenv("DAILY_LIMIT_USD", "3"))
    OPERATION_NOTIFY_USD: float = float(os.getenv("OPERATION_NOTIFY_USD", "1"))
    OPERATION_APPROVE_USD: float = float(os.getenv("OPERATION_APPROVE_USD", "20"))
    OPERATION_MAX_USD: float = float(os.getenv("OPERATION_MAX_USD", "2"))


settings = Settings()
