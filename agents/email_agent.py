"""EmailAgent — Agent 07: email-маркетинг, рассылки, автосерии."""

import time
from typing import Any, Optional
from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType

logger = get_logger("email_agent", agent="email_agent")


class EmailAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(name="email_agent", description="Email-маркетинг: рассылки, автосерии, управление подписчиками", **kwargs)
        self._subscribers: list[dict] = []

    @property
    def capabilities(self) -> list[str]:
        return ["email", "newsletter"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type == "newsletter":
                result = await self.create_newsletter(kwargs.get("topic", kwargs.get("step", "")), kwargs.get("audience", "subscribers"))
            elif task_type == "email":
                result = await self.create_sequence(kwargs.get("goal", kwargs.get("step", "")), kwargs.get("emails_count", 5))
            elif task_type == "manage_subscribers":
                result = await self.manage_subscribers(kwargs.get("action", "list"), kwargs.get("data", {}))
            else:
                result = await self.create_newsletter(kwargs.get("step", task_type), "subscribers")
            result.duration_ms = int((time.monotonic() - start) * 1000)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def create_newsletter(self, topic: str, audience: str, tone: str = "professional") -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        response = await self.llm_router.call_llm(task_type=TaskType.CONTENT, prompt=f"Напиши email-рассылку.\nТема: {topic}\nАудитория: {audience}\nТон: {tone}\nВключи: subject line, preheader, тело письма, CTA.", estimated_tokens=2000)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.01, f"Newsletter: {topic[:50]}")
        return TaskResult(success=True, output=response, cost_usd=0.01)

    async def create_sequence(self, goal: str, emails_count: int = 5) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        response = await self.llm_router.call_llm(task_type=TaskType.CONTENT, prompt=f"Создай email-автосерию из {emails_count} писем.\nЦель: {goal}\nДля каждого: subject, тело, CTA, интервал отправки.", estimated_tokens=3000)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.02, f"Email sequence: {goal[:50]}")
        return TaskResult(success=True, output=response, cost_usd=0.02)

    async def manage_subscribers(self, action: str, data: dict) -> TaskResult:
        if action == "list":
            return TaskResult(success=True, output=self._subscribers)
        elif action == "add":
            self._subscribers.append(data)
            return TaskResult(success=True, output={"added": True, "total": len(self._subscribers)})
        return TaskResult(success=True, output={"action": action, "status": "noted"})
