from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agents.base_agent import BaseAgent, TaskResult
from modules.reflector import VITOReflector
from modules.skill_library import VITOSkillLibrary


class SelfEvolver(BaseAgent):
    NEEDS = {
        "weekly_improve_cycle": ["technical_reflections", "skill_library", "devops_agent", "self_healer"],
        "propose_improvements": ["technical_reflections", "skill_library"],
        "*": ["technical_reflections"],
    }

    def __init__(self, **kwargs):
        super().__init__(name="self_evolver", description="Автономное улучшение VITO через безопасные предложения", **kwargs)
        self.reflector = VITOReflector()
        self.skill_lib = VITOSkillLibrary()

    @property
    def capabilities(self) -> list[str]:
        return ["weekly_improve_cycle", "propose_improvements"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        try:
            if task_type == "propose_improvements":
                output = await self.propose_improvements()
            else:
                output = await self.weekly_improve_cycle()
            return TaskResult(success=True, output=output)
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def weekly_improve_cycle(self) -> dict[str, Any]:
        issues = self.reflector.get_recent(n=15, category="technical")
        proposals = await self.propose_improvements(issues=issues)
        await self._notify_report(proposals)
        return {"generated_at": datetime.now(timezone.utc).isoformat(), "proposals": proposals}

    async def propose_improvements(self, issues: list[str] | None = None) -> list[dict[str, Any]]:
        issues = issues or self.reflector.get_recent(n=15, category="technical")
        skills = self.skill_lib.list_all(limit=10)
        proposals = [
            {
                "title": "Strengthen flaky browser runbooks",
                "why": "Repeated technical reflections mention browser/platform fragility.",
                "risk": "low",
                "type": "runtime_hardening",
            },
            {
                "title": "Promote top recurring successful patterns into stronger skill packs",
                "why": f"Skill library contains {len(skills)} reusable skills; some should be promoted to runtime defaults.",
                "risk": "low",
                "type": "skill_promotion",
            },
        ]
        if issues:
            proposals.append(
                {
                    "title": "Target highest-frequency technical failure with a verified patch",
                    "why": issues[0][:300],
                    "risk": "medium",
                    "type": "verified_patch",
                }
            )
        return proposals[:3]

    async def _notify_report(self, proposals: list[dict[str, Any]]) -> None:
        if not self.comms:
            return
        lines = ["🔧 *VITO SelfEvolver — Еженедельный отчёт*", ""]
        for i, item in enumerate(proposals, start=1):
            lines.append(f"{i}. {item.get('title')}")
            lines.append(f"   why: {item.get('why')}")
        await self.comms.send_message("\n".join(lines))
