"""PartnershipAgent — Agent 17: партнёрства, аффилиаты, коллаборации."""

import time
from typing import Any, Optional
from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType

logger = get_logger("partnership_agent", agent="partnership_agent")


class PartnershipAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(name="partnership_agent", description="Партнёрства: аффилиаты, рефералы, коллаборации", **kwargs)
        self._referrals: list[dict] = []

    @property
    def capabilities(self) -> list[str]:
        return ["partnership", "affiliate"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type == "partnership":
                result = await self.find_affiliates(kwargs.get("niche", kwargs.get("step", "")))
            elif task_type == "affiliate":
                result = await self.find_affiliates(kwargs.get("niche", kwargs.get("step", "")))
            elif task_type == "referrals":
                result = await self.track_referrals()
            elif task_type == "collaboration":
                result = await self.propose_collaboration(kwargs.get("partner", ""))
            else:
                result = await self.find_affiliates(kwargs.get("step", task_type))
            result.duration_ms = int((time.monotonic() - start) * 1000)
            self._track_result(result)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def find_affiliates(self, niche: str) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        response = await self.llm_router.call_llm(
            task_type=TaskType.RESEARCH,
            prompt=f"Найди партнёрские программы для ниши: {niche}\nДай топ-5 с: комиссией, условиями, ссылкой для регистрации.",
            estimated_tokens=2000,
        )
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.01, f"Find affiliates: {niche[:50]}")
        return TaskResult(success=True, output=response, cost_usd=0.01)

    async def track_referrals(self) -> TaskResult:
        return TaskResult(success=True, output={"referrals": self._referrals, "total": len(self._referrals)})

    async def propose_collaboration(self, partner: str) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        response = await self.llm_router.call_llm(
            task_type=TaskType.CONTENT,
            prompt=f"Напиши предложение о сотрудничестве для: {partner}\nТон: профессиональный, дружелюбный. Включи: взаимные выгоды, предложение, CTA.",
            estimated_tokens=1500,
        )
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        return TaskResult(success=True, output=response)
