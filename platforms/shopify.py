"""ShopifyPlatform — placeholder implementation (API integration pending)."""

from platforms.base_platform import BasePlatform
from config.settings import settings


class ShopifyPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="shopify", **kwargs)
        self._token = getattr(settings, "SHOPIFY_ACCESS_TOKEN", "")

    async def authenticate(self) -> bool:
        self._authenticated = bool(self._token)
        return self._authenticated

    async def publish(self, content: dict) -> dict:
        if not self._token:
            return {"platform": "shopify", "status": "not_configured", "error": "SHOPIFY_ACCESS_TOKEN missing"}
        return {"platform": "shopify", "status": "not_implemented", "error": "Shopify publish not implemented yet"}
