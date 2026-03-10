from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from agents.base_agent import BaseAgent, TaskResult
from goal_engine import GoalPriority
from llm_router import TaskType
from modules.owner_model import OwnerModel
from modules.reflector import VITOReflector
from modules.skill_library import VITOSkillLibrary

CURRICULUM_PROMPT = """
Ты стратег-ИИ системы VITO для автономной генерации дохода.

ТЕКУЩЕЕ СОСТОЯНИЕ:
{state_summary}

НЕДАВНИЕ РЕФЛЕКСИИ:
{recent_learnings}

АКТИВНЫЕ ЦЕЛИ:
{active_goals}

ПРЕДПОЧТЕНИЯ ВЛАДЕЛЬЦА:
{owner_preferences}

Предложи 3 наиболее ценные следующие цели.
Для каждой:
- title
- rationale
- expected_revenue
- effort
- type
- confidence
Только JSON list.
""".strip()


class CurriculumAgent(BaseAgent):
    NEEDS = {
        "generate_goals": ["goal_engine", "owner_model", "reflector", "skill_library"],
        "prioritize_goals": ["goal_engine", "owner_model"],
        "assess_state": ["goal_engine", "reflector"],
        "*": ["goal_engine"],
    }

    def __init__(self, goal_engine=None, **kwargs):
        super().__init__(name="curriculum_agent", description="Автономный генератор следующих целей", **kwargs)
        self.goal_engine = goal_engine
        self.skill_lib = VITOSkillLibrary()
        self.reflector = VITOReflector()
        self.owner_model = OwnerModel()

    @property
    def capabilities(self) -> list[str]:
        return ["generate_goals", "prioritize_goals", "assess_state"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        try:
            if task_type == "prioritize_goals":
                output = await self.prioritize_goals(kwargs.get("goals") or [])
            elif task_type == "assess_state":
                output = await self.assess_state()
            else:
                output = await self.generate_goals()
            return TaskResult(success=True, output=output)
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def generate_goals(self) -> dict[str, Any]:
        state = await self._gather_state()
        learnings = self.reflector.get_recent(n=10, category="strategy")
        active = self._get_active_goals()
        prefs = self.owner_model.get_preferences()
        goals = []
        if self.llm_router:
            prompt = CURRICULUM_PROMPT.format(
                state_summary=json.dumps(state, ensure_ascii=False),
                recent_learnings="\n".join(learnings),
                active_goals=json.dumps(active, ensure_ascii=False),
                owner_preferences=json.dumps(prefs, ensure_ascii=False),
            )
            raw = await self._call_llm(task_type=TaskType.RESEARCH, prompt=prompt, estimated_tokens=800)
            goals = _extract_json_list(raw)
        if not goals:
            goals = self._fallback_goals(state)
        approved = self.owner_model.filter_goals(goals)
        return {"generated_at": datetime.now(timezone.utc).isoformat(), "goals": approved[:3], "state": state}

    async def prioritize_goals(self, goals: list[dict[str, Any]]) -> dict[str, Any]:
        ranked = sorted(
            goals or [],
            key=lambda g: (
                -float(g.get("confidence") or 0),
                -float(g.get("expected_revenue") or 0),
                str(g.get("effort") or "z"),
            ),
        )
        return {"ranked": ranked}

    async def assess_state(self) -> dict[str, Any]:
        return await self._gather_state()

    async def _gather_state(self) -> dict[str, Any]:
        active = self._get_active_goals()
        return {
            "active_goals": len(active),
            "active_titles": [g.get("title") for g in active[:5]],
            "recent_reflections": len(self.reflector.get_recent(n=20)),
            "skill_count": self.skill_lib.count(),
        }

    def _get_active_goals(self) -> list[dict[str, Any]]:
        if not self.goal_engine:
            return []
        goals = self.goal_engine.get_all_goals()
        out = []
        for g in goals:
            if getattr(g, "status", None) and getattr(g.status, "value", "") not in {"completed", "failed", "cancelled"}:
                out.append({"goal_id": g.goal_id, "title": g.title, "priority": getattr(g.priority, "name", "")})
        return out

    def _fallback_goals(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "title": "Scan fresh digital product opportunities",
                "rationale": "Idle system should proactively look for monetizable niches.",
                "expected_revenue": 150,
                "effort": "low",
                "type": "explore",
                "confidence": 0.72,
            },
            {
                "title": "Refine weakest platform runbook",
                "rationale": "Execution discipline on fragile platforms has highest leverage.",
                "expected_revenue": 120,
                "effort": "medium",
                "type": "optimize",
                "confidence": 0.68,
            },
            {
                "title": "Create one new validated product package",
                "rationale": "Revenue requires fresh inventory, not just orchestration quality.",
                "expected_revenue": 220,
                "effort": "high",
                "type": "create",
                "confidence": 0.61,
            },
        ]


def _extract_json_list(raw: str) -> list[dict[str, Any]]:
    import re

    try:
        m = re.search(r"\[.*\]", raw or "", re.DOTALL)
        return json.loads(m.group()) if m else []
    except Exception:
        return []
