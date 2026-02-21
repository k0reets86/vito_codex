"""DocumentAgent — Agent 19: документация, отчёты, база знаний."""

import time
from typing import Any, Optional
from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType

logger = get_logger("document_agent", agent="document_agent")


class DocumentAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(name="document_agent", description="Документация: создание, отчёты, база знаний", **kwargs)

    @property
    def capabilities(self) -> list[str]:
        return ["documentation", "knowledge_base"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type == "documentation":
                result = await self.create_doc(kwargs.get("title", kwargs.get("step", "")), kwargs.get("content_type", "technical"), kwargs.get("context", {}))
            elif task_type == "knowledge_base":
                result = await self.update_knowledge_base(kwargs.get("topic", ""), kwargs.get("content", kwargs.get("step", "")))
            elif task_type == "report":
                result = await self.generate_report(kwargs.get("report_type", "general"), kwargs.get("data", {}))
            else:
                result = await self.create_doc(kwargs.get("step", task_type), "general", {})
            result.duration_ms = int((time.monotonic() - start) * 1000)
            self._track_result(result)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def create_doc(self, title: str, content_type: str = "technical", context: dict = None) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        context_text = ""
        if context:
            context_text = "\nКонтекст:\n" + "\n".join(f"- {k}: {v}" for k, v in context.items())
        response = await self.llm_router.call_llm(
            task_type=TaskType.CONTENT,
            prompt=f"Создай документ.\nНазвание: {title}\nТип: {content_type}{context_text}\nФормат: Markdown с заголовками, списками, примерами кода если нужно.",
            estimated_tokens=3000,
        )
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.02, f"Doc: {title[:50]}")
        return TaskResult(success=True, output=response, cost_usd=0.02)

    async def generate_report(self, report_type: str = "general", data: dict = None) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        data_text = ""
        if data:
            data_text = "\nДанные:\n" + "\n".join(f"- {k}: {v}" for k, v in data.items())
        response = await self.llm_router.call_llm(
            task_type=TaskType.CONTENT,
            prompt=f"Сгенерируй отчёт типа: {report_type}{data_text}\nВключи: резюме, ключевые метрики, выводы, рекомендации.",
            estimated_tokens=2500,
        )
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.02, f"Report: {report_type}")
        return TaskResult(success=True, output=response, cost_usd=0.02)

    async def update_knowledge_base(self, topic: str, content: str) -> TaskResult:
        if not self.memory:
            return TaskResult(success=False, error="Memory Manager недоступен")
        self.memory.store_knowledge(
            doc_id=f"kb_{hash(topic) % 100000}",
            text=f"{topic}: {content}",
            metadata={"type": "knowledge_base", "topic": topic},
        )
        logger.info(f"База знаний обновлена: {topic}", extra={"event": "kb_updated"})
        return TaskResult(success=True, output={"topic": topic, "status": "stored"})
