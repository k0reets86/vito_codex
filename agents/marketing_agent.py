"""MarketingAgent — Agent 04: стратегия, воронки, рекламные тексты."""

import time
from typing import Any, Optional
from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType

logger = get_logger("marketing_agent", agent="marketing_agent")


class MarketingAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(name="marketing_agent", description="Маркетинговая стратегия, воронки продаж, рекламные тексты", **kwargs)

    @property
    def capabilities(self) -> list[str]:
        return ["marketing_strategy", "funnel"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type == "marketing_strategy":
                result = await self.create_strategy(kwargs.get("product", ""), kwargs.get("target_audience", ""), kwargs.get("budget_usd", 100))
            elif task_type == "funnel":
                result = await self.design_funnel(kwargs.get("product", kwargs.get("step", "")))
            elif task_type == "ad_copy":
                result = await self.create_ad_copy(kwargs.get("product", ""), kwargs.get("platform", "facebook"))
            else:
                result = await self.create_strategy(kwargs.get("step", task_type), "general", 100)
            result.duration_ms = int((time.monotonic() - start) * 1000)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def create_strategy(self, product: str, target_audience: str, budget_usd: float = 100) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        response = await self._call_llm(task_type=TaskType.STRATEGY, prompt=f"Создай маркетинговую стратегию для продукта: {product}\nЦА: {target_audience}\nБюджет: ${budget_usd}\nВключи: каналы, тактики, KPI, timeline.", estimated_tokens=3000)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.03, f"Marketing strategy: {product[:50]}")
        return TaskResult(success=True, output=response, cost_usd=0.03)

    async def design_funnel(self, product: str, stages: list[str] = None) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        stages_str = f"Этапы: {', '.join(stages)}" if stages else "Стандартная воронка: awareness → interest → desire → action"
        response = await self._call_llm(task_type=TaskType.STRATEGY, prompt=f"Спроектируй воронку продаж для: {product}\n{stages_str}\nОпиши каждый этап, контент, метрики.", estimated_tokens=2500)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        return TaskResult(success=True, output=response, cost_usd=0.02)

    async def create_ad_copy(self, product: str, platform: str, style: str = "direct") -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        response = await self._call_llm(task_type=TaskType.CONTENT, prompt=f"Напиши рекламный текст для {platform}. Продукт: {product}. Стиль: {style}. 3 варианта.", estimated_tokens=1500)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        return TaskResult(success=True, output=response, cost_usd=0.01)

    async def suggest_channels(self, product: str, budget_usd: float = 100) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        response = await self._call_llm(task_type=TaskType.STRATEGY, prompt=f"Предложи лучшие маркетинговые каналы для: {product}, бюджет ${budget_usd}.", estimated_tokens=1500)
        return TaskResult(success=True, output=response or "No response", cost_usd=0.01)
