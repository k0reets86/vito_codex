"""Amazon KDP Platform — Browser-based интеграция через BrowserAgent."""

from pathlib import Path
from typing import Any

from config.logger import get_logger
from config.settings import settings
from modules.listing_optimizer import optimize_listing_payload
from platforms.base_platform import BasePlatform

logger = get_logger("amazon_kdp", agent="amazon_kdp")


class AmazonKDPPlatform(BasePlatform):
    def __init__(self, browser_agent=None, **kwargs):
        super().__init__(name="amazon_kdp", browser_agent=browser_agent, **kwargs)
        self._state_file = Path(str(getattr(settings, "KDP_STORAGE_STATE_FILE", "runtime/kdp_storage_state.json") or "runtime/kdp_storage_state.json"))

    async def _probe_saved_session(self) -> bool:
        if not self._state_file.exists():
            return False
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                args = [
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--renderer-process-limit=1",
                ]
                if bool(getattr(settings, "BROWSER_CONSTRAINED_MODE", True)):
                    args.extend(["--no-zygote", "--single-process"])
                browser = await p.chromium.launch(
                    headless=True,
                    args=args,
                )
                context = await browser.new_context(storage_state=str(self._state_file), viewport={"width": 1280, "height": 720})
                page = await context.new_page()
                await page.goto("https://kdp.amazon.com/bookshelf", wait_until="domcontentloaded", timeout=90000)
                await page.wait_for_timeout(1500)
                u = (page.url or "").lower()
                ok = ("/bookshelf" in u or "/reports" in u or "/en_us/" in u) and ("signin" not in u and "ap/signin" not in u)
                await context.close()
                await browser.close()
                return ok
        except Exception as e:
            logger.warning(f"KDP saved-session probe error: {e}", extra={"event": "kdp_session_probe_error"})
            return False

    async def authenticate(self) -> bool:
        """Аутентификация через BrowserAgent (KDP login page)."""
        # Preferred path: saved browser session (created by scripts/kdp_auth_helper.py).
        if self.browser_agent is None and await self._probe_saved_session():
            self._authenticated = True
            return True
        if not self.browser_agent:
            logger.warning("BrowserAgent не подключён для Amazon KDP", extra={"event": "kdp_no_browser"})
            self._authenticated = False
            return False
        try:
            result = await self.browser_agent.execute_task(
                task_type="browse",
                url="https://kdp.amazon.com/bookshelf",
            )
            if not result or not result.success:
                self._authenticated = False
                return False
            out = result.output
            if isinstance(out, dict):
                title = str(out.get("title", "")).lower()
                url = str(out.get("url", "")).lower()
            else:
                raw = str(out or "").lower()
                title = raw
                url = raw
            self._authenticated = "signin" not in title and "ap/signin" not in url
            return self._authenticated
        except Exception as e:
            logger.error(f"KDP auth error: {e}", extra={"event": "kdp_auth_error"})
            self._authenticated = False
            return False

    async def publish(self, content: dict) -> dict:
        """Публикация через BrowserAgent — заполнение форм KDP."""
        content = optimize_listing_payload("amazon_kdp", content or {})
        operation = str(content.get("operation") or "create").strip().lower()
        allow_existing_update = bool(content.get("allow_existing_update"))
        owner_edit_confirmed = bool(content.get("owner_edit_confirmed"))
        target_document_id = str(content.get("target_document_id") or content.get("target_book_id") or "").strip()
        if bool(getattr(settings, "PUBLISH_CREATE_GUARD_ENABLED", True)):
            if operation in {"create", "new"} and allow_existing_update:
                return {
                    "platform": "amazon_kdp",
                    "status": "blocked",
                    "error": "create_mode_forbids_existing_update",
                }
            if allow_existing_update and not owner_edit_confirmed:
                return {
                    "platform": "amazon_kdp",
                    "status": "blocked",
                    "error": "existing_update_requires_explicit_owner_request",
                }
            if allow_existing_update and not target_document_id:
                return {
                    "platform": "amazon_kdp",
                    "status": "blocked",
                    "error": "existing_update_requires_target_document_id",
                }
        if not self.browser_agent:
            return {"platform": "amazon_kdp", "status": "no_browser"}
        try:
            result = await self.browser_agent.execute_task(
                task_type="form_fill",
                url="https://kdp.amazon.com/bookshelf",
                form_data=content,
            )
            out = result.output if result else None
            evidence_url = ""
            evidence_id = ""
            evidence_path = ""
            if isinstance(out, dict):
                evidence_url = str(out.get("url") or out.get("book_url") or "").strip()
                evidence_id = str(out.get("id") or out.get("book_id") or "").strip()
                evidence_path = str(out.get("screenshot_path") or out.get("path") or "").strip()
            # Contract rule: "published" requires evidence fields; otherwise degrade to prepared.
            status = "failed"
            if result and result.success:
                has_evidence = bool(evidence_url or evidence_id or evidence_path)
                status = "published" if has_evidence else "prepared"
            return {
                "platform": "amazon_kdp",
                "status": status,
                "url": evidence_url,
                "id": evidence_id,
                "screenshot_path": evidence_path,
                "output": out,
            }
        except Exception as e:
            logger.error(f"KDP publish error: {e}", extra={"event": "kdp_publish_error"})
            return {"platform": "amazon_kdp", "status": "error", "error": str(e)}

    async def get_analytics(self) -> dict:
        """Получение аналитики через BrowserAgent (KDP Reports page)."""
        if not self.browser_agent:
            return {"platform": "amazon_kdp", "sales": 0, "revenue": 0.0}
        try:
            result = await self.browser_agent.execute_task(
                task_type="browse",
                url="https://kdp.amazon.com/reports",
                action="extract_text",
            )
            return {
                "platform": "amazon_kdp",
                "raw_data": result.output if result else None,
                "sales": 0,
                "revenue": 0.0,
            }
        except Exception as e:
            logger.error(f"KDP analytics error: {e}", extra={"event": "kdp_analytics_error"})
            return {"platform": "amazon_kdp", "sales": 0, "revenue": 0.0}

    async def health_check(self) -> bool:
        if self.browser_agent is not None:
            return True
        return False
