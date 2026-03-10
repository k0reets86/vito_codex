"""Creative Fabrica Platform — browser-first operational adapter."""

from config.logger import get_logger
from config.settings import settings
from modules.browser_platform_runtime import browser_auth_probe, browser_extract_analytics, browser_publish_form, resolve_storage_state
from platforms.base_platform import BasePlatform

logger = get_logger("creative_fabrica", agent="creative_fabrica")


class CreativeFabricaPlatform(BasePlatform):
    def __init__(self, browser_agent=None, **kwargs):
        super().__init__(name="creative_fabrica", browser_agent=browser_agent, **kwargs)
        self._storage_state_path = resolve_storage_state(
            getattr(settings, "CREATIVE_FABRICA_STORAGE_STATE_FILE", ""),
            "runtime/creative_fabrica_storage_state.json",
        )

    async def authenticate(self) -> bool:
        if not self.browser_agent:
            logger.warning("BrowserAgent не подключён для Creative Fabrica", extra={"event": "cf_no_browser"})
            self._authenticated = False
            return False
        try:
            self._authenticated = await browser_auth_probe(
                browser_agent=self.browser_agent,
                service="creative_fabrica",
                url="https://www.creativefabrica.com/designer/dashboard",
                storage_state_path=self._storage_state_path,
            )
            return self._authenticated
        except Exception as e:
            logger.error(f"Creative Fabrica auth error: {e}", extra={"event": "cf_auth_error"})
            self._authenticated = False
            return False

    async def publish(self, content: dict) -> dict:
        if not self.browser_agent:
            return self._finalize_publish_result({"platform": "creative_fabrica", "status": "no_browser"}, mode="browser")
        try:
            result = await browser_publish_form(
                browser_agent=self.browser_agent,
                service="creative_fabrica",
                url="https://www.creativefabrica.com/designer/upload",
                form_data=content,
                success_status="draft",
            )
            return self._finalize_publish_result(result, mode="browser")
        except Exception as e:
            logger.error(f"Creative Fabrica publish error: {e}", extra={"event": "cf_publish_error"})
            return self._finalize_publish_result({"platform": "creative_fabrica", "status": "error", "error": str(e)}, mode="browser")

    async def get_analytics(self) -> dict:
        if not self.browser_agent:
            return self._finalize_analytics_result({"platform": "creative_fabrica", "sales": 0, "revenue": 0.0}, source="browser_earnings")
        try:
            result = await browser_extract_analytics(
                browser_agent=self.browser_agent,
                service="creative_fabrica",
                url="https://www.creativefabrica.com/designer/earnings",
            )
            return self._finalize_analytics_result({**result, "sales": 0, "revenue": 0.0}, source="browser_earnings")
        except Exception as e:
            logger.error(f"Creative Fabrica analytics error: {e}", extra={"event": "cf_analytics_error"})
            return self._finalize_analytics_result({"platform": "creative_fabrica", "sales": 0, "revenue": 0.0}, source="browser_earnings")

    async def health_check(self) -> bool:
        return self.browser_agent is not None
