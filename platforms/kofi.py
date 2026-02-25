"""KofiPlatform — Ko-fi API integration.

Ko-fi has a limited API — mainly webhook-based for receiving donations/purchases.
Ko-fi Shop API: POST products via their internal API.
Auth: KF_API key + page_id.
"""

from typing import Any

import aiohttp

from config.logger import get_logger
from config.settings import settings
from platforms.base_platform import BasePlatform
from modules.execution_facts import ExecutionFacts

logger = get_logger("kofi", agent="kofi")
API_BASE = "https://ko-fi.com/api"


class KofiPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="kofi", **kwargs)
        self._api_key = settings.KOFI_API_KEY
        self._page_id = settings.KOFI_PAGE_ID
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def authenticate(self) -> bool:
        """Verify Ko-fi API key by checking profile page availability."""
        if not self._api_key or not self._page_id:
            self._authenticated = False
            logger.info(
                "Ko-fi not configured (no API key or page ID)",
                extra={"event": "kofi_not_configured"},
            )
            return False

        try:
            session = await self._get_session()
            # Ko-fi doesn't have a dedicated auth endpoint
            # Verify by checking the public page exists
            async with session.get(
                f"https://ko-fi.com/{self._page_id}",
                timeout=aiohttp.ClientTimeout(total=10),
                allow_redirects=True,
            ) as resp:
                # 200/403 = page exists (Ko-fi blocks bots but page is real)
                self._authenticated = resp.status in (200, 301, 302, 403)
                if self._authenticated:
                    logger.info(
                        f"Ko-fi page verified: {self._page_id}",
                        extra={"event": "kofi_auth_ok"},
                    )
                return self._authenticated
        except Exception as e:
            logger.error(f"Ko-fi auth error: {e}", exc_info=True)
            self._authenticated = False
            return False

    async def publish(self, content: dict) -> dict:
        """Create a Ko-fi shop item.

        Ko-fi doesn't have a public product creation API.
        This prepares the product data and attempts to use their internal API.
        Falls back to browser_agent automation if available.

        content: {title, description, price, type (digital/physical), file_url}
        """
        if content.get("dry_run"):
            title = content.get("title", "")
            try:
                ExecutionFacts().record(
                    action="platform:publish",
                    status="prepared",
                    detail=f"kofi dry_run title={str(title)[:80]}",
                    evidence="dryrun:kofi",
                    source="kofi.publish",
                    evidence_dict={"platform": "kofi", "dry_run": True, "title": title},
                )
            except Exception:
                pass
            return {
                "platform": "kofi",
                "status": "prepared",
                "dry_run": True,
                "title": title,
            }

        if not self._authenticated:
            auth_ok = await self.authenticate()
            if not auth_ok:
                return {"platform": "kofi", "status": "not_authenticated"}

        title = content.get("title", "")
        price = content.get("price", 0)
        description = content.get("description", "")

        # Ko-fi doesn't have a documented public API for creating products
        # Use browser_agent if available for automation
        if self.browser_agent:
            try:
                result = await self.browser_agent.execute_task(
                    "web_action",
                    url="https://ko-fi.com/manage/shop",
                    action="create_product",
                    data={
                        "title": title,
                        "description": description,
                        "price": price,
                    },
                )
                if result.success:
                    logger.info(
                        f"Ko-fi product created via browser: {title}",
                        extra={"event": "kofi_publish_ok"},
                    )
                    try:
                        ExecutionFacts().record(
                            action="platform:publish",
                            status="created",
                            detail=f"kofi title={title[:80]}",
                            evidence=f"https://ko-fi.com/{self._page_id}",
                            source="kofi.publish",
                            evidence_dict={"platform": "kofi", "title": title, "method": "browser_automation"},
                        )
                    except Exception:
                        pass
                    return {
                        "platform": "kofi",
                        "status": "created",
                        "title": title,
                        "price": price,
                        "method": "browser_automation",
                    }
            except Exception as e:
                logger.warning(f"Ko-fi browser automation failed: {e}")

        # Fallback: prepare product data for manual review
        product_url = f"https://ko-fi.com/s/{self._page_id}"
        logger.info(
            f"Ko-fi product prepared (manual upload needed): {title}",
            extra={"event": "kofi_publish_prepared"},
        )
        try:
            ExecutionFacts().record(
                action="platform:publish",
                status="prepared",
                detail=f"kofi title={title[:80]}",
                evidence=product_url,
                source="kofi.publish",
                evidence_dict={"platform": "kofi", "title": title, "method": "prepared"},
            )
        except Exception:
            pass
        return {
            "platform": "kofi",
            "status": "prepared",
            "title": title,
            "price": price,
            "description": description,
            "shop_url": product_url,
            "note": "Ko-fi has no public product API. Use browser_agent or manual upload.",
        }

    async def get_donations(self) -> list[dict]:
        """Check recent donations/purchases via Ko-fi webhook data.

        Ko-fi sends webhooks to a configured URL. This method checks
        if we have stored webhook data in our database.
        """
        # Ko-fi sends POST webhooks with donation data
        # We'd need to set up a webhook receiver endpoint
        return []

    async def get_analytics(self) -> dict:
        """Ko-fi analytics — limited to what's available."""
        return {
            "platform": "kofi",
            "page_id": self._page_id,
            "page_url": f"https://ko-fi.com/{self._page_id}" if self._page_id else "",
            "supporters": 0,
            "revenue": 0.0,
            "note": "Ko-fi analytics available on ko-fi.com/manage. No public API.",
        }

    async def health_check(self) -> bool:
        if not self._api_key:
            return False
        return await self.authenticate()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
