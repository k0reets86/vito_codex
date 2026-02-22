"""GumroadPlatform — интеграция с Gumroad API v2 + Playwright browser automation.

API: GET products, enable/disable/delete. POST/PUT products = 404 (removed by Gumroad).
Product creation: ONLY via Playwright + session cookie (browser automation).
See memory/gumroad_publishing.md for full experience log.
"""

import asyncio
from pathlib import Path
from typing import Any

import aiohttp

from config.logger import get_logger
from config.settings import settings
from platforms.base_platform import BasePlatform

logger = get_logger("gumroad", agent="gumroad")
API_BASE = "https://api.gumroad.com/v2"
COOKIE_FILE = Path("/tmp/gumroad_cookie.txt")


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
        """Create and publish a product on Gumroad via Playwright browser automation.

        content: {
            name: str,               # Product title
            price: int,              # Price in dollars (not cents)
            description: str,        # Product description text
            summary: str,            # Short summary (1-2 sentences)
            pdf_path: str,           # Path to PDF file
            cover_path: str,         # Path to cover image (1280x720)
            thumb_path: str,         # Path to thumbnail (600x600)
        }

        Gumroad API does NOT support product creation (404). Uses Playwright + session cookie.
        """
        if not self._authenticated:
            auth_ok = await self.authenticate()
            if not auth_ok:
                return {"platform": "gumroad", "status": "not_authenticated"}

        # Try browser-based creation
        return await self._publish_via_browser(content)

    async def _publish_via_browser(self, content: dict) -> dict:
        """Create product via Playwright using session cookie from owner's browser.

        Cookie file: /tmp/gumroad_cookie.txt (_gumroad_app_session value)
        """
        cookie = ""
        if COOKIE_FILE.exists():
            cookie = COOKIE_FILE.read_text().strip()
        if not cookie:
            logger.warning("No Gumroad session cookie. Owner must provide _gumroad_app_session.")
            return {
                "platform": "gumroad",
                "status": "need_cookie",
                "error": "No session cookie. Ask owner for _gumroad_app_session from browser.",
            }

        name = content.get("name", "VITO Product")
        price = str(content.get("price", 9))
        description = content.get("description", "")
        summary = content.get("summary", "")
        pdf_path = content.get("pdf_path", "")
        cover_path = content.get("cover_path", "")
        thumb_path = content.get("thumb_path", "")

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("playwright not installed")
            return {"platform": "gumroad", "status": "error", "error": "playwright not installed"}

        try:
            async with async_playwright() as p:
                br = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
                ctx = await br.new_context(
                    viewport={"width": 1280, "height": 1400},
                    user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                )
                await ctx.add_cookies([{
                    "name": "_gumroad_app_session", "value": cookie,
                    "domain": ".gumroad.com", "path": "/", "httpOnly": True,
                    "secure": True, "sameSite": "Lax",
                }])
                page = await ctx.new_page()
                page.set_default_timeout(20000)

                # Step 1: Create product
                await page.goto("https://gumroad.com/products/new", wait_until="networkidle")
                await asyncio.sleep(2)
                if "login" in page.url:
                    await br.close()
                    return {"platform": "gumroad", "status": "cookie_expired", "error": "Session cookie expired."}

                # Fill name
                name_el = page.locator('input[placeholder*="name" i]').first
                if await name_el.is_visible(timeout=5000):
                    await name_el.fill(name)

                # Click Next
                for sel in ['button:has-text("Next")', 'button:has-text("Create")', 'button[type="submit"]']:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=3000):
                            await btn.click()
                            await asyncio.sleep(3)
                            break
                    except Exception:
                        continue

                # Fill price
                inputs = await page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('input:not([type="hidden"]):not([type="file"])')).map(
                        (el, i) => ({i, value: el.value, visible: el.offsetParent !== null})
                    );
                }""")
                for info in inputs:
                    if info.get("value") == "0" and info.get("visible"):
                        all_inputs = page.locator('input:not([type="hidden"]):not([type="file"])')
                        await all_inputs.nth(info["i"]).fill(price)
                        break

                # Fill summary
                summary_el = page.locator('input[placeholder*="You\'ll get"]').first
                try:
                    if await summary_el.is_visible(timeout=3000):
                        await summary_el.fill(summary)
                except Exception:
                    pass

                # Fill description
                desc_el = page.locator('[contenteditable="true"]').first
                try:
                    if await desc_el.is_visible(timeout=3000):
                        await desc_el.click()
                        await page.keyboard.press("Control+a")
                        await page.keyboard.press("Backspace")
                        for line in description.strip().split("\n"):
                            if line.strip():
                                await page.keyboard.type(line, delay=1)
                            await page.keyboard.press("Enter")
                except Exception:
                    pass

                # Upload cover (file input [2] — accepts video formats)
                if cover_path and Path(cover_path).exists():
                    fi = await page.locator('input[type="file"]').all()
                    for f in fi:
                        accept = await f.evaluate("el => el.accept || ''")
                        if ".mov" in accept or ".mp4" in accept:
                            await f.set_input_files(cover_path)
                            await asyncio.sleep(4)
                            break

                # Upload thumbnail (single image input, not multiple)
                if thumb_path and Path(thumb_path).exists():
                    fi = await page.locator('input[type="file"]').all()
                    for f in fi:
                        attrs = await f.evaluate("el => ({accept: el.accept, multiple: el.multiple})")
                        if not attrs.get("multiple") and ".jpg" in (attrs.get("accept") or ""):
                            await f.set_input_files(thumb_path)
                            await asyncio.sleep(4)
                            break

                # Save
                save = page.locator('button:has-text("Save")').first
                try:
                    await save.click()
                    await asyncio.sleep(4)
                except Exception:
                    pass

                # Go to Content tab and upload PDF
                if pdf_path and Path(pdf_path).exists():
                    content_tab = page.locator('button:has-text("Content"), a:has-text("Content")').first
                    try:
                        await content_tab.click()
                        await asyncio.sleep(3)
                    except Exception:
                        pass

                    upload_btn = page.locator('button:has-text("Upload your files")').first
                    try:
                        if await upload_btn.is_visible(timeout=5000):
                            await upload_btn.click()
                            await asyncio.sleep(2)
                            fi = await page.locator('input[type="file"]').all()
                            for f in fi:
                                accept = await f.evaluate("el => el.accept || ''")
                                if "image" not in accept and "audio" not in accept:
                                    await f.set_input_files(pdf_path)
                                    await asyncio.sleep(5)
                                    break
                    except Exception:
                        pass

                    # Save content
                    try:
                        save2 = page.locator('button:has-text("Save")').first
                        await save2.click()
                        await asyncio.sleep(3)
                    except Exception:
                        pass

                slug = page.url.split("/products/")[-1].split("/")[0] if "/products/" in page.url else ""
                await br.close()

            # Publish via API
            products = await self.get_products()
            for prod in products:
                if prod.get("name") == name or (slug and slug in prod.get("short_url", "")):
                    pid = prod.get("id")
                    enable_result = await self.enable_product(pid)
                    return {
                        "platform": "gumroad",
                        "status": enable_result.get("status", "created"),
                        "product_id": pid,
                        "url": prod.get("short_url", ""),
                    }

            return {"platform": "gumroad", "status": "created", "note": "Product created, check Gumroad dashboard."}

        except Exception as e:
            logger.error(f"Gumroad browser publish error: {e}", exc_info=True)
            return {"platform": "gumroad", "status": "error", "error": str(e)}

    async def enable_product(self, product_id: str) -> dict:
        """PUT /v2/products/{id}/enable — publish a draft product."""
        if not self._authenticated:
            auth_ok = await self.authenticate()
            if not auth_ok:
                return {"platform": "gumroad", "status": "not_authenticated"}

        try:
            session = await self._get_session()
            async with session.put(
                f"{API_BASE}/products/{product_id}/enable",
                params=self._params(),
            ) as resp:
                if resp.content_type and "json" in resp.content_type:
                    data = await resp.json()
                else:
                    text = await resp.text()
                    logger.warning(f"Gumroad enable unexpected: {resp.status} {text[:200]}")
                    return {"platform": "gumroad", "status": "error", "error": f"HTTP {resp.status}"}

                if resp.status == 200 and data.get("success"):
                    product = data.get("product", {})
                    logger.info(
                        f"Gumroad product published: {product.get('name')}",
                        extra={"event": "gumroad_enable_ok", "context": {"product_id": product_id}},
                    )
                    return {
                        "platform": "gumroad",
                        "status": "published",
                        "product_id": product_id,
                        "url": product.get("short_url", ""),
                    }
                error = data.get("message", str(resp.status))
                logger.warning(f"Gumroad enable failed: {error}", extra={"event": "gumroad_enable_fail"})
                return {"platform": "gumroad", "status": "error", "error": error}
        except Exception as e:
            logger.error(f"Gumroad enable error: {e}", extra={"event": "gumroad_enable_error"}, exc_info=True)
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
