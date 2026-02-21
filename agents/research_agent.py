"""ResearchAgent — Agent 18: глубокие исследования через Perplexity + LLM."""

import time
from typing import Any, Optional

from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType

logger = get_logger("research_agent", agent="research_agent")


class ResearchAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(name="research_agent", description="Глубокие исследования: рынок, конкуренты, тренды", **kwargs)

    @property
    def capabilities(self) -> list[str]:
        return ["research", "competitor_analysis", "market_analysis"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type == "research":
                result = await self.deep_research(kwargs.get("topic", kwargs.get("step", "")))
            elif task_type == "competitor_analysis":
                result = await self.competitor_analysis(kwargs.get("niche", kwargs.get("step", "")))
            elif task_type == "market_analysis":
                result = await self.market_analysis(kwargs.get("product_type", kwargs.get("step", "")))
            else:
                result = await self.deep_research(kwargs.get("step", task_type))
            result.duration_ms = int((time.monotonic() - start) * 1000)
            self._track_result(result)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def deep_research(self, topic: str) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        response = await self.llm_router.call_llm(
            task_type=TaskType.RESEARCH,
            prompt=f"Проведи глубокое исследование темы: {topic}\nДай структурированный анализ с выводами и рекомендациями.",
            system_prompt="Ты — аналитик-исследователь. Давай детальные, структурированные ответы.",
            estimated_tokens=3000,
        )
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.02, f"Deep research: {topic[:50]}")
        if self.memory:
            self.memory.store_knowledge(
                doc_id=f"research_{hash(topic) % 10000}",
                text=f"Исследование: {topic}. {response[:2000]}",
                metadata={"type": "research", "topic": topic},
            )
            self.memory.save_skill(
                name=f"research_{topic[:40]}",
                description=f"Исследование: {topic}. Ключевые выводы: {response[:200]}",
                agent="research_agent",
                task_type="research",
                method={"approach": "deep_research", "topic": topic[:100]},
            )
        return TaskResult(success=True, output=response, cost_usd=0.02)

    async def competitor_analysis(self, niche: str) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        response = await self.llm_router.call_llm(
            task_type=TaskType.RESEARCH,
            prompt=f"Проведи анализ конкурентов в нише: {niche}\nОпиши топ-5 конкурентов, их сильные/слабые стороны, ценообразование, УТП.",
            estimated_tokens=3000,
        )
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.02, f"Competitor analysis: {niche[:50]}")
        if self.memory:
            self.memory.store_knowledge(
                doc_id=f"competitors_{hash(niche) % 10000}",
                text=f"Анализ конкурентов: {niche}. {response[:2000]}",
                metadata={"type": "competitor_analysis", "niche": niche},
            )
            self.memory.save_skill(
                name=f"competitors_{niche[:40]}",
                description=f"Анализ конкурентов в нише: {niche}. {response[:200]}",
                agent="research_agent",
                task_type="competitor_analysis",
                method={"approach": "competitor_analysis", "niche": niche[:100]},
            )
        return TaskResult(success=True, output=response, cost_usd=0.02)

    async def market_analysis(self, product_type: str) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        response = await self.llm_router.call_llm(
            task_type=TaskType.STRATEGY,
            prompt=f"Проведи анализ рынка для типа продукта: {product_type}\nОцени объём рынка, рост, барьеры входа, возможности.",
            estimated_tokens=2500,
        )
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.03, f"Market analysis: {product_type[:50]}")
        if self.memory:
            self.memory.store_knowledge(
                doc_id=f"market_{hash(product_type) % 10000}",
                text=f"Анализ рынка: {product_type}. {response[:2000]}",
                metadata={"type": "market_analysis", "product_type": product_type},
            )
            self.memory.save_skill(
                name=f"market_{product_type[:40]}",
                description=f"Анализ рынка: {product_type}. {response[:200]}",
                agent="research_agent",
                task_type="market_analysis",
                method={"approach": "market_analysis", "product_type": product_type[:100]},
            )
        return TaskResult(success=True, output=response, cost_usd=0.03)
