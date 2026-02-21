"""GumroadPlatform — интеграция с Gumroad API v2.

Gumroad API docs: https://app.gumroad.com/api
Авторизация: access_token (creator token из Settings → Advanced → Application).
Fallback: GUMROAD_APP_SECRET если GUMROAD_API_KEY не задан.
"""

from typing import Any

import aiohttp

from config.logger import get_logger
from config.settings import settings
from platforms.base_platform import BasePlatform

logger = get_logger("gumroad", agent="gumroad")
API_BASE = "https://api.gumroad.com/v2"


class GumroadPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="gumroad", **kwargs)
        # Пробуем access_token, fallback на app_secret
        self._access_token = (
            getattr(settings, "GUMROAD_API_KEY", "")
            or getattr(settings, "GUMROAD_APP_SECRET", "")
        )
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _params(self, extra: dict | None = None) -> dict:
        """Базовые параметры с access_token."""
        params = {"access_token": self._access_token}
        if extra:
            params.update(extra)
        return params

    async def authenticate(self) -> bool:
        """GET /v2/user — проверка авторизации."""
        if not self._access_token:
            self._authenticated = False
            return False
        try:
            session = await self._get_session()
            async with session.get(f"{API_BASE}/user", params=self._params()) as resp:
                self._authenticated = resp.status == 200
                if self._authenticated:
                    data = await resp.json()
                    user = data.get("user", {})
                    logger.info(
                        f"Gumroad авторизация: {user.get('name', 'unknown')}",
                        extra={"event": "gumroad_auth_ok", "context": {"user": user.get("name")}},
                    )
                else:
                    body = await resp.text()
                    logger.warning(
                        f"Gumroad авторизация не удалась: {resp.status} {body[:200]}",
                        extra={"event": "gumroad_auth_fail", "context": {"status": resp.status}},
                    )
                return self._authenticated
        except Exception as e:
            logger.error(f"Gumroad auth error: {e}", extra={"event": "gumroad_auth_error"}, exc_info=True)
            self._authenticated = False
            return False

    async def publish(self, content: dict) -> dict:
        """POST /v2/products — создание продукта.

        content: {name, price (cents), description, url (optional)}
        """
        if not self._authenticated:
            auth_ok = await self.authenticate()
            if not auth_ok:
                return {"platform": "gumroad", "status": "not_authenticated"}

        product_data = {
            "name": content.get("name", "VITO Product"),
            "price": content.get("price", 0),  # в центах
            "description": content.get("description", ""),
        }
        if content.get("url"):
            product_data["url"] = content["url"]
        if content.get("preview_url"):
            product_data["preview_url"] = content["preview_url"]

        try:
            session = await self._get_session()
            async with session.post(
                f"{API_BASE}/products",
                data={**self._params(), **product_data},
            ) as resp:
                if resp.status == 404:
                    # Gumroad API no longer supports product creation via API.
                    # Save product details for manual upload or browser_agent.
                    logger.info(
                        f"Gumroad API: product creation not available via API. Saving for manual upload.",
                        extra={"event": "gumroad_api_no_create"},
                    )
                    from pathlib import Path
                    import time as _time
                    out = Path("/home/vito/vito-agent/output/products")
                    out.mkdir(parents=True, exist_ok=True)
                    fp = out / f"gumroad_{int(_time.time())}.md"
                    fp.write_text(
                        f"# {product_data['name']}\n\n"
                        f"**Price:** ${product_data['price'] / 100:.2f}\n\n"
                        f"{product_data.get('description', '')}\n\n"
                        f"---\nUpload to: https://gumroad.com/products/new\n",
                        encoding="utf-8",
                    )
                    return {
                        "platform": "gumroad",
                        "status": "prepared",
                        "file_path": str(fp),
                        "url": "https://gumroad.com/products/new",
                        "note": "Gumroad API does not support product creation. File saved for manual upload.",
                    }

                if resp.content_type and "json" in resp.content_type:
                    data = await resp.json()
                else:
                    text = await resp.text()
                    logger.warning(f"Gumroad unexpected response: {resp.status} {text[:200]}")
                    return {"platform": "gumroad", "status": "error", "error": f"HTTP {resp.status}"}

                if resp.status == 200 and data.get("success"):
                    product = data.get("product", {})
                    logger.info(
                        f"Gumroad продукт создан: {product.get('name')} (${product.get('price', 0) / 100:.2f})",
                        extra={"event": "gumroad_publish_ok", "context": {"product_id": product.get("id")}},
                    )
                    return {
                        "platform": "gumroad",
                        "status": "created",
                        "product_id": product.get("id"),
                        "url": product.get("short_url", ""),
                        "data": product,
                    }
                logger.warning(
                    f"Gumroad publish failed: {data.get('message', resp.status)}",
                    extra={"event": "gumroad_publish_fail"},
                )
                return {"platform": "gumroad", "status": "error", "error": data.get("message", str(resp.status))}
        except Exception as e:
            logger.error(f"Gumroad publish error: {e}", extra={"event": "gumroad_publish_error"}, exc_info=True)
            return {"platform": "gumroad", "status": "error", "error": str(e)}

    async def get_analytics(self) -> dict:
        """GET /v2/products → суммирует sales_count и sales_usd_cents."""
        if not self._authenticated:
            auth_ok = await self.authenticate()
            if not auth_ok:
                return {"platform": "gumroad", "sales": 0, "revenue": 0.0}

        try:
            products = await self.get_products()
            total_sales = sum(p.get("sales_count", 0) for p in products)
            total_revenue_cents = sum(p.get("sales_usd_cents", 0) for p in products)
            analytics = {
                "platform": "gumroad",
                "sales": total_sales,
                "revenue": total_revenue_cents / 100.0,
                "products_count": len(products),
            }
            logger.info(
                f"Gumroad аналитика: {total_sales} продаж, ${total_revenue_cents / 100:.2f}",
                extra={"event": "gumroad_analytics_ok", "context": analytics},
            )
            return analytics
        except Exception as e:
            logger.error(f"Gumroad analytics error: {e}", extra={"event": "gumroad_analytics_error"}, exc_info=True)
            return {"platform": "gumroad", "sales": 0, "revenue": 0.0, "error": str(e)}

    async def get_products(self) -> list[dict]:
        """GET /v2/products → список продуктов."""
        if not self._authenticated:
            auth_ok = await self.authenticate()
            if not auth_ok:
                return []

        try:
            session = await self._get_session()
            async with session.get(f"{API_BASE}/products", params=self._params()) as resp:
                data = await resp.json()
                if resp.status == 200 and data.get("success"):
                    products = data.get("products", [])
                    logger.info(
                        f"Gumroad: {len(products)} продуктов",
                        extra={"event": "gumroad_products_ok", "context": {"count": len(products)}},
                    )
                    return products
                return []
        except Exception as e:
            logger.error(f"Gumroad products error: {e}", extra={"event": "gumroad_products_error"}, exc_info=True)
            return []

    async def health_check(self) -> bool:
        """Проверка доступности API."""
        return await self.authenticate()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
