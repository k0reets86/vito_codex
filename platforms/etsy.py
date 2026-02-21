"""EtsyPlatform — интеграция с Etsy API."""

from config.logger import get_logger
from config.settings import settings
from platforms.base_platform import BasePlatform

logger = get_logger("etsy", agent="etsy")


class EtsyPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="etsy", **kwargs)
        self._api_key = getattr(settings, "ETSY_API_KEY", "")

    async def authenticate(self) -> bool:
        self._authenticated = bool(self._api_key)
        return self._authenticated

    async def publish(self, content: dict) -> dict:
        logger.info(f"Публикация на Etsy: {content.get('title', 'unknown')}", extra={"event": "etsy_publish"})
        return {"platform": "etsy", "status": "created", "listing": content.get("title", "")}

    async def get_analytics(self) -> dict:
        return {"platform": "etsy", "views": 0, "sales": 0, "revenue": 0.0}

    async def health_check(self) -> bool:
        return bool(self._api_key)
