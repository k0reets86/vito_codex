"""QualityJudge — оценка качества контента перед публикацией.

Порог: score >= 7 — одобрено, < 7 — доработка.
"""

import json
import time
from typing import Any, Optional

from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType

logger = get_logger("quality_judge", agent="quality_judge")

APPROVAL_THRESHOLD = 7


class QualityJudge(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(name="quality_judge", description="Оценка качества контента (порог >= 7)", **kwargs)

    @property
    def capabilities(self) -> list[str]:
        return ["quality_review", "content_check"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        try:
            content = kwargs.get("content", kwargs.get("step", ""))
            content_type = kwargs.get("content_type", "article")
            result = await self.review(content, content_type)
            self._track_result(result)
            return result
        finally:
            self._status = AgentStatus.IDLE

    async def review(self, content: str, content_type: str = "article") -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        start = time.monotonic()
        prompt = (
            f"Оцени качество следующего контента (тип: {content_type}).\n\n"
            f"Контент:\n---\n{content[:5000]}\n---\n\n"
            f"Верни JSON: {{\"score\": 1-10, \"feedback\": \"описание\", \"issues\": [\"проблема1\"]}}\n"
            f"Только JSON."
        )
        response = await self.llm_router.call_llm(
            task_type=TaskType.CONTENT, prompt=prompt,
            system_prompt="Ты — строгий редактор. Оценивай объективно. JSON only.",
            estimated_tokens=1000,
        )
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.005, f"Quality review: {content_type}")
        duration_ms = int((time.monotonic() - start) * 1000)
        # Parse
        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            data = json.loads(cleaned.strip())
        except (json.JSONDecodeError, ValueError):
            data = {"score": 5, "feedback": response, "issues": []}
        score = data.get("score", 5)
        approved = score >= APPROVAL_THRESHOLD
        result_output = {"score": score, "feedback": data.get("feedback", ""), "approved": approved, "issues": data.get("issues", [])}
        logger.info(f"Quality review: score={score}, approved={approved}", extra={"event": "quality_review", "context": result_output})
        return TaskResult(success=True, output=result_output, cost_usd=0.005, duration_ms=duration_ms)
