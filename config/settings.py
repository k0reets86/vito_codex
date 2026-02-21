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
    SENDGRID_API_KEY: str = os.getenv("SENDGRID_API_KEY", "")
    REDDIT_CLIENT_ID: str = os.getenv("REDDIT_CLIENT_ID", "")
    REDDIT_CLIENT_SECRET: str = os.getenv("REDDIT_CLIENT_SECRET", "")

    # Financial limits (USD)
    DAILY_LIMIT_USD: float = float(os.getenv("DAILY_LIMIT_USD", "10"))
    OPERATION_NOTIFY_USD: float = float(os.getenv("OPERATION_NOTIFY_USD", "20"))
    OPERATION_APPROVE_USD: float = float(os.getenv("OPERATION_APPROVE_USD", "50"))


settings = Settings()
