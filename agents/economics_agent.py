"""EconomicsAgent — Agent 16: ценообразование, юнит-экономика, P&L."""

import time
from typing import Any, Optional
from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType

logger = get_logger("economics_agent", agent="economics_agent")


class EconomicsAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(name="economics_agent", description="Экономика: ценообразование, юнит-экономика, P&L моделирование", **kwargs)

    @property
    def capabilities(self) -> list[str]:
        return ["pricing", "unit_economics"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type == "pricing":
                result = await self.suggest_price(kwargs.get("product", kwargs.get("step", "")))
            elif task_type == "unit_economics":
                result = await self.unit_economics(kwargs.get("product", kwargs.get("step", "")))
            elif task_type == "pnl":
                result = await self.model_pnl(kwargs.get("scenario", {}))
            else:
                result = await self.suggest_price(kwargs.get("step", task_type))
            result.duration_ms = int((time.monotonic() - start) * 1000)
            self._track_result(result)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def suggest_price(self, product: str) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        response = await self._call_llm(
            task_type=TaskType.STRATEGY,
            prompt=f"Предложи оптимальную цену для продукта: {product}\nУчти: конкурентов, ценность, целевую аудиторию, маржу.\nДай 3 варианта: economy, standard, premium.",
            estimated_tokens=1500,
        )
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.01, f"Pricing: {product[:50]}")
        return TaskResult(success=True, output=response, cost_usd=0.01)

    async def unit_economics(self, product: str) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        response = await self._call_llm(
            task_type=TaskType.STRATEGY,
            prompt=f"Рассчитай юнит-экономику для: {product}\nВключи: CAC, LTV, margin, breakeven point, payback period.",
            estimated_tokens=1500,
        )
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.01, f"Unit economics: {product[:50]}")
        return TaskResult(success=True, output=response, cost_usd=0.01)

    async def model_pnl(self, scenario: dict) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        scenario_text = "\n".join(f"{k}: {v}" for k, v in scenario.items())
        response = await self._call_llm(
            task_type=TaskType.STRATEGY,
            prompt=f"Смоделируй P&L для сценария:\n{scenario_text}\nДай прогноз: выручка, расходы, прибыль, ROI на 3/6/12 месяцев.",
            estimated_tokens=2000,
        )
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.02, "P&L modeling")
        return TaskResult(success=True, output=response, cost_usd=0.02)
