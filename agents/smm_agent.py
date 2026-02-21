"""SMMAgent — Agent 03: управление социальными сетями."""

import time
from typing import Any, Optional
from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType

logger = get_logger("smm_agent", agent="smm_agent")
SUPPORTED_PLATFORMS = ["instagram", "twitter", "linkedin", "tiktok"]


class SMMAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(name="smm_agent", description="Управление соцсетями: посты, хэштеги, планирование", **kwargs)
        self._scheduled_posts: list[dict] = []

    @property
    def capabilities(self) -> list[str]:
        return ["social_media", "scheduling"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type in ("social_media", "create_post"):
                result = await self.create_post(kwargs.get("platform", "instagram"), kwargs.get("content", kwargs.get("step", "")))
            elif task_type == "scheduling":
                result = await self.schedule_post(kwargs.get("platform", "instagram"), kwargs.get("content", ""), kwargs.get("publish_at", ""))
            elif task_type == "suggest_hashtags":
                result = await self.suggest_hashtags(kwargs.get("content", ""), kwargs.get("platform", "instagram"))
            else:
                result = await self.create_post("instagram", kwargs.get("step", task_type))
            result.duration_ms = int((time.monotonic() - start) * 1000)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def create_post(self, platform: str, content: str, style: str = None) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        style_note = f" Стиль: {style}." if style else ""
        response = await self.llm_router.call_llm(task_type=TaskType.CONTENT, prompt=f"Создай пост для {platform}.{style_note}\nТема: {content}", estimated_tokens=1000)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.005, f"SMM post: {platform}")
        return TaskResult(success=True, output=response, cost_usd=0.005, metadata={"platform": platform})

    async def schedule_post(self, platform: str, content: str, publish_at: str) -> TaskResult:
        post_result = await self.create_post(platform, content)
        if not post_result.success:
            return post_result
        entry = {"platform": platform, "content": post_result.output, "publish_at": publish_at, "status": "scheduled"}
        self._scheduled_posts.append(entry)
        return TaskResult(success=True, output={"scheduled": True, "platform": platform, "publish_at": publish_at, "post": post_result.output})

    async def suggest_hashtags(self, content: str, platform: str = "instagram") -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        response = await self.llm_router.call_llm(task_type=TaskType.CONTENT, prompt=f"Подбери 15-20 хэштегов для {platform} по теме: {content[:500]}", estimated_tokens=500)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        return TaskResult(success=True, output=response, cost_usd=0.003)
