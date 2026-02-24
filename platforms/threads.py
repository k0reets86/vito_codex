"""ThreadsPlatform — placeholder implementation (Graph API integration pending)."""

from platforms.base_platform import BasePlatform
from config.settings import settings


class ThreadsPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="threads", **kwargs)
        self._token = getattr(settings, "THREADS_ACCESS_TOKEN", "")

    async def authenticate(self) -> bool:
        self._authenticated = bool(self._token)
        return self._authenticated

    async def publish(self, content: dict) -> dict:
        if not self._token:
            return {"platform": "threads", "status": "not_configured", "error": "THREADS_ACCESS_TOKEN missing"}
        return {"platform": "threads", "status": "not_implemented", "error": "Threads publish not implemented yet"}
