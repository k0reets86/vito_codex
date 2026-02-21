"""ContentCreator — Agent 02: создание контента (статьи, ebook, описания).

Saves all output to /home/vito/vito-agent/output/ directory.
"""

import re
import time
from pathlib import Path
from typing import Any, Optional

from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType

logger = get_logger("content_creator", agent="content_creator")

OUTPUT_BASE = Path("/home/vito/vito-agent/output")
ARTICLES_DIR = OUTPUT_BASE / "articles"
EBOOKS_DIR = OUTPUT_BASE / "ebooks"
PRODUCTS_DIR = OUTPUT_BASE / "products"

for d in (ARTICLES_DIR, EBOOKS_DIR, PRODUCTS_DIR):
    d.mkdir(parents=True, exist_ok=True)


def _slugify(text: str, max_len: int = 50) -> str:
    """Convert text to safe filename slug."""
    slug = re.sub(r"[^\w\s-]", "", text.lower().strip())
    slug = re.sub(r"[\s_]+", "_", slug)
    return slug[:max_len]


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

        # Save to file
        slug = _slugify(topic)
        ts = int(time.time())
        file_path = ARTICLES_DIR / f"{slug}_{ts}.md"
        file_path.write_text(response, encoding="utf-8")
        logger.info(f"Article saved: {file_path}", extra={"event": "article_saved", "context": {"path": str(file_path)}})

        self._record_expense(0.02, f"Article: {topic[:50]}")
        return TaskResult(
            success=True,
            output=response,
            cost_usd=0.02,
            metadata={"file_path": str(file_path), "topic": topic},
        )

    async def create_ebook(self, topic: str, chapters: int = 5) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        parts = []
        for i in range(1, chapters + 1):
            if not self.llm_router.check_daily_limit():
                logger.warning(f"Ebook остановлен на главе {i}/{chapters}: бюджет исчерпан", extra={"event": "ebook_budget_stop"})
                break
            prompt = f"Напиши главу {i} из {chapters} для ebook на тему: {topic}. 800-1200 слов, с подзаголовками."
            response = await self.llm_router.call_llm(task_type=TaskType.CONTENT, prompt=prompt, estimated_tokens=3000)
            if response:
                parts.append(f"# Глава {i}\n\n{response}")
            else:
                logger.warning(f"Ebook: глава {i}/{chapters} не сгенерирована, останавливаюсь", extra={"event": "ebook_chapter_fail"})
                break
        if not parts:
            return TaskResult(success=False, error="Не удалось сгенерировать ebook")

        full_text = "\n\n---\n\n".join(parts)

        # Save to file
        slug = _slugify(topic)
        ts = int(time.time())
        file_path = EBOOKS_DIR / f"{slug}_{ts}.md"
        file_path.write_text(full_text, encoding="utf-8")
        logger.info(f"Ebook saved: {file_path}", extra={"event": "ebook_saved", "context": {"path": str(file_path), "chapters": len(parts)}})

        cost = 0.02 * len(parts)
        self._record_expense(cost, f"Ebook: {topic[:50]}")
        return TaskResult(
            success=True,
            output=full_text,
            cost_usd=cost,
            metadata={"file_path": str(file_path), "chapters": len(parts), "topic": topic},
        )

    async def create_product_description(self, product: str, platform: str) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        prompt = f"Напиши продающее описание для {platform}: {product}\nВключи: заголовок, описание, ключевые особенности, CTA."
        response = await self.llm_router.call_llm(task_type=TaskType.CONTENT, prompt=prompt, estimated_tokens=1500)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")

        # Save to file
        slug = _slugify(product)
        ts = int(time.time())
        file_path = PRODUCTS_DIR / f"{platform}_{slug}_{ts}.md"
        file_path.write_text(response, encoding="utf-8")
        logger.info(f"Product description saved: {file_path}", extra={"event": "product_desc_saved"})

        self._record_expense(0.01, f"Product description: {product[:50]}")
        return TaskResult(
            success=True,
            output=response,
            cost_usd=0.01,
            metadata={"file_path": str(file_path), "product": product, "platform": platform},
        )
