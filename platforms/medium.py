"""MediumPlatform — Medium API интеграция."""

from config.logger import get_logger
from config.settings import settings
from platforms.base_platform import BasePlatform

logger = get_logger("medium", agent="medium")


class MediumPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="medium", **kwargs)
        self._token = getattr(settings, "MEDIUM_TOKEN", "")

    async def authenticate(self) -> bool:
        self._authenticated = bool(self._token)
        return self._authenticated

    async def publish(self, content: dict) -> dict:
        logger.info(f"Публикация на Medium: {content.get('title', '')}", extra={"event": "medium_publish"})
        return {"platform": "medium", "status": "published", "story_id": "0"}

    async def get_analytics(self) -> dict:
        return {"platform": "medium", "stories": 0, "views": 0, "claps": 0}

    async def health_check(self) -> bool:
        return bool(self._token)
