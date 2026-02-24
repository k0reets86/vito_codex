"""LinkedInPlatform — placeholder implementation (API integration pending)."""

from platforms.base_platform import BasePlatform
from config.settings import settings


class LinkedInPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="linkedin", **kwargs)
        self._token = getattr(settings, "LINKEDIN_ACCESS_TOKEN", "")

    async def authenticate(self) -> bool:
        self._authenticated = bool(self._token)
        return self._authenticated

    async def publish(self, content: dict) -> dict:
        if not self._token:
            return {"platform": "linkedin", "status": "not_configured", "error": "LINKEDIN_ACCESS_TOKEN missing"}
        return {"platform": "linkedin", "status": "not_implemented", "error": "LinkedIn publish not implemented yet"}
