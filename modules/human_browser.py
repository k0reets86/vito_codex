from __future__ import annotations

import os
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.paths import root_path
from config.settings import settings


@dataclass(frozen=True)
class HumanBrowserContextSpec:
    service: str
    storage_state_path: str
    persistent_profile_dir: str
    screenshot_first_default: bool
    anti_bot_humanize: bool
    headless_preferred: bool
    llm_navigation_allowed: bool


def _random_delay_ms(lo: int, hi: int) -> int:
    lo2 = int(min(lo, hi))
    hi2 = int(max(lo, hi))
    return random.randint(lo2, hi2)


def profile_dir_for_service(service: str) -> str:
    svc = (str(service or "").strip().lower() or "generic").replace("/", "_")
    return root_path("runtime", "browser_profiles", svc)


class HumanBrowser:
    """Thin browser runtime wrapper with pacing, screenshots and service-aware context."""

    def __init__(self, logger=None):
        self.logger = logger

    def build_context_spec(self, profile: dict[str, Any]) -> HumanBrowserContextSpec:
        service = str(profile.get("service") or "generic").strip().lower() or "generic"
        storage_state_path = str(profile.get("storage_state_path") or "").strip()
        persistent_profile_dir = str(profile.get("persistent_profile_dir") or profile_dir_for_service(service))
        return HumanBrowserContextSpec(
            service=service,
            storage_state_path=storage_state_path,
            persistent_profile_dir=persistent_profile_dir,
            screenshot_first_default=bool(profile.get("screenshot_first_default")),
            anti_bot_humanize=bool(profile.get("anti_bot_humanize", True)),
            headless_preferred=bool(profile.get("headless_preferred", True)),
            llm_navigation_allowed=bool(profile.get("llm_navigation_allowed", False)),
        )

    @staticmethod
    def resolve_browser_engine(preferred: str | None = None) -> tuple[str, Any]:
        preferred_engine = str(preferred or getattr(settings, "BROWSER_AUTOMATION_ENGINE", "auto") or "auto").strip().lower()
        preferred_engine = preferred_engine if preferred_engine in {"auto", "playwright", "patchright"} else "auto"
        errors: list[str] = []
        if preferred_engine in {"auto", "patchright"}:
            try:
                from patchright.async_api import async_playwright as async_patchright

                return "patchright", async_patchright
            except Exception as exc:
                errors.append(f"patchright:{exc}")
                if preferred_engine == "patchright":
                    raise RuntimeError("patchright_unavailable")
        try:
            from playwright.async_api import async_playwright

            return "playwright", async_playwright
        except Exception as exc:
            errors.append(f"playwright:{exc}")
        raise RuntimeError("browser_engine_unavailable:" + " | ".join(errors))

    async def prepare_page(self, page, *, profile: dict[str, Any]) -> None:
        if bool(getattr(settings, "BROWSER_HUMANIZE_ENABLED", True)) and bool(profile.get("anti_bot_humanize", True)):
            await page.wait_for_timeout(_random_delay_ms(120, 420))

    async def before_navigation(self, page, *, profile: dict[str, Any], url: str = "") -> None:
        if bool(getattr(settings, "BROWSER_HUMANIZE_ENABLED", True)) and bool(profile.get("anti_bot_humanize", True)):
            await page.wait_for_timeout(_random_delay_ms(90, 260))

    async def after_navigation(self, page, *, profile: dict[str, Any], url: str = "") -> None:
        if bool(getattr(settings, "BROWSER_HUMANIZE_ENABLED", True)) and bool(profile.get("anti_bot_humanize", True)):
            await self.idle_scroll(page, profile=profile)
            await page.wait_for_timeout(_random_delay_ms(120, 340))

    async def click(self, page, selector: str, *, profile: dict[str, Any], timeout: int | None = None) -> None:
        if bool(getattr(settings, "BROWSER_HUMANIZE_ENABLED", True)) and bool(profile.get("anti_bot_humanize", True)):
            try:
                await page.locator(selector).hover(timeout=timeout or 4000)
            except Exception:
                pass
            await page.wait_for_timeout(_random_delay_ms(70, 180))
        await page.click(selector, timeout=timeout or 5000)

    async def type_text(self, page, selector: str, value: str, *, profile: dict[str, Any]) -> None:
        text = str(value or "")
        if not text:
            await page.fill(selector, "")
            return
        if bool(getattr(settings, "BROWSER_HUMANIZE_ENABLED", True)) and bool(profile.get("anti_bot_humanize", True)):
            await page.click(selector, timeout=5000)
            try:
                await page.fill(selector, "")
            except Exception:
                pass
            for chunk in self._chunk_text(text):
                await page.type(selector, chunk, delay=_random_delay_ms(20, 55))
                await page.wait_for_timeout(_random_delay_ms(20, 90))
            return
        await page.fill(selector, text)

    async def idle_scroll(self, page, *, profile: dict[str, Any]) -> None:
        if not bool(getattr(settings, "BROWSER_HUMANIZE_ENABLED", True)) or not bool(profile.get("anti_bot_humanize", True)):
            return
        try:
            for delta in (120, 180, -90):
                await page.mouse.wheel(0, delta)
                await page.wait_for_timeout(_random_delay_ms(40, 120))
        except Exception:
            try:
                await page.evaluate("window.scrollBy(0, 180)")
            except Exception:
                pass

    async def capture(self, page, *, service: str, task_type: str, path: str = "") -> str:
        final_path = str(path or self.default_screenshot_path(service, task_type))
        await page.screenshot(path=final_path, full_page=True)
        return final_path

    def context_kwargs(self, profile: dict[str, Any], *, user_agent: str, locale: str, timezone_id: str) -> dict[str, Any]:
        spec = self.build_context_spec(profile)
        kwargs: dict[str, Any] = {
            "viewport": {"width": 1280, "height": 720},
            "user_agent": user_agent,
            "locale": locale,
            "timezone_id": timezone_id,
        }
        storage = spec.storage_state_path
        if storage and os.path.exists(storage):
            kwargs["storage_state"] = storage
        Path(spec.persistent_profile_dir).mkdir(parents=True, exist_ok=True)
        return kwargs

    @staticmethod
    def has_persistent_profile_data(profile: dict[str, Any]) -> bool:
        spec = HumanBrowser().build_context_spec(profile)
        path = Path(spec.persistent_profile_dir)
        if not path.exists() or not path.is_dir():
            return False
        try:
            return any(path.iterdir())
        except Exception:
            return False

    async def launch_managed_context(
        self,
        browser_type,
        *,
        profile: dict[str, Any],
        headless: bool,
        launch_args: list[str] | None = None,
        user_agent: str,
        locale: str,
        timezone_id: str,
        viewport: dict[str, int] | None = None,
    ):
        """Launch browser+context using storage_state first, then persistent profile fallback."""
        spec = self.build_context_spec(profile)
        args = list(launch_args or [])
        viewport = viewport or {"width": 1280, "height": 720}
        Path(spec.persistent_profile_dir).mkdir(parents=True, exist_ok=True)

        if spec.storage_state_path and os.path.exists(spec.storage_state_path):
            browser = await browser_type.launch(headless=headless, args=args)
            context = await browser.new_context(
                storage_state=spec.storage_state_path,
                viewport=viewport,
                user_agent=user_agent,
                locale=locale,
                timezone_id=timezone_id,
            )
            return browser, context, "storage_state"

        if self.has_persistent_profile_data(profile):
            context = await browser_type.launch_persistent_context(
                user_data_dir=spec.persistent_profile_dir,
                headless=headless,
                args=args,
                viewport=viewport,
                user_agent=user_agent,
                locale=locale,
                timezone_id=timezone_id,
            )
            return None, context, "persistent_profile"

        browser = await browser_type.launch(headless=headless, args=args)
        context = await browser.new_context(
            viewport=viewport,
            user_agent=user_agent,
            locale=locale,
            timezone_id=timezone_id,
        )
        return browser, context, "fresh"

    @staticmethod
    def default_screenshot_path(service: str, task_type: str) -> str:
        svc = str(service or "generic").strip().lower() or "generic"
        task = str(task_type or "step").strip().lower() or "step"
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"/tmp/{svc}_{task}_{ts}.png"

    @staticmethod
    def _chunk_text(value: str, size: int = 12) -> list[str]:
        text = str(value or "")
        if not text:
            return []
        return [text[i:i + size] for i in range(0, len(text), size)]
