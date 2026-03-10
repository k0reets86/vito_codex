"""Substack Platform — browser-first operational adapter."""

from config.logger import get_logger
from config.settings import settings
from modules.browser_platform_runtime import browser_auth_probe, browser_extract_analytics, browser_publish_form, resolve_storage_state
from platforms.base_platform import BasePlatform

logger = get_logger("substack", agent="substack")


class SubstackPlatform(BasePlatform):
    def __init__(self, browser_agent=None, **kwargs):
        super().__init__(name="substack", browser_agent=browser_agent, **kwargs)
        self._storage_state_path = resolve_storage_state(
            getattr(settings, "SUBSTACK_STORAGE_STATE_FILE", ""),
            "runtime/substack_storage_state.json",
        )

    async def authenticate(self) -> bool:
        if not self.browser_agent:
            logger.warning("BrowserAgent не подключён для Substack", extra={"event": "substack_no_browser"})
            self._authenticated = False
            return False
        try:
            self._authenticated = await browser_auth_probe(
                browser_agent=self.browser_agent,
                service="substack",
                url="https://substack.com/home",
                storage_state_path=self._storage_state_path,
            )
            return self._authenticated
        except Exception as e:
            logger.error(f"Substack auth error: {e}", extra={"event": "substack_auth_error"})
            self._authenticated = False
            return False

    async def publish(self, content: dict) -> dict:
        if not self.browser_agent:
            return {"platform": "substack", "status": "no_browser"}
        try:
            return await browser_publish_form(
                browser_agent=self.browser_agent,
                service="substack",
                url="https://substack.com/publish/post",
                form_data=content,
                success_status="draft",
            )
        except Exception as e:
            logger.error(f"Substack publish error: {e}", extra={"event": "substack_publish_error"})
            return {"platform": "substack", "status": "error", "error": str(e)}

    async def get_analytics(self) -> dict:
        if not self.browser_agent:
            return {"platform": "substack", "subscribers": 0, "posts": 0}
        try:
            result = await browser_extract_analytics(
                browser_agent=self.browser_agent,
                service="substack",
                url="https://substack.com/home",
            )
            return {**result, "subscribers": 0, "posts": 0}
        except Exception as e:
            logger.error(f"Substack analytics error: {e}", extra={"event": "substack_analytics_error"})
            return {"platform": "substack", "subscribers": 0, "posts": 0}

    async def health_check(self) -> bool:
        return self.browser_agent is not None
