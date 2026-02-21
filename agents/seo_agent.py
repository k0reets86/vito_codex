"""SEOAgent — Agent 06: SEO-оптимизация и keyword research."""

import json
import time
from typing import Any, Optional
from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType

logger = get_logger("seo_agent", agent="seo_agent")


class SEOAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(name="seo_agent", description="SEO-оптимизация, keyword research, мета-теги", **kwargs)

    @property
    def capabilities(self) -> list[str]:
        return ["seo", "keyword_research"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type == "keyword_research":
                result = await self.keyword_research(kwargs.get("topic", kwargs.get("step", "")))
            elif task_type == "seo":
                result = await self.optimize_content(kwargs.get("content", ""), kwargs.get("keywords", []))
            elif task_type == "generate_meta":
                result = await self.generate_meta(kwargs.get("content", ""), kwargs.get("keywords", []))
            else:
                result = await self.keyword_research(kwargs.get("step", task_type))
            result.duration_ms = int((time.monotonic() - start) * 1000)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def keyword_research(self, topic: str, language: str = "en") -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        response = await self.llm_router.call_llm(task_type=TaskType.RESEARCH, prompt=f"Keyword research для: {topic} (язык: {language}). Дай 10 primary keywords, 10 long-tail, 5 LSI.", estimated_tokens=2000)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.01, f"Keyword research: {topic[:50]}")
        return TaskResult(success=True, output=response, cost_usd=0.01)

    async def optimize_content(self, content: str, keywords: list[str]) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        response = await self.llm_router.call_llm(task_type=TaskType.CONTENT, prompt=f"Оптимизируй контент для SEO. Keywords: {', '.join(keywords)}\n\nКонтент:\n{content[:5000]}", estimated_tokens=3000)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.01, "SEO optimize content")
        return TaskResult(success=True, output=response, cost_usd=0.01)

    async def analyze_rankings(self, url: str) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        response = await self.llm_router.call_llm(task_type=TaskType.RESEARCH, prompt=f"Проанализируй SEO для URL: {url}. Оцени on-page факторы, дай рекомендации.", estimated_tokens=2000)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        return TaskResult(success=True, output=response, cost_usd=0.01)

    async def generate_meta(self, content: str, keywords: list[str]) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        response = await self.llm_router.call_llm(task_type=TaskType.CONTENT, prompt=f"Сгенерируй SEO мета-теги (title <=60, description <=160) для:\n{content[:3000]}\nKeywords: {', '.join(keywords)}", estimated_tokens=1000)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        return TaskResult(success=True, output=response, cost_usd=0.005)
