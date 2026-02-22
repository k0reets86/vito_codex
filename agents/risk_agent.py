"""RiskAgent — Agent 12: оценка рисков, репутация, жалобы."""

import time
from typing import Any, Optional
from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType

logger = get_logger("risk_agent", agent="risk_agent")


class RiskAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(name="risk_agent", description="Управление рисками: оценка, репутация, жалобы", **kwargs)

    @property
    def capabilities(self) -> list[str]:
        return ["risk_assessment", "reputation"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type == "risk_assessment":
                result = await self.assess_risk(kwargs.get("action", kwargs.get("step", "")))
            elif task_type == "reputation":
                result = await self.monitor_reputation()
            elif task_type == "complaint":
                result = await self.handle_complaint(kwargs.get("complaint", {}))
            else:
                result = await self.assess_risk(kwargs.get("step", task_type))
            result.duration_ms = int((time.monotonic() - start) * 1000)
            self._track_result(result)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def assess_risk(self, action: str) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        response = await self._call_llm(
            task_type=TaskType.STRATEGY,
            prompt=f"Оцени риски действия: {action}\nОтветь в формате JSON:\n{{\"risk_level\": \"low/medium/high\", \"factors\": [...], \"recommendation\": \"...\"}}",
            estimated_tokens=1000,
        )
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.01, f"Risk assessment: {action[:50]}")
        return TaskResult(success=True, output=response, cost_usd=0.01)

    async def monitor_reputation(self) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        response = await self._call_llm(
            task_type=TaskType.ROUTINE,
            prompt="Составь чеклист мониторинга репутации для AI-бизнеса:\n- Отзывы на платформах\n- Упоминания в соцсетях\n- Рейтинги\nДай текущий статус: positive/neutral/negative.",
            estimated_tokens=1000,
        )
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        return TaskResult(success=True, output=response)

    async def handle_complaint(self, complaint: dict) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        complaint_text = "\n".join(f"{k}: {v}" for k, v in complaint.items())
        response = await self._call_llm(
            task_type=TaskType.CONTENT,
            prompt=f"Составь ответ на жалобу клиента:\n{complaint_text}\nТон: вежливый, решение-ориентированный. Предложи компенсацию если уместно.",
            estimated_tokens=1000,
        )
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        return TaskResult(success=True, output=response)
