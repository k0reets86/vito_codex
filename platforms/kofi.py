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
from modules.display_bootstrap import ensure_display
from modules.listing_optimizer import optimize_listing_payload
from modules.xvfb_session import XvfbSession
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
        xvfb = None
        try:
            async with async_playwright() as p:
                # Ko-fi challenge pages are significantly more frequent in headless mode.
                # Prefer headed mode (under Xvfb on server) unless explicitly forced.
                force_headless = os.getenv("VITO_FORCE_HEADLESS", "0").lower() in {"1", "true", "yes", "on"}
                if not force_headless:
                    disp = ensure_display()
                    if not disp:
                        xvfb = XvfbSession(enabled=True)
                        xvfb.start()
                        disp = str(os.getenv("DISPLAY", "")).strip()
                    if not disp:
                        force_headless = True
                launch_args = [
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--disable-blink-features=AutomationControlled",
                ]
                launched_headed = False
                if not force_headless:
                    try:
                        logger.info(
                            "Ko-fi headed launch attempt",
                            extra={"event": "kofi_headed_launch_attempt", "context": {"display": str(os.getenv("DISPLAY", ""))}},
                        )
                        browser = await p.chromium.launch(
                            headless=False,
                            args=["--no-sandbox", "--disable-dev-shm-usage"],
                        )
                        launched_headed = True
                    except Exception as e2:
                        logger.warning(f"Ko-fi headed launch failed, fallback headless: {e2}")
                        browser = await p.chromium.launch(headless=True, args=launch_args)
                        launched_headed = False
                else:
                    browser = await p.chromium.launch(headless=True, args=launch_args)
                    launched_headed = False
                context = await browser.new_context(
                    storage_state=str(self._storage_state_path),
                    viewport={"width": 1366, "height": 900},
                )
                page = await context.new_page()
                try:
                    await page.goto("https://ko-fi.com/", wait_until="domcontentloaded", timeout=90000)
                    await page.wait_for_timeout(3200)
                    await page.mouse.move(200, 250)
                    await page.wait_for_timeout(600)
                    await page.mouse.move(980, 420)
                    await page.wait_for_timeout(700)
                except Exception:
                    pass
                landing_urls = [
                    "https://ko-fi.com/shop/settings?productType=0",
                    "https://ko-fi.com/shop/settings?src=sidemenu&productType=0",
                    "https://ko-fi.com/manage",
                ]
                for u in landing_urls:
                    await page.goto(u, wait_until="domcontentloaded", timeout=90000)
                    await page.wait_for_timeout(3800)
                    if "/404" not in (page.url or ""):
                        break
                current = page.url.lower()
                page_title = (await page.title()).strip().lower()
                body_text = (await page.text_content("body") or "").strip().lower()
                challenge_signals = (
                    "checking your browser before accessing",
                    "attention required",
                    "verify you are human",
                    "cf_chl_opt",
                    "turnstile",
                )
                challenge_like = any(x in body_text for x in challenge_signals) or "/cdn-cgi/challenge" in (page.url or "").lower()
                if "just a moment" in page_title or challenge_like:
                    # Cloudflare may auto-resolve in headed mode after a short delay.
                    await page.wait_for_timeout(12000)
                    page_title = (await page.title()).strip().lower()
                    body_text = (await page.text_content("body") or "").strip().lower()
                    challenge_like = any(x in body_text for x in challenge_signals) or "/cdn-cgi/challenge" in (page.url or "").lower()
                if "just a moment" in page_title or challenge_like:
                    # Attempt Turnstile solve via Anti-Captcha if sitekey is present.
                    try:
                        sitekey = await page.evaluate("""() => {
                            const el = document.querySelector('[data-sitekey]');
                            if (el) return el.getAttribute('data-sitekey') || '';
                            const ifr = document.querySelector("iframe[src*='challenges.cloudflare.com']");
                            if (ifr && ifr.src) {
                                const m = ifr.src.match(/[?&]sitekey=([^&]+)/i);
                                if (m) return m[1];
                            }
                            return '';
                        }""")
                        if sitekey:
                            from modules.captcha_solver import CaptchaSolver
                            token = CaptchaSolver.get_instance().solve_turnstile(str(sitekey), page.url)
                            if token:
                                await page.evaluate(
                                    """(tk) => {
                                        const fields = document.querySelectorAll(
                                            "input[name='cf-turnstile-response'], textarea[name='cf-turnstile-response']"
                                        );
                                        fields.forEach((f) => { f.value = tk; f.dispatchEvent(new Event('input', {bubbles:true})); });
                                    }""",
                                    token,
                                )
                                await page.wait_for_timeout(1800)
                    except Exception:
                        pass
                    # One reload retry before hard fail.
                    try:
                        await page.reload(wait_until="domcontentloaded", timeout=90000)
                        await page.wait_for_timeout(8000)
                        body_text = (await page.text_content("body") or "").strip().lower()
                        challenge_like = any(x in body_text for x in challenge_signals) or "/cdn-cgi/challenge" in (page.url or "").lower()
                    except Exception:
                        pass
                if "just a moment" in page_title or challenge_like:
                    return {
                        "platform": "kofi",
                        "status": "blocked",
                        "error": "cloudflare_challenge",
                        "url": page.url,
                        "launch_mode": "headed" if launched_headed else "headless",
                        "display": str(os.getenv("DISPLAY", "")),
                    }
                if "/login" in current or "/signin" in current:
                    return {
                        "platform": "kofi",
                        "status": "needs_browser_login",
                        "error": "Stored Ko-fi session expired.",
                        "storage_state": str(self._storage_state_path),
                    }
                if "/404" in current:
                    return {
                        "platform": "kofi",
                        "status": "blocked",
                        "error": "kofi_manage_path_not_available",
                        "url": page.url,
                    }

                # Cookie banner can block form interactions.
                for txt in ("Accept All", "Save My Preferences", "I accept", "Accept"):
                    try:
                        btn = page.get_by_role("button", name=txt)
                        if await btn.count():
                            await btn.first.click(timeout=1200)
                            await page.wait_for_timeout(800)
                            break
                    except Exception:
                        continue

                # If payment providers are not connected, product creation is blocked by Ko-fi UI.
                try:
                    provider_connect = await page.locator("a:has-text('Connect')").count()
                except Exception:
                    provider_connect = 0
                if provider_connect >= 1 and "/shop/settings" in (page.url or "").lower():
                    return {
                        "platform": "kofi",
                        "status": "blocked",
                        "error": "payments_not_connected",
                        "url": page.url,
                    }

                for sel in (
                    "input[name='postImageTitle']",
                    "input[name='title']",
                    "input[placeholder*='Title']",
                    "input[type='text']",
                ):
                    try:
                        loc = page.locator(sel)
                        if await loc.count():
                            await loc.first.fill(title[:120], timeout=1800)
                            break
                    except Exception:
                        continue
                for sel in (
                    "textarea[name='postImageDescription']",
                    "textarea[name='description']",
                    "textarea[placeholder*='Description']",
                    "textarea",
                ):
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

                # If editor controls are not present, treat as blocked/challenge instead of prepared.
                try:
                    title_inputs = await page.locator("input[name='title'], input[type='text']").count()
                    desc_areas = await page.locator("textarea[name='description'], textarea").count()
                    action_buttons = await page.locator(
                        "button:has-text('Publish'), button:has-text('Save'), button:has-text('Create'), button[type='submit']"
                    ).count()
                    if title_inputs == 0 and desc_areas == 0 and action_buttons == 0:
                        return {
                            "platform": "kofi",
                            "status": "blocked",
                            "error": "editor_controls_not_available",
                            "url": page.url,
                        }
                except Exception:
                    pass

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
                if not clicked:
                    for sel in (
                        "button:has-text('Publish')",
                        "button:has-text('Save')",
                        "button:has-text('Create')",
                        "button[type='submit']",
                        "input[type='submit']",
                    ):
                        try:
                            loc = page.locator(sel)
                            if await loc.count():
                                await loc.first.click(timeout=2500)
                                await page.wait_for_timeout(1500)
                                clicked = True
                                break
                        except Exception:
                            continue

                # Try extracting created shop-item URL if visible.
                detected_url = ""
                try:
                    href = await page.locator("a[href*='ko-fi.com/s/']").first.get_attribute("href")
                    if href:
                        detected_url = href if href.startswith("http") else f"https://ko-fi.com{href}"
                except Exception:
                    pass
                if not detected_url:
                    detected_url = created_url

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
                        evidence=detected_url,
                        source="kofi.publish.browser",
                        evidence_dict={"platform": "kofi", "title": title, "mode": "browser_only", "url": detected_url},
                    )
                except Exception:
                    pass
                return {
                    "platform": "kofi",
                    "status": status,
                    "title": title,
                    "price": price,
                    "mode": "browser_only",
                    "url": detected_url,
                    "screenshot_path": shot,
                }
        except Exception as e:
            return {"platform": "kofi", "status": "error", "error": str(e), "screenshot_path": shot}
        finally:
            try:
                if xvfb is not None:
                    xvfb.stop()
            except Exception:
                pass
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
