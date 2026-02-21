"""LegalAgent — Agent 11: проверка TOS, авторских прав, GDPR."""

import time
from typing import Any, Optional
from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType

logger = get_logger("legal_agent", agent="legal_agent")


class LegalAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(name="legal_agent", description="Юридический: TOS, авторские права, GDPR", **kwargs)

    @property
    def capabilities(self) -> list[str]:
        return ["legal", "copyright", "gdpr"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            action = kwargs.get("action", task_type)
            if action == "check_tos":
                result = await self.check_tos(kwargs.get("platform", ""))
            elif action == "check_copyright":
                result = await self.check_copyright(kwargs.get("content", kwargs.get("step", "")))
            elif action == "gdpr_audit":
                result = await self.gdpr_audit()
            else:
                result = await self.check_tos(kwargs.get("platform", kwargs.get("step", "")))
            result.duration_ms = int((time.monotonic() - start) * 1000)
            self._track_result(result)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def check_tos(self, platform: str) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        response = await self.llm_router.call_llm(
            task_type=TaskType.RESEARCH,
            prompt=f"Проанализируй Terms of Service платформы {platform}.\nПроверь: можно ли продавать AI-контент, ограничения, риски бана, комиссии.\nДай краткий вердикт: compliant/risk/violation.",
            estimated_tokens=2000,
        )
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.01, f"TOS check: {platform}")
        return TaskResult(success=True, output=response, cost_usd=0.01)

    async def check_copyright(self, content: str) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        response = await self.llm_router.call_llm(
            task_type=TaskType.ROUTINE,
            prompt=f"Проверь контент на потенциальные нарушения авторских прав:\n{content[:2000]}\nОтветь: safe/risk/violation с пояснением.",
            estimated_tokens=1000,
        )
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        return TaskResult(success=True, output=response)

    async def gdpr_audit(self) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        response = await self.llm_router.call_llm(
            task_type=TaskType.RESEARCH,
            prompt="Проведи GDPR-аудит для AI-бизнеса, который:\n- Собирает email подписчиков\n- Хранит данные в PostgreSQL\n- Использует внешние API\nДай чеклист соответствия.",
            estimated_tokens=2000,
        )
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.02, "GDPR audit")
        return TaskResult(success=True, output=response, cost_usd=0.02)
