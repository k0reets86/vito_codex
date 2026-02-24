"""Skill templates for rapid integrations."""

from typing import List

TEMPLATES = {
    "oauth_api": {
        "keywords": ["oauth", "auth", "token", "refresh", "client_id", "client_secret"],
        "steps": [
            "Identify OAuth flow (authorization code vs client credentials)",
            "Implement token exchange + refresh + secure storage",
            "Add API client with retries and rate limits",
            "Add health check and minimal tests",
        ],
    },
    "rest_api": {
        "keywords": ["api", "rest", "endpoint", "webhook"],
        "steps": [
            "Confirm base URL and auth method",
            "Implement client with timeout/retries",
            "Add minimal integration tests",
        ],
    },
    "telegram_channel": {
        "keywords": ["telegram", "канал"],
        "steps": [
            "Create channel and bot, add admin",
            "Store bot token and channel id",
            "Implement posting + scheduling",
            "Add analytics collection",
        ],
    },
    "youtube_channel": {
        "keywords": ["youtube", "ютуб"],
        "steps": [
            "Enable YouTube Data API",
            "OAuth setup + scopes",
            "Implement upload + metadata",
            "Add analytics fetch",
        ],
    },
    "threads": {
        "keywords": ["threads", "тредс"],
        "steps": [
            "Check official API availability",
            "Implement auth or browser automation",
            "Create posting + link tracking",
        ],
    },
}


def match_templates(request: str) -> List[str]:
    lower = request.lower()
    matched = []
    for name, cfg in TEMPLATES.items():
        if any(k in lower for k in cfg["keywords"]):
            matched.append(name)
    return matched
