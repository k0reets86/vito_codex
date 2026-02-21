"""Substack Platform — Browser-based интеграция через BrowserAgent."""

from typing import Any

from config.logger import get_logger
from platforms.base_platform import BasePlatform

logger = get_logger("substack", agent="substack")


class SubstackPlatform(BasePlatform):
    def __init__(self, browser_agent=None, **kwargs):
        super().__init__(name="substack", browser_agent=browser_agent, **kwargs)

    async def authenticate(self) -> bool:
        """Аутентификация через BrowserAgent."""
        if not self.browser_agent:
            logger.warning("BrowserAgent не подключён для Substack", extra={"event": "substack_no_browser"})
            self._authenticated = False
            return False
        try:
            result = await self.browser_agent.execute_task(
                task_type="browse",
                url="https://substack.com/dashboard",
                action="check_login",
            )
            self._authenticated = result.success if result else False
            return self._authenticated
        except Exception as e:
            logger.error(f"Substack auth error: {e}", extra={"event": "substack_auth_error"})
            self._authenticated = False
            return False

    async def publish(self, content: dict) -> dict:
        """Публикация через BrowserAgent — создание поста."""
        if not self.browser_agent:
            return {"platform": "substack", "status": "no_browser"}
        try:
            result = await self.browser_agent.execute_task(
                task_type="form_fill",
                url="https://substack.com/publish/post",
                form_data=content,
            )
            return {
                "platform": "substack",
                "status": "published" if result and result.success else "failed",
                "output": result.output if result else None,
            }
        except Exception as e:
            logger.error(f"Substack publish error: {e}", extra={"event": "substack_publish_error"})
            return {"platform": "substack", "status": "error", "error": str(e)}

    async def get_analytics(self) -> dict:
        """Аналитика через BrowserAgent (Substack Dashboard)."""
        if not self.browser_agent:
            return {"platform": "substack", "subscribers": 0, "posts": 0}
        try:
            result = await self.browser_agent.execute_task(
                task_type="browse",
                url="https://substack.com/dashboard",
                action="extract_text",
            )
            return {
                "platform": "substack",
                "raw_data": result.output if result else None,
                "subscribers": 0,
                "posts": 0,
            }
        except Exception as e:
            logger.error(f"Substack analytics error: {e}", extra={"event": "substack_analytics_error"})
            return {"platform": "substack", "subscribers": 0, "posts": 0}

    async def health_check(self) -> bool:
        return self.browser_agent is not None
