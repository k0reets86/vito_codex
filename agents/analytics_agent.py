"""AnalyticsAgent — Agent 09: ежедневный дашборд, аномалии, прогнозы."""

import time
from typing import Any, Optional
from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType

logger = get_logger("analytics_agent", agent="analytics_agent")


class AnalyticsAgent(BaseAgent):
    def __init__(self, registry=None, **kwargs):
        super().__init__(name="analytics_agent", description="Аналитика: дашборд, аномалии, прогнозы, ROI", **kwargs)
        self.registry = registry

    @property
    def capabilities(self) -> list[str]:
        return ["analytics", "dashboard", "forecast"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type == "dashboard":
                result = await self.daily_dashboard()
            elif task_type == "anomalies":
                result = await self.detect_anomalies()
            elif task_type == "forecast":
                result = await self.forecast_revenue(kwargs.get("days", 30))
            elif task_type == "agent_performance":
                result = await self.agent_performance()
            else:
                result = await self.daily_dashboard()
            result.duration_ms = int((time.monotonic() - start) * 1000)
            self._track_result(result)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def daily_dashboard(self) -> TaskResult:
        data = {}
        if self.finance:
            try:
                data["daily_spend"] = self.finance.get_daily_spend()
            except Exception:
                data["daily_spend"] = 0.0
            try:
                data["daily_revenue"] = self.finance.get_daily_revenue()
            except Exception:
                data["daily_revenue"] = 0.0
        data["timestamp"] = time.strftime("%Y-%m-%d %H:%M")
        return TaskResult(success=True, output=data)

    async def detect_anomalies(self) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        stats = {}
        if self.finance:
            try:
                stats["daily_spend"] = self.finance.get_daily_spend()
            except Exception:
                pass
        response = await self._call_llm(
            task_type=TaskType.ROUTINE,
            prompt=f"Проанализируй метрики и найди аномалии:\n{stats}\nОтветь кратко: есть ли отклонения?",
            estimated_tokens=500,
        )
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        return TaskResult(success=True, output=response)

    async def forecast_revenue(self, days: int = 30) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        response = await self._call_llm(
            task_type=TaskType.STRATEGY,
            prompt=f"Спрогнозируй выручку на {days} дней. Учти текущие тренды. Дай оценку в USD.",
            estimated_tokens=1000,
        )
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.01, f"Forecast {days}d")
        return TaskResult(success=True, output=response, cost_usd=0.01)

    async def agent_performance(self) -> TaskResult:
        if not self.registry:
            return TaskResult(success=True, output={"status": "no registry attached"})
        try:
            statuses = self.registry.get_all_statuses()
            summary = [
                {
                    "name": s.get("name"),
                    "completed": s.get("tasks_completed", 0),
                    "failed": s.get("tasks_failed", 0),
                    "cost_usd": s.get("total_cost", 0),
                    "status": s.get("status"),
                }
                for s in statuses
            ]
            return TaskResult(success=True, output=summary)
        except Exception as e:
            return TaskResult(success=False, error=str(e))
