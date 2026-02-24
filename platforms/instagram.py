"""InstagramPlatform — placeholder implementation (Graph API integration pending)."""

from platforms.base_platform import BasePlatform
from config.settings import settings


class InstagramPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="instagram", **kwargs)
        self._token = getattr(settings, "INSTAGRAM_ACCESS_TOKEN", "")

    async def authenticate(self) -> bool:
        self._authenticated = bool(self._token)
        return self._authenticated

    async def publish(self, content: dict) -> dict:
        if not self._token:
            return {"platform": "instagram", "status": "not_configured", "error": "INSTAGRAM_ACCESS_TOKEN missing"}
        return {"platform": "instagram", "status": "not_implemented", "error": "Instagram publish not implemented yet"}
