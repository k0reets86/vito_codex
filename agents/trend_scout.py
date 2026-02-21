"""TrendScout — Agent 01: сканирование трендов и предложение ниш."""

import json
import time
import uuid
from typing import Any, Optional

from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType

logger = get_logger("trend_scout", agent="trend_scout")


class TrendScout(BaseAgent):
    def __init__(self, browser_agent=None, **kwargs):
        super().__init__(name="trend_scout", description="Сканирование трендов, исследование ниш", **kwargs)
        self.browser_agent = browser_agent

    @property
    def capabilities(self) -> list[str]:
        return ["trend_scan", "niche_research"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type == "trend_scan":
                result = await self.scan_google_trends(kwargs.get("keywords", ["digital products", "AI tools"]))
            elif task_type == "niche_research":
                result = await self.suggest_niches()
            else:
                result = await self.scan_google_trends(kwargs.get("keywords", ["digital products"]))
            result.duration_ms = int((time.monotonic() - start) * 1000)
            self._track_result(result)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def scan_google_trends(self, keywords: list[str], geo: str = "US") -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        prompt = f"Проанализируй текущие тренды Google Trends для ключевых слов: {', '.join(keywords)} (регион: {geo}). Дай топ-10 растущих запросов и ниш."
        response = await self.llm_router.call_llm(task_type=TaskType.RESEARCH, prompt=prompt, estimated_tokens=2000)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.02, f"Google Trends scan: {', '.join(keywords[:3])}")
        if self.memory:
            self.memory.store_knowledge(doc_id=f"trends_{uuid.uuid4().hex[:8]}", text=f"Google Trends {geo}: {response[:500]}", metadata={"type": "trend", "geo": geo})
        return TaskResult(success=True, output=response, cost_usd=0.02)

    async def scan_reddit(self, subreddits: list[str]) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        prompt = f"Проанализируй горячие темы в Reddit-сообществах: {', '.join(subreddits)}. Какие темы обсуждаются чаще всего? Какие возможности для цифровых продуктов?"
        response = await self.llm_router.call_llm(task_type=TaskType.RESEARCH, prompt=prompt, estimated_tokens=2000)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.02, f"Reddit scan: {', '.join(subreddits[:3])}")
        if self.memory:
            self.memory.store_knowledge(doc_id=f"reddit_{uuid.uuid4().hex[:8]}", text=f"Reddit trends: {response[:500]}", metadata={"type": "trend", "source": "reddit"})
        return TaskResult(success=True, output=response, cost_usd=0.02)

    async def suggest_niches(self) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        prompt = "Предложи 5-7 перспективных ниш для цифровых продуктов (ebooks, templates, курсы, SaaS). Для каждой укажи: название, уровень конкуренции, потенциал монетизации, рекомендуемые продукты."
        response = await self.llm_router.call_llm(task_type=TaskType.STRATEGY, prompt=prompt, estimated_tokens=2500)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.03, "Suggest niches")
        return TaskResult(success=True, output=response, cost_usd=0.03)
