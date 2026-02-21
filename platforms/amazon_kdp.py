"""Amazon KDP Platform — Browser-based интеграция через BrowserAgent."""

from typing import Any

from config.logger import get_logger
from platforms.base_platform import BasePlatform

logger = get_logger("amazon_kdp", agent="amazon_kdp")


class AmazonKDPPlatform(BasePlatform):
    def __init__(self, browser_agent=None, **kwargs):
        super().__init__(name="amazon_kdp", browser_agent=browser_agent, **kwargs)

    async def authenticate(self) -> bool:
        """Аутентификация через BrowserAgent (KDP login page)."""
        if not self.browser_agent:
            logger.warning("BrowserAgent не подключён для Amazon KDP", extra={"event": "kdp_no_browser"})
            self._authenticated = False
            return False
        try:
            result = await self.browser_agent.execute_task(
                task_type="browse",
                url="https://kdp.amazon.com",
                action="check_login",
            )
            self._authenticated = result.success if result else False
            return self._authenticated
        except Exception as e:
            logger.error(f"KDP auth error: {e}", extra={"event": "kdp_auth_error"})
            self._authenticated = False
            return False

    async def publish(self, content: dict) -> dict:
        """Публикация через BrowserAgent — заполнение форм KDP."""
        if not self.browser_agent:
            return {"platform": "amazon_kdp", "status": "no_browser"}
        try:
            result = await self.browser_agent.execute_task(
                task_type="form_fill",
                url="https://kdp.amazon.com/bookshelf",
                form_data=content,
            )
            return {
                "platform": "amazon_kdp",
                "status": "published" if result and result.success else "failed",
                "output": result.output if result else None,
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
        return self.browser_agent is not None
