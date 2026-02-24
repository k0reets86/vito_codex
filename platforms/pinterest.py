"""PinterestPlatform — placeholder implementation (API integration pending)."""

from platforms.base_platform import BasePlatform
from config.settings import settings


class PinterestPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="pinterest", **kwargs)
        self._token = getattr(settings, "PINTEREST_ACCESS_TOKEN", "")

    async def authenticate(self) -> bool:
        self._authenticated = bool(self._token)
        return self._authenticated

    async def publish(self, content: dict) -> dict:
        if not self._token:
            return {"platform": "pinterest", "status": "not_configured", "error": "PINTEREST_ACCESS_TOKEN missing"}
        return {"platform": "pinterest", "status": "not_implemented", "error": "Pinterest publish not implemented yet"}
