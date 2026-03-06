"""KofiPlatform — Ko-fi integration.

Ko-fi has limited public API for shop item management.
Preferred live path in VITO: browser automation with saved session state.
Fallback path: prepared/manual payload.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import aiohttp

from config.logger import get_logger
from config.paths import PROJECT_ROOT
from config.settings import settings
from modules.execution_facts import ExecutionFacts
from modules.listing_optimizer import optimize_listing_payload
from platforms.base_platform import BasePlatform

logger = get_logger("kofi", agent="kofi")
API_BASE = "https://ko-fi.com/api"


class KofiPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="kofi", **kwargs)
        self._api_key = settings.KOFI_API_KEY
        self._page_id = settings.KOFI_PAGE_ID
        self._mode = str(os.getenv("KOFI_MODE", "api") or "api").strip().lower()
        self._storage_state_path = Path(str(os.getenv("KOFI_STORAGE_STATE_FILE", "runtime/kofi_storage_state.json") or "runtime/kofi_storage_state.json"))
        if not self._storage_state_path.is_absolute():
            self._storage_state_path = PROJECT_ROOT / self._storage_state_path
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _authenticate_browser_mode(self) -> bool:
        if not self._storage_state_path.exists():
            self._authenticated = False
            return False
        try:
            raw = self._storage_state_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            cookies = data.get("cookies") if isinstance(data, dict) else None
            self._authenticated = isinstance(cookies, list) and len(cookies) > 0
            return self._authenticated
        except Exception:
            self._authenticated = False
            return False

    async def authenticate(self) -> bool:
        """Verify Ko-fi connectivity.

        - browser/browser_only mode: validate saved storage_state cookies
        - api mode: validate public page accessibility
        """
        if self._mode in {"browser", "browser_only"}:
            return await self._authenticate_browser_mode()

        if not self._api_key or not self._page_id:
            self._authenticated = False
            logger.info(
                "Ko-fi not configured (no API key or page ID)",
                extra={"event": "kofi_not_configured"},
            )
            return False

        try:
            session = await self._get_session()
            async with session.get(
                f"https://ko-fi.com/{self._page_id}",
                timeout=aiohttp.ClientTimeout(total=10),
                allow_redirects=True,
            ) as resp:
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

    async def _publish_via_browser(self, content: dict) -> dict:
        content = optimize_listing_payload("kofi", content or {})
        operation = str(content.get("operation") or "create").strip().lower()
        allow_existing_update = bool(content.get("allow_existing_update"))
        owner_edit_confirmed = bool(content.get("owner_edit_confirmed"))
        target_product_id = str(content.get("target_product_id") or "").strip()
        if bool(getattr(settings, "PUBLISH_CREATE_GUARD_ENABLED", True)):
            if operation in {"create", "new"} and allow_existing_update:
                return {
                    "platform": "kofi",
                    "status": "blocked",
                    "error": "create_mode_forbids_existing_update",
                }
            if allow_existing_update and not owner_edit_confirmed:
                return {
                    "platform": "kofi",
                    "status": "blocked",
                    "error": "existing_update_requires_explicit_owner_request",
                }
            if allow_existing_update and not target_product_id:
                return {
                    "platform": "kofi",
                    "status": "blocked",
                    "error": "existing_update_requires_target_product_id",
                }
        if not self._storage_state_path.exists():
            return {
                "platform": "kofi",
                "status": "needs_browser_login",
                "error": "Ko-fi browser session required. Run: python3 scripts/kofi_auth_helper.py browser-capture",
                "storage_state": str(self._storage_state_path),
            }
        try:
            from playwright.async_api import async_playwright
        except Exception:
            return {"platform": "kofi", "status": "error", "error": "playwright_not_installed"}

        title = str(content.get("title") or "VITO Ko-fi Product").strip()
        description = str(content.get("description") or "").strip()
        price = str(content.get("price") or "5").strip()
        shot = str(PROJECT_ROOT / "runtime" / "kofi_browser_publish.png")
        page_html = str(PROJECT_ROOT / "runtime" / "kofi_browser_publish.html")
        created_url = f"https://ko-fi.com/s/{self._page_id}" if self._page_id else "https://ko-fi.com/manage/shop"

        browser = None
        context = None
        page = None
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=os.getenv("VITO_BROWSER_HEADLESS", "1").lower() not in {"0", "false", "no"},
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-software-rasterizer",
                        "--disable-blink-features=AutomationControlled",
                    ],
                )
                context = await browser.new_context(
                    storage_state=str(self._storage_state_path),
                    viewport={"width": 1366, "height": 900},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
                )
                page = await context.new_page()
                await page.goto("https://ko-fi.com/manage/shop", wait_until="domcontentloaded", timeout=90000)
                await page.wait_for_timeout(2000)
                current = page.url.lower()
                if "/login" in current or "/signin" in current:
                    return {
                        "platform": "kofi",
                        "status": "needs_browser_login",
                        "error": "Stored Ko-fi session expired.",
                        "storage_state": str(self._storage_state_path),
                    }

                for sel in ("input[name='title']", "input[placeholder*='Title']", "input[type='text']"):
                    try:
                        loc = page.locator(sel)
                        if await loc.count():
                            await loc.first.fill(title[:120], timeout=1800)
                            break
                    except Exception:
                        continue
                for sel in ("textarea[name='description']", "textarea[placeholder*='Description']", "textarea"):
                    try:
                        loc = page.locator(sel)
                        if await loc.count():
                            await loc.first.fill(description[:3000], timeout=1800)
                            break
                    except Exception:
                        continue
                for sel in ("input[name='price']", "input[placeholder*='Price']", "input[inputmode='decimal']"):
                    try:
                        loc = page.locator(sel)
                        if await loc.count():
                            await loc.first.fill(price, timeout=1800)
                            break
                    except Exception:
                        continue

                clicked = False
                for txt in ("Publish", "Save", "Create", "Create product", "Post"):
                    try:
                        btn = page.get_by_role("button", name=txt)
                        if await btn.count():
                            await btn.first.click(timeout=2500)
                            await page.wait_for_timeout(1500)
                            clicked = True
                            break
                    except Exception:
                        continue

                try:
                    await page.screenshot(path=shot, full_page=True)
                except Exception:
                    pass
                try:
                    html = await page.content()
                    Path(page_html).parent.mkdir(parents=True, exist_ok=True)
                    Path(page_html).write_text(html or "", encoding="utf-8")
                except Exception:
                    pass

                status = "created" if clicked else "prepared"
                try:
                    ExecutionFacts().record(
                        action="platform:publish",
                        status=status,
                        detail=f"kofi browser title={title[:80]}",
                        evidence=created_url,
                        source="kofi.publish.browser",
                        evidence_dict={"platform": "kofi", "title": title, "mode": "browser_only", "url": created_url},
                    )
                except Exception:
                    pass
                return {
                    "platform": "kofi",
                    "status": status,
                    "title": title,
                    "price": price,
                    "mode": "browser_only",
                    "url": created_url,
                    "screenshot_path": shot,
                }
        except Exception as e:
            return {"platform": "kofi", "status": "error", "error": str(e), "screenshot_path": shot}
        finally:
            try:
                if page is not None:
                    await page.close()
            except Exception:
                pass
            try:
                if context is not None:
                    await context.close()
            except Exception:
                pass
            try:
                if browser is not None:
                    await browser.close()
            except Exception:
                pass

    async def publish(self, content: dict) -> dict:
        """Create a Ko-fi shop item."""
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

        if self._mode in {"browser", "browser_only"}:
            return await self._publish_via_browser(content)

        if not self._authenticated:
            auth_ok = await self.authenticate()
            if not auth_ok:
                return {"platform": "kofi", "status": "not_authenticated"}

        title = content.get("title", "")
        price = content.get("price", 0)
        description = content.get("description", "")

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
            "note": "Ko-fi has no public product API. Use browser automation or manual upload.",
        }

    async def get_donations(self) -> list[dict]:
        return []

    async def get_analytics(self) -> dict:
        return {
            "platform": "kofi",
            "page_id": self._page_id,
            "page_url": f"https://ko-fi.com/{self._page_id}" if self._page_id else "",
            "supporters": 0,
            "revenue": 0.0,
            "note": "Ko-fi analytics available on ko-fi.com/manage. No public API.",
        }

    async def health_check(self) -> bool:
        if self._mode in {"browser", "browser_only"}:
            return await self._authenticate_browser_mode()
        if not self._api_key:
            return False
        return await self.authenticate()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
