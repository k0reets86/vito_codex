"""PrintfulPlatform — интеграция с Printful REST API (print-on-demand)."""

from typing import Any

import aiohttp

from config.logger import get_logger
from config.settings import settings
from platforms.base_platform import BasePlatform
from modules.execution_facts import ExecutionFacts

logger = get_logger("printful", agent="printful")
API_BASE = "https://api.printful.com"


class PrintfulPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="printful", **kwargs)
        self._api_key = getattr(settings, "PRINTFUL_API_KEY", "")
        self._session: aiohttp.ClientSession | None = None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=self._headers())
        return self._session

    async def authenticate(self) -> bool:
        """GET /store — проверка авторизации."""
        if not self._api_key:
            self._authenticated = False
            return False
        try:
            session = await self._get_session()
            async with session.get(f"{API_BASE}/store") as resp:
                self._authenticated = resp.status == 200
                if self._authenticated:
                    logger.info("Printful авторизация успешна", extra={"event": "printful_auth_ok"})
                return self._authenticated
        except Exception as e:
            logger.error(f"Printful auth error: {e}", extra={"event": "printful_auth_error"})
            self._authenticated = False
            return False

    async def publish(self, content: dict) -> dict:
        """POST /store/products — создание продукта."""
        if content.get("dry_run"):
            name = (content.get("sync_product", {}) or {}).get("name", "printful_dryrun")
            try:
                ExecutionFacts().record(
                    action="platform:publish",
                    status="prepared",
                    detail=f"printful dry_run name={str(name)[:80]}",
                    evidence="dryrun:printful",
                    source="printful.publish",
                    evidence_dict={"platform": "printful", "dry_run": True, "name": name},
                )
            except Exception:
                pass
            return {
                "platform": "printful",
                "status": "prepared",
                "dry_run": True,
                "name": name,
            }

        if not self._authenticated:
            return {"platform": "printful", "status": "not_authenticated"}
        try:
            session = await self._get_session()
            async with session.post(f"{API_BASE}/store/products", json=content) as resp:
                data = await resp.json()
                logger.info(
                    f"Printful продукт создан: {content.get('sync_product', {}).get('name', 'unknown')}",
                    extra={"event": "printful_publish"},
                )
                try:
                    product = (data or {}).get("result", {}) if isinstance(data, dict) else {}
                    pid = product.get("id", "")
                    evidence = f"https://www.printful.com/dashboard/store/products/{pid}" if pid else ""
                    ExecutionFacts().record(
                        action="platform:publish",
                        status="created",
                        detail=f"printful product_id={pid}",
                        evidence=evidence,
                        source="printful.publish",
                        evidence_dict={"platform": "printful", "product_id": pid, "url": evidence},
                    )
                except Exception:
                    pass
                return {"platform": "printful", "status": "created", "data": data}
        except Exception as e:
            logger.error(f"Printful publish error: {e}", extra={"event": "printful_publish_error"})
            return {"platform": "printful", "status": "error", "error": str(e)}

    async def get_analytics(self) -> dict:
        """GET /orders — аналитика заказов."""
        if not self._authenticated:
            return {"platform": "printful", "orders": 0, "revenue": 0.0}
        try:
            session = await self._get_session()
            async with session.get(f"{API_BASE}/orders") as resp:
                data = await resp.json()
                orders = data.get("result", [])
                revenue = sum(
                    float(o.get("retail_costs", {}).get("total", 0)) for o in orders
                )
                return {"platform": "printful", "orders": len(orders), "revenue": revenue}
        except Exception as e:
            logger.error(f"Printful analytics error: {e}", extra={"event": "printful_analytics_error"})
            return {"platform": "printful", "orders": 0, "revenue": 0.0, "error": str(e)}

    async def get_products(self) -> list[dict]:
        """GET /store/products — список продуктов."""
        if not self._authenticated:
            return []
        try:
            session = await self._get_session()
            async with session.get(f"{API_BASE}/store/products") as resp:
                data = await resp.json()
                return data.get("result", [])
        except Exception as e:
            logger.error(f"Printful products error: {e}", extra={"event": "printful_products_error"})
            return []

    async def create_mockup(self, product_id: int, files: list[dict]) -> dict:
        """POST /mockup-generator/create-task — создание мокапа."""
        if not self._authenticated:
            return {"status": "not_authenticated"}
        try:
            session = await self._get_session()
            payload = {"variant_ids": [product_id], "files": files}
            async with session.post(f"{API_BASE}/mockup-generator/create-task/{product_id}", json=payload) as resp:
                return await resp.json()
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def health_check(self) -> bool:
        return bool(self._api_key)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
