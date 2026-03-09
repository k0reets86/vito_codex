"""EmailAgent — Agent 07: email-маркетинг, рассылки, автосерии."""

import time
from typing import Any

from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType

logger = get_logger("email_agent", agent="email_agent")


class EmailAgent(BaseAgent):
    NEEDS = {
        "newsletter": ["marketing_strategy", "seo"],
        "email": ["marketing_strategy"],
        "manage_subscribers": [],
        "default": [],
    }

    def __init__(self, **kwargs):
        super().__init__(name="email_agent", description="Email-маркетинг: рассылки, автосерии, управление подписчиками", **kwargs)
        self._subscribers: list[dict] = []

    @property
    def capabilities(self) -> list[str]:
        return ["email", "newsletter", "manage_subscribers"]

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
        local = self._local_newsletter(topic, audience, tone)
        if not self.llm_router:
            return TaskResult(success=True, output=local, metadata={"mode": "local_fallback"})
        response = await self._call_llm(
            task_type=TaskType.CONTENT,
            prompt=f"Напиши email-рассылку.\nТема: {topic}\nАудитория: {audience}\nТон: {tone}\nВключи: subject line, preheader, тело письма, CTA.",
            estimated_tokens=2000,
        )
        if response:
            self._record_expense(0.01, f"Newsletter: {topic[:50]}")
            local["llm_notes"] = response
        return TaskResult(success=True, output=local, cost_usd=0.01 if response else 0.0)

    async def create_sequence(self, goal: str, emails_count: int = 5) -> TaskResult:
        local = self._local_sequence(goal, emails_count)
        if not self.llm_router:
            return TaskResult(success=True, output=local, metadata={"mode": "local_fallback"})
        response = await self._call_llm(
            task_type=TaskType.CONTENT,
            prompt=f"Создай email-автосерию из {emails_count} писем.\nЦель: {goal}\nДля каждого: subject, тело, CTA, интервал отправки.",
            estimated_tokens=3000,
        )
        if response:
            self._record_expense(0.02, f"Email sequence: {goal[:50]}")
            local["llm_notes"] = response
        return TaskResult(success=True, output=local, cost_usd=0.02 if response else 0.0)

    async def manage_subscribers(self, action: str, data: dict) -> TaskResult:
        if action == "list":
            return TaskResult(success=True, output={"subscribers": self._subscribers, "total": len(self._subscribers)})
        if action == "add":
            self._subscribers.append(data)
            return TaskResult(success=True, output={"added": True, "total": len(self._subscribers)})
        return TaskResult(success=True, output={"action": action, "status": "noted"})

    def _local_newsletter(self, topic: str, audience: str, tone: str) -> dict[str, Any]:
        topic = (topic or "Weekly update").strip()
        audience = (audience or "subscribers").strip()
        return {
            "subject": f"{topic}: a practical update for {audience}"[:90],
            "preheader": f"A concise breakdown and next step for {audience}.",
            "body": f"Hi,\n\nHere is a focused update on {topic}. We pulled out the practical points and the next action you can take today.\n\nBest,\nTeam",
            "cta": "Reply for the full pack",
            "tone": tone,
            "audience": audience,
        }

    def _local_sequence(self, goal: str, emails_count: int) -> dict[str, Any]:
        goal = (goal or "conversion").strip()
        steps = []
        for idx in range(max(int(emails_count), 1)):
            steps.append(
                {
                    "email_number": idx + 1,
                    "subject": f"{goal.title()} email {idx + 1}",
                    "purpose": "educate" if idx == 0 else "convert" if idx == emails_count - 1 else "nurture",
                    "cta": "Continue",
                    "delay_days": idx,
                }
            )
        return {"goal": goal, "emails": steps}
