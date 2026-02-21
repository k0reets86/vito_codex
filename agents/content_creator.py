"""ContentCreator — Agent 02: создание контента (статьи, ebook, описания)."""

import time
from typing import Any, Optional

from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType

logger = get_logger("content_creator", agent="content_creator")


class ContentCreator(BaseAgent):
    def __init__(self, quality_judge=None, **kwargs):
        super().__init__(name="content_creator", description="Создание статей, ebook, описаний продуктов", **kwargs)
        self.quality_judge = quality_judge

    @property
    def capabilities(self) -> list[str]:
        return ["content_creation", "article", "ebook"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type in ("content_creation", "article"):
                result = await self.create_article(kwargs.get("topic", kwargs.get("step", "")), kwargs.get("keywords"))
            elif task_type == "ebook":
                result = await self.create_ebook(kwargs.get("topic", ""), kwargs.get("chapters", 5))
            elif task_type == "product_description":
                result = await self.create_product_description(kwargs.get("product", ""), kwargs.get("platform", "etsy"))
            else:
                result = await self.create_article(kwargs.get("step", task_type))
            result.duration_ms = int((time.monotonic() - start) * 1000)
            self._track_result(result)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def create_article(self, topic: str, keywords: list[str] = None) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        kw = f"\nКлючевые слова: {', '.join(keywords)}" if keywords else ""
        prompt = f"Напиши подробную статью на тему: {topic}{kw}\nСтруктура: заголовок, введение, 3-5 разделов, заключение. 1500-2000 слов."
        response = await self.llm_router.call_llm(task_type=TaskType.CONTENT, prompt=prompt, estimated_tokens=4000)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.02, f"Article: {topic[:50]}")
        return TaskResult(success=True, output=response, cost_usd=0.02)

    async def create_ebook(self, topic: str, chapters: int = 5) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        parts = []
        for i in range(1, chapters + 1):
            prompt = f"Напиши главу {i} из {chapters} для ebook на тему: {topic}. 800-1200 слов, с подзаголовками."
            response = await self.llm_router.call_llm(task_type=TaskType.CONTENT, prompt=prompt, estimated_tokens=3000)
            if response:
                parts.append(f"# Глава {i}\n\n{response}")
        if not parts:
            return TaskResult(success=False, error="Не удалось сгенерировать ebook")
        cost = 0.02 * len(parts)
        self._record_expense(cost, f"Ebook: {topic[:50]}")
        return TaskResult(success=True, output="\n\n---\n\n".join(parts), cost_usd=cost)

    async def create_product_description(self, product: str, platform: str) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        prompt = f"Напиши продающее описание для {platform}: {product}\nВключи: заголовок, описание, ключевые особенности, CTA."
        response = await self.llm_router.call_llm(task_type=TaskType.CONTENT, prompt=prompt, estimated_tokens=1500)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.01, f"Product description: {product[:50]}")
        return TaskResult(success=True, output=response, cost_usd=0.01)
