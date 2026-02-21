"""ECommerceAgent — Agent 05: управление листингами на платформах."""

import time
from typing import Any, Optional

from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger

logger = get_logger("ecommerce_agent", agent="ecommerce_agent")


class ECommerceAgent(BaseAgent):
    def __init__(self, platforms: dict = None, **kwargs):
        super().__init__(name="ecommerce_agent", description="Управление листингами (Gumroad, Etsy, Ko-fi)", **kwargs)
        self.platforms = platforms or {}

    @property
    def capabilities(self) -> list[str]:
        return ["listing_create", "sales_check", "ecommerce"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type in ("listing_create", "ecommerce"):
                result = await self.create_listing(kwargs.get("platform", "gumroad"), kwargs.get("data", kwargs))
            elif task_type == "sales_check":
                result = await self.check_sales(kwargs.get("platform"))
            elif task_type == "update_listing":
                result = await self.update_listing(kwargs.get("platform", ""), kwargs.get("listing_id", ""), kwargs.get("data", {}))
            else:
                result = TaskResult(success=False, error=f"Неизвестный task_type: {task_type}")
            result.duration_ms = int((time.monotonic() - start) * 1000)
            self._track_result(result)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def create_listing(self, platform: str, data: dict) -> TaskResult:
        plat = self.platforms.get(platform)
        if not plat:
            return TaskResult(success=False, error=f"Платформа '{platform}' не зарегистрирована. Доступны: {list(self.platforms.keys())}")
        try:
            result = await plat.publish(data)
            logger.info(f"Листинг создан на {platform}", extra={"event": "listing_created", "context": {"platform": platform}})
            return TaskResult(success=True, output=result)
        except Exception as e:
            return TaskResult(success=False, error=f"Ошибка создания листинга на {platform}: {e}")

    async def update_listing(self, platform: str, listing_id: str, data: dict) -> TaskResult:
        plat = self.platforms.get(platform)
        if not plat:
            return TaskResult(success=False, error=f"Платформа '{platform}' не зарегистрирована")
        try:
            if hasattr(plat, "update"):
                result = await plat.update(listing_id, data)
                return TaskResult(success=True, output=result)
            return TaskResult(success=False, error=f"Платформа {platform} не поддерживает обновление")
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def check_sales(self, platform: str = None) -> TaskResult:
        results = {}
        platforms_to_check = [platform] if platform else list(self.platforms.keys())
        for p_name in platforms_to_check:
            plat = self.platforms.get(p_name)
            if plat:
                try:
                    analytics = await plat.get_analytics()
                    results[p_name] = analytics
                except Exception as e:
                    results[p_name] = {"error": str(e)}
        return TaskResult(success=True, output=results)
