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
        response = None
        if self.llm_router:
            response = await self._call_llm(
                task_type=TaskType.RESEARCH,
                prompt=f"Проанализируй Terms of Service платформы {platform}.\nПроверь: можно ли продавать AI-контент, ограничения, риски бана, комиссии.\nДай краткий вердикт: compliant/risk/violation.",
                estimated_tokens=2000,
            )
        if response:
            self._record_expense(0.01, f"TOS check: {platform}")
            return TaskResult(success=True, output=response, cost_usd=0.01)
        return TaskResult(success=True, output=self._local_tos_check(platform), metadata={"mode": "local_fallback"})

    async def check_copyright(self, content: str) -> TaskResult:
        response = None
        if self.llm_router:
            response = await self._call_llm(
                task_type=TaskType.ROUTINE,
                prompt=f"Проверь контент на потенциальные нарушения авторских прав:\n{content[:2000]}\nОтветь: safe/risk/violation с пояснением.",
                estimated_tokens=1000,
            )
        if response:
            return TaskResult(success=True, output=response)
        return TaskResult(success=True, output=self._local_copyright_check(content), metadata={"mode": "local_fallback"})

    async def gdpr_audit(self) -> TaskResult:
        response = None
        if self.llm_router:
            response = await self._call_llm(
                task_type=TaskType.RESEARCH,
                prompt="Проведи GDPR-аудит для AI-бизнеса, который:\n- Собирает email подписчиков\n- Хранит данные в PostgreSQL\n- Использует внешние API\nДай чеклист соответствия.",
                estimated_tokens=2000,
            )
        if response:
            self._record_expense(0.02, "GDPR audit")
            return TaskResult(success=True, output=response, cost_usd=0.02)
        return TaskResult(success=True, output=self._local_gdpr_audit(), metadata={"mode": "local_fallback"})

    def _local_tos_check(self, platform: str) -> dict:
        p = (platform or "unknown").strip().lower()
        risk_flags = [
            "запрещенный контент",
            "некорректные claims по доходу/медицине/финансам",
            "автоматизированный спам",
            "нарушение брендов/товарных знаков",
        ]
        return {
            "platform": p,
            "verdict": "risk_review_required",
            "risk_score": 45,
            "checks": [
                "Проверить правила цифровых товаров платформы",
                "Проверить ограничения по авто-постингу и bot behavior",
                "Проверить payout/chargeback policy",
            ],
            "risk_flags": risk_flags,
            "decision": "Можно работать, но публиковать только после чек-листа compliance.",
        }

    def _local_copyright_check(self, content: str) -> dict:
        txt = (content or "").lower()
        bad = []
        if "disney" in txt or "marvel" in txt or "star wars" in txt:
            bad.append("бренд/франшиза")
        if "copy" in txt and "competitor" in txt:
            bad.append("признак копирования чужого контента")
        verdict = "safe" if not bad else "risk"
        return {
            "verdict": verdict,
            "risk_score": 20 if verdict == "safe" else 70,
            "issues": bad,
            "recommendation": "Использовать оригинальный текст/визуал и хранить source-подтверждения.",
        }

    def _local_gdpr_audit(self) -> dict:
        return {
            "overall": "partial",
            "risk_score": 52,
            "checklist": [
                {"item": "Privacy Policy актуальна", "status": "todo"},
                {"item": "Consent logging для email", "status": "todo"},
                {"item": "Data retention policy", "status": "todo"},
                {"item": "Право на удаление данных", "status": "todo"},
                {"item": "DPA с внешними процессорами", "status": "todo"},
            ],
            "next_actions": [
                "Вести журнал согласий",
                "Добавить DSAR workflow (экспорт/удаление)",
                "Проверить трансграничную передачу данных",
            ],
        }
