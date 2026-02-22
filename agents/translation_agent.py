"""TranslationAgent — Agent 08: перевод и локализация. Языки: EN/DE/UA/PL."""

import time
from typing import Any, Optional
from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType

logger = get_logger("translation_agent", agent="translation_agent")
SUPPORTED_LANGS = ["en", "de", "ua", "pl"]


class TranslationAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(name="translation_agent", description="Перевод и локализация: EN, DE, UA, PL", **kwargs)

    @property
    def capabilities(self) -> list[str]:
        return ["translate", "localize"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type == "translate":
                result = await self.translate(kwargs.get("text", kwargs.get("step", "")), kwargs.get("source_lang", "en"), kwargs.get("target_lang", "de"))
            elif task_type == "localize":
                result = await self.localize_listing(kwargs.get("listing_data", {}), kwargs.get("target_lang", "de"))
            elif task_type == "detect_language":
                result = await self.detect_language(kwargs.get("text", ""))
            else:
                result = await self.translate(kwargs.get("step", task_type), "en", "de")
            result.duration_ms = int((time.monotonic() - start) * 1000)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def translate(self, text: str, source_lang: str, target_lang: str) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        response = await self._call_llm(task_type=TaskType.CONTENT, prompt=f"Переведи с {source_lang} на {target_lang}. Сохрани стиль и тон.\n\nТекст:\n{text}", estimated_tokens=2000)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.01, f"Translate {source_lang}->{target_lang}")
        return TaskResult(success=True, output=response, cost_usd=0.01)

    async def localize_listing(self, listing_data: dict, target_lang: str) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        text = "\n".join(f"{k}: {v}" for k, v in listing_data.items())
        response = await self._call_llm(task_type=TaskType.CONTENT, prompt=f"Локализуй листинг на {target_lang}. Адаптируй для местного рынка.\n\n{text}", estimated_tokens=2000)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        return TaskResult(success=True, output=response, cost_usd=0.01)

    async def detect_language(self, text: str) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        response = await self._call_llm(task_type=TaskType.ROUTINE, prompt=f"Определи язык текста. Ответь одним кодом (en/de/ua/pl/ru/другой):\n{text[:500]}", estimated_tokens=100)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        return TaskResult(success=True, output=response.strip().lower()[:5])
