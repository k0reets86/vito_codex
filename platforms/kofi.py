"""KofiPlatform — интеграция с Ko-fi."""

from config.logger import get_logger
from platforms.base_platform import BasePlatform

logger = get_logger("kofi", agent="kofi")


class KofiPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="kofi", **kwargs)

    async def authenticate(self) -> bool:
        self._authenticated = self.browser_agent is not None
        return self._authenticated

    async def publish(self, content: dict) -> dict:
        logger.info(f"Публикация на Ko-fi: {content.get('title', 'unknown')}", extra={"event": "kofi_publish"})
        return {"platform": "kofi", "status": "created", "item": content.get("title", "")}

    async def get_analytics(self) -> dict:
        return {"platform": "kofi", "supporters": 0, "revenue": 0.0}

    async def health_check(self) -> bool:
        return self.browser_agent is not None
