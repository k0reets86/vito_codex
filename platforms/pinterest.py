"""PinterestPlatform — browser-first adapter with optional API fallback."""

from __future__ import annotations

import os
import re
from pathlib import Path

from config.logger import get_logger
from config.paths import PROJECT_ROOT
from config.settings import settings
from modules.execution_facts import ExecutionFacts
from modules.xvfb_session import XvfbSession
from platforms.base_platform import BasePlatform

logger = get_logger("pinterest", agent="pinterest")


class PinterestPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="pinterest", **kwargs)
        self._token = str(getattr(settings, "PINTEREST_ACCESS_TOKEN", "") or "")
        self._mode = str(getattr(settings, "PINTEREST_MODE", "browser") or "browser").strip().lower()
        self._storage_state_path = Path(
            str(getattr(settings, "PINTEREST_STORAGE_STATE_FILE", "runtime/pinterest_storage_state.json") or "runtime/pinterest_storage_state.json")
        )
        if not self._storage_state_path.is_absolute():
            self._storage_state_path = PROJECT_ROOT / self._storage_state_path

    async def authenticate(self) -> bool:
        if self._mode == "browser":
            self._authenticated = self._storage_state_path.exists()
            return self._authenticated
        self._authenticated = bool(self._token)
        return self._authenticated

    async def publish(self, content: dict) -> dict:
        if content.get("dry_run"):
            text = str(content.get("text") or content.get("title") or "").strip()[:150]
            return {"platform": "pinterest", "status": "prepared", "dry_run": True, "preview": text}
        if self._mode == "browser":
            return await self._publish_browser(content or {})
        if not self._token:
            return {"platform": "pinterest", "status": "not_configured", "error": "PINTEREST_ACCESS_TOKEN missing"}
        return {"platform": "pinterest", "status": "not_implemented", "error": "Pinterest API publish path not wired yet"}

    async def _publish_browser(self, content: dict) -> dict:
        if not self._storage_state_path.exists():
            return {
                "platform": "pinterest",
                "status": "needs_browser_login",
                "error": "Pinterest browser session required.",
                "storage_state": str(self._storage_state_path),
            }
        try:
            from playwright.async_api import async_playwright
        except Exception:
            return {"platform": "pinterest", "status": "error", "error": "playwright_not_installed"}

        title = str(content.get("title") or content.get("name") or "VITO Pin").strip()
        description = str(content.get("description") or content.get("text") or "").strip()
        target_url = str(content.get("url") or content.get("target_url") or "").strip()
        media_path = str(content.get("image_path") or content.get("cover_path") or "").strip()

        shot = str(PROJECT_ROOT / "runtime" / "pinterest_browser_publish.png")
        page_html = str(PROJECT_ROOT / "runtime" / "pinterest_browser_publish.html")

        browser = None
        context = None
        page = None
        xvfb = None
        try:
            async with async_playwright() as p:
                # Pinterest anti-bot is stricter in headless. Prefer headed mode unless forced.
                force_headless = os.getenv("VITO_FORCE_HEADLESS", "0").lower() in {"1", "true", "yes", "on"}
                launch_args = [
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ]
                xvfb = XvfbSession(enabled=not force_headless)
                xvfb.start()
                launched_headed = False
                if not force_headless:
                    try:
                        browser = await p.chromium.launch(
                            headless=False,
                            args=["--no-sandbox", "--disable-dev-shm-usage"],
                        )
                        launched_headed = True
                    except Exception as e2:
                        logger.warning(f"Pinterest headed launch failed, fallback headless: {e2}")
                        browser = await p.chromium.launch(headless=True, args=launch_args)
                        launched_headed = False
                else:
                    browser = await p.chromium.launch(headless=True, args=launch_args)
                    launched_headed = False
                context = await browser.new_context(
                    storage_state=str(self._storage_state_path),
                    viewport={"width": 1366, "height": 900},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
                )
                page = await context.new_page()
                # Warm-up home first, then open creation tool (reduces challenge frequency).
                await page.goto("https://www.pinterest.com/", wait_until="domcontentloaded", timeout=90000)
                await page.wait_for_timeout(3200)
                try:
                    await page.mouse.move(240, 220)
                    await page.wait_for_timeout(500)
                    await page.mouse.wheel(0, 360)
                    await page.wait_for_timeout(900)
                    await page.mouse.move(980, 520)
                    await page.wait_for_timeout(700)
                except Exception:
                    pass
                await page.goto("https://www.pinterest.com/pin-creation-tool/", wait_until="domcontentloaded", timeout=90000)
                await page.wait_for_timeout(3200)
                current = (page.url or "").lower()
                title_now = (await page.title() or "").lower()
                body_now = (await page.text_content("body") or "").lower()
                challenge_signals = (
                    "cf_chl_opt",
                    "turnstile",
                    "attention required",
                    "checking your browser before accessing",
                )
                challenge_like = any(x in body_now for x in challenge_signals) or "/cdn-cgi/challenge" in (page.url or "").lower()
                # Prevent false positives on normal localized pages: if editor controls exist, do not treat as challenge.
                try:
                    editor_controls = (
                        await page.locator("input[type='file'], textarea, div[contenteditable='true']").count()
                    )
                except Exception:
                    editor_controls = 0
                if editor_controls > 0 and "/pin-creation-tool" in current:
                    challenge_like = False
                if challenge_like or "just a moment" in title_now:
                    # In headed mode challenge can resolve automatically after a short wait.
                    await page.wait_for_timeout(4500)
                    title_now = (await page.title() or "").lower()
                    body_now = (await page.text_content("body") or "").lower()
                    challenge_like = any(x in body_now for x in challenge_signals) or "/cdn-cgi/challenge" in (page.url or "").lower()
                    try:
                        editor_controls = (
                            await page.locator("input[type='file'], textarea, div[contenteditable='true']").count()
                        )
                    except Exception:
                        editor_controls = 0
                    if editor_controls > 0 and "/pin-creation-tool" in (page.url or "").lower():
                        challenge_like = False
                if challenge_like or "just a moment" in title_now:
                    # Attempt Turnstile solve via Anti-Captcha if sitekey present.
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
                                await page.wait_for_timeout(1600)
                    except Exception:
                        pass
                    try:
                        await page.reload(wait_until="domcontentloaded", timeout=90000)
                        await page.wait_for_timeout(2200)
                        title_now = (await page.title() or "").lower()
                        body_now = (await page.text_content("body") or "").lower()
                        challenge_like = any(x in body_now for x in challenge_signals) or "/cdn-cgi/challenge" in (page.url or "").lower()
                        try:
                            editor_controls = (
                                await page.locator("input[type='file'], textarea, div[contenteditable='true']").count()
                            )
                        except Exception:
                            editor_controls = 0
                        if editor_controls > 0 and "/pin-creation-tool" in (page.url or "").lower():
                            challenge_like = False
                    except Exception:
                        pass
                if challenge_like or "just a moment" in title_now:
                    return {
                        "platform": "pinterest",
                        "status": "blocked",
                        "error": "anti_bot_challenge_or_timeout",
                        "url": page.url,
                        "launch_mode": "headed" if launched_headed else "headless",
                        "display": str(os.getenv("DISPLAY", "")),
                    }
                if any(x in current for x in ("/login", "session/new", "signup", "authenticate")):
                    return {
                        "platform": "pinterest",
                        "status": "needs_browser_login",
                        "error": "Stored Pinterest session expired.",
                        "storage_state": str(self._storage_state_path),
                    }

                if media_path:
                    try:
                        fi = page.locator("input[type='file']")
                        if await fi.count():
                            await fi.first.set_input_files(media_path, timeout=5000)
                            await page.wait_for_timeout(1200)
                    except Exception:
                        pass

                for sel in (
                    "textarea[aria-label*='title' i]",
                    "textarea[data-test-id*='pin-title' i]",
                    "div[contenteditable='true'][aria-label*='title' i]",
                ):
                    try:
                        loc = page.locator(sel)
                        if await loc.count():
                            await loc.first.fill(title[:100], timeout=2000)
                            break
                    except Exception:
                        continue

                for sel in (
                    "textarea[aria-label*='description' i]",
                    "div[contenteditable='true'][aria-label*='description' i]",
                ):
                    try:
                        loc = page.locator(sel)
                        if await loc.count():
                            await loc.first.fill(description[:500], timeout=2000)
                            break
                    except Exception:
                        continue

                if target_url:
                    for sel in ("input[placeholder*='Link' i]", "input[aria-label*='Link' i]", "input[type='url']"):
                        try:
                            loc = page.locator(sel)
                            if await loc.count():
                                await loc.first.fill(target_url[:512], timeout=2000)
                                break
                        except Exception:
                            continue

                pin_url = ""
                for btxt in ("Publish", "Опубликовать", "Save", "Сохранить"):
                    try:
                        btn = page.get_by_role("button", name=btxt)
                        if await btn.count():
                            await btn.first.click(timeout=2500)
                            await page.wait_for_timeout(2200)
                            break
                    except Exception:
                        continue
                now_url = str(page.url or "")
                if "/pin/" in now_url:
                    pin_url = now_url
                if not pin_url:
                    try:
                        html = await page.content()
                        m = re.search(r"https://(?:[a-z]{2}\.)?pinterest\.com/pin/\d+/?", html, re.IGNORECASE)
                        if m:
                            pin_url = m.group(0)
                    except Exception:
                        pass
                try:
                    await page.screenshot(path=shot, full_page=True)
                except Exception:
                    pass
                try:
                    Path(page_html).parent.mkdir(parents=True, exist_ok=True)
                    Path(page_html).write_text(await page.content(), encoding="utf-8")
                except Exception:
                    pass

                status = "published" if pin_url else "prepared"
                try:
                    ExecutionFacts().record(
                        action="platform:publish",
                        status=status,
                        detail=f"pinterest browser {status}",
                        evidence=pin_url or now_url,
                        source="pinterest.publish.browser",
                        evidence_dict={"platform": "pinterest", "status": status, "url": pin_url or now_url},
                    )
                except Exception:
                    pass
                return {
                    "platform": "pinterest",
                    "status": status,
                    "url": pin_url or now_url,
                    "mode": "browser_only",
                    "screenshot_path": shot,
                }
        except Exception as e:
            return {"platform": "pinterest", "status": "error", "error": str(e), "screenshot_path": shot}
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

    async def get_analytics(self) -> dict:
        return {"platform": "pinterest", "note": "basic browser-first adapter"}

    async def health_check(self) -> bool:
        return bool(await self.authenticate())
