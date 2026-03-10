"""PartnershipAgent — Agent 17: партнёрства, аффилиаты, коллаборации."""

import time
from typing import Any

from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType
from modules.governance_runtime import build_partnership_execution_profile
from modules.growth_runtime import build_partnership_runtime_profile

logger = get_logger("partnership_agent", agent="partnership_agent")


class PartnershipAgent(BaseAgent):
    NEEDS = {
        "partnership": ["research", "marketing_strategy"],
        "affiliate": ["research"],
        "collaboration": ["email"],
        "default": [],
    }

    def __init__(self, **kwargs):
        super().__init__(name="partnership_agent", description="Партнёрства: аффилиаты, рефералы, коллаборации", **kwargs)
        self._referrals: list[dict] = []

    @property
    def capabilities(self) -> list[str]:
        return ["partnership", "affiliate", "referrals", "collaboration"]

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
        local = self._local_affiliates(niche)
        if not self.llm_router:
            return TaskResult(success=True, output=local, metadata={"mode": "local_fallback", "partnership_runtime_profile": build_partnership_runtime_profile(niche, local.get("candidates")), **self.get_skill_pack()})
        response = await self._call_llm(
            task_type=TaskType.RESEARCH,
            prompt=f"Найди партнёрские программы для ниши: {niche}\nДай топ-5 с: комиссией, условиями, ссылкой для регистрации.",
            estimated_tokens=2000,
        )
        if response:
            self._record_expense(0.01, f"Find affiliates: {niche[:50]}")
            local["llm_notes"] = response
        runtime_profile = build_partnership_runtime_profile(niche, local.get("candidates"))
        local["runtime_candidates"] = runtime_profile["top_candidates"]
        local["outreach_plan"] = [f"personalize_outreach::{row.get('name')}" for row in local["runtime_candidates"]]
        return TaskResult(
            success=True,
            output=local,
            cost_usd=0.01 if response else 0.0,
            metadata={
                "partnership_runtime_profile": runtime_profile,
                "partnership_execution_profile": build_partnership_execution_profile(
                    niche=niche,
                    candidate_count=runtime_profile.get("candidate_count", 0),
                    shortlist_count=len(local.get("runtime_candidates") or []),
                ),
                **self.get_skill_pack(),
            },
        )

    async def track_referrals(self) -> TaskResult:
        return TaskResult(
            success=True,
            output={"referrals": self._referrals, "total": len(self._referrals)},
            metadata={
                "partnership_runtime_profile": build_partnership_runtime_profile("referrals", []),
                "partnership_execution_profile": build_partnership_execution_profile(niche="referrals", candidate_count=len(self._referrals), shortlist_count=0),
                **self.get_skill_pack(),
            },
        )

    async def propose_collaboration(self, partner: str) -> TaskResult:
        local = self._local_collaboration(partner)
        if not self.llm_router:
            return TaskResult(
                success=True,
                output=local,
                metadata={
                    "mode": "local_fallback",
                    "partnership_runtime_profile": build_partnership_runtime_profile(partner, []),
                    "partnership_execution_profile": build_partnership_execution_profile(niche=partner, candidate_count=1, shortlist_count=1),
                    **self.get_skill_pack(),
                },
            )
        response = await self._call_llm(
            task_type=TaskType.CONTENT,
            prompt=f"Напиши предложение о сотрудничестве для: {partner}\nТон: профессиональный, дружелюбный. Включи: взаимные выгоды, предложение, CTA.",
            estimated_tokens=1500,
        )
        if response:
            local["llm_notes"] = response
        return TaskResult(
            success=True,
            output=local,
            metadata={
                "partnership_runtime_profile": build_partnership_runtime_profile(partner, []),
                "partnership_execution_profile": build_partnership_execution_profile(niche=partner, candidate_count=1, shortlist_count=1),
                **self.get_skill_pack(),
            },
        )

    def _local_affiliates(self, niche: str) -> dict[str, Any]:
        niche = (niche or "creator tools").strip()
        candidates = [
            {"name": f"{niche} Partner One", "commission": "20%", "fit": "creator audience"},
            {"name": f"{niche} Partner Two", "commission": "30%", "fit": "education audience"},
            {"name": f"{niche} Partner Three", "commission": "15%", "fit": "newsletter audience"},
        ]
        return {"niche": niche, "candidates": candidates}

    def _local_collaboration(self, partner: str) -> dict[str, Any]:
        partner = (partner or "Potential partner").strip()
        return {
            "partner": partner,
            "proposal": f"We can co-create a focused asset with {partner} and distribute it to both audiences.",
            "cta": "Reply if you want a short pilot proposal.",
        }
