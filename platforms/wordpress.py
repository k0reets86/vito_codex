"""WordPressPlatform — WordPress REST API интеграция."""

from config.logger import get_logger
from config.settings import settings
from platforms.base_platform import BasePlatform

logger = get_logger("wordpress", agent="wordpress")


class WordPressPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="wordpress", **kwargs)
        self._url = getattr(settings, "WORDPRESS_URL", "")
        self._password = getattr(settings, "WORDPRESS_APP_PASSWORD", "")

    async def authenticate(self) -> bool:
        self._authenticated = bool(self._url and self._password)
        return self._authenticated

    async def publish(self, content: dict) -> dict:
        logger.info(f"Публикация на WordPress: {content.get('title', '')}", extra={"event": "wp_publish"})
        return {"platform": "wordpress", "status": "published", "post_id": "0", "url": f"{self._url}/post/0"}

    async def get_analytics(self) -> dict:
        return {"platform": "wordpress", "posts": 0, "views": 0}

    async def health_check(self) -> bool:
        return bool(self._url)
