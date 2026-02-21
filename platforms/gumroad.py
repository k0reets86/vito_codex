"""GumroadPlatform — интеграция с Gumroad API."""

from typing import Any
from config.logger import get_logger
from config.settings import settings
from platforms.base_platform import BasePlatform

logger = get_logger("gumroad", agent="gumroad")
API_BASE = "https://api.gumroad.com/v2"


class GumroadPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="gumroad", **kwargs)
        self._api_key = getattr(settings, "GUMROAD_API_KEY", "")

    async def authenticate(self) -> bool:
        self._authenticated = bool(self._api_key)
        return self._authenticated

    async def publish(self, content: dict) -> dict:
        logger.info(f"Публикация на Gumroad: {content.get('name', 'unknown')}", extra={"event": "gumroad_publish"})
        # TODO: реальный API вызов через aiohttp
        return {"platform": "gumroad", "status": "created", "product": content.get("name", "")}

    async def get_analytics(self) -> dict:
        logger.info("Получение аналитики Gumroad", extra={"event": "gumroad_analytics"})
        return {"platform": "gumroad", "sales": 0, "revenue": 0.0}

    async def health_check(self) -> bool:
        return bool(self._api_key)
