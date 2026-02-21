"""Creative Fabrica Platform — Browser-based интеграция через BrowserAgent."""

from typing import Any

from config.logger import get_logger
from platforms.base_platform import BasePlatform

logger = get_logger("creative_fabrica", agent="creative_fabrica")


class CreativeFabricaPlatform(BasePlatform):
    def __init__(self, browser_agent=None, **kwargs):
        super().__init__(name="creative_fabrica", browser_agent=browser_agent, **kwargs)

    async def authenticate(self) -> bool:
        """Аутентификация через BrowserAgent."""
        if not self.browser_agent:
            logger.warning("BrowserAgent не подключён для Creative Fabrica", extra={"event": "cf_no_browser"})
            self._authenticated = False
            return False
        try:
            result = await self.browser_agent.execute_task(
                task_type="browse",
                url="https://www.creativefabrica.com/dashboard",
                action="check_login",
            )
            self._authenticated = result.success if result else False
            return self._authenticated
        except Exception as e:
            logger.error(f"Creative Fabrica auth error: {e}", extra={"event": "cf_auth_error"})
            self._authenticated = False
            return False

    async def publish(self, content: dict) -> dict:
        """Публикация через BrowserAgent — загрузка продукта."""
        if not self.browser_agent:
            return {"platform": "creative_fabrica", "status": "no_browser"}
        try:
            result = await self.browser_agent.execute_task(
                task_type="form_fill",
                url="https://www.creativefabrica.com/designer/upload",
                form_data=content,
            )
            return {
                "platform": "creative_fabrica",
                "status": "published" if result and result.success else "failed",
                "output": result.output if result else None,
            }
        except Exception as e:
            logger.error(f"Creative Fabrica publish error: {e}", extra={"event": "cf_publish_error"})
            return {"platform": "creative_fabrica", "status": "error", "error": str(e)}

    async def get_analytics(self) -> dict:
        """Аналитика через BrowserAgent."""
        if not self.browser_agent:
            return {"platform": "creative_fabrica", "sales": 0, "revenue": 0.0}
        try:
            result = await self.browser_agent.execute_task(
                task_type="browse",
                url="https://www.creativefabrica.com/designer/earnings",
                action="extract_text",
            )
            return {
                "platform": "creative_fabrica",
                "raw_data": result.output if result else None,
                "sales": 0,
                "revenue": 0.0,
            }
        except Exception as e:
            logger.error(f"Creative Fabrica analytics error: {e}", extra={"event": "cf_analytics_error"})
            return {"platform": "creative_fabrica", "sales": 0, "revenue": 0.0}

    async def health_check(self) -> bool:
        return self.browser_agent is not None
