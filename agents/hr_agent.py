"""HRAgent — Agent 15: оценка производительности агентов, рейтинг, улучшения."""

import time
from typing import Any, Optional
from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType

logger = get_logger("hr_agent", agent="hr_agent")


class HRAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(name="hr_agent", description="HR: оценка агентов, рейтинг, оптимизация", **kwargs)
        self.registry = None

    @property
    def capabilities(self) -> list[str]:
        return ["hr", "performance_evaluation", "knowledge_audit", "agent_development"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type in ("hr", "evaluate"):
                result = await self.agent_ranking()
            elif task_type == "performance_evaluation":
                result = await self.evaluate_performance(kwargs.get("agent_name", ""))
            elif task_type == "improvements":
                result = await self.suggest_improvements()
            elif task_type == "knowledge_audit":
                result = await self.audit_knowledge_base()
            elif task_type == "agent_development":
                result = await self.plan_agent_development()
            else:
                result = await self.agent_ranking()
            result.duration_ms = int((time.monotonic() - start) * 1000)
            self._track_result(result)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def evaluate_performance(self, agent_name: str) -> TaskResult:
        if not self.registry:
            return TaskResult(success=True, output={"agent": agent_name, "status": "no registry"})
        statuses = self.registry.get_all_statuses()
        agent_data = next((s for s in statuses if s.get("name") == agent_name), None)
        if not agent_data:
            return TaskResult(success=True, output={"agent": agent_name, "status": "not_found"})
        completed = agent_data.get("tasks_completed", 0)
        failed = agent_data.get("tasks_failed", 0)
        total = completed + failed
        success_rate = (completed / total * 100) if total > 0 else 0
        return TaskResult(success=True, output={
            "agent": agent_name,
            "tasks_completed": completed,
            "tasks_failed": failed,
            "success_rate": round(success_rate, 1),
            "total_cost": agent_data.get("total_cost", 0),
        })

    async def agent_ranking(self) -> TaskResult:
        if not self.registry:
            return TaskResult(success=True, output=[])
        statuses = self.registry.get_all_statuses()
        ranking = []
        for s in statuses:
            completed = s.get("tasks_completed", 0)
            failed = s.get("tasks_failed", 0)
            total = completed + failed
            score = (completed / total * 100) if total > 0 else 0
            ranking.append({"name": s["name"], "score": round(score, 1), "completed": completed, "failed": failed})
        ranking.sort(key=lambda x: x["score"], reverse=True)
        return TaskResult(success=True, output=ranking)

    async def suggest_improvements(self) -> TaskResult:
        if not self.llm_router:
            return TaskResult(success=False, error="LLM Router недоступен")
        statuses = []
        if self.registry:
            statuses = self.registry.get_all_statuses()
        stats_text = "\n".join(f"- {s.get('name', '?')}: completed={s.get('tasks_completed', 0)}, failed={s.get('tasks_failed', 0)}, cost=${s.get('total_cost', 0):.2f}" for s in statuses) or "Нет данных"
        response = await self._call_llm(
            task_type=TaskType.STRATEGY,
            prompt=f"Проанализируй производительность агентов и дай рекомендации:\n{stats_text}\nПредложи: что улучшить, какие агенты неэффективны, как оптимизировать.",
            estimated_tokens=1500,
        )
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        return TaskResult(success=True, output=response)

    async def audit_knowledge_base(self) -> TaskResult:
        """Audit knowledge/skills coverage and suggest updates."""
        if not self.llm_router or not self.memory:
            return TaskResult(success=False, error="LLM Router или Memory недоступны")
        # Summarize current skills
        try:
            skills = self.memory.search_skills("platform integration", limit=10)
        except Exception:
            skills = []
        skills_text = "\n".join([f"- {s.get('name')}: {s.get('description','')[:80]}" for s in skills]) or "Нет навыков"
        platform_text = ""
        try:
            from modules.platform_registry import PlatformRegistry
            reg = PlatformRegistry()
            items = reg.list_platforms(limit=50)
            if items:
                lines = ["Платформы в реестре:"]
                for p in items:
                    lines.append(f"- {p['name']} ({'configured' if p['configured'] else 'not_configured'})")
                platform_text = "\n".join(lines)
        except Exception:
            platform_text = ""
        prompt = (
            "Проведи аудит базы знаний и навыков VITO. "
            "Укажи пробелы по платформам коммерции/контента и предложи что обновить.\n"
            f"Навыки:\n{skills_text}\n"
            f"{platform_text}\n"
            "Ответ: краткий список пробелов + рекомендации."
        )
        response = await self._call_llm(task_type=TaskType.STRATEGY, prompt=prompt, estimated_tokens=800)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        return TaskResult(success=True, output=response)

    async def plan_agent_development(self) -> TaskResult:
        """Plan periodic development goals for agents by domain."""
        if not self.llm_router or not self.registry:
            return TaskResult(success=False, error="LLM Router или Registry недоступны")
        statuses = self.registry.get_all_statuses()
        agents = ", ".join([s.get("name","?") for s in statuses]) or "None"
        prompt = (
            "Составь план развития агентов по доменам. "
            "Цель: чтобы каждый агент развивался в своём направлении под оркестратором VITO.\n"
            f"Агенты: {agents}\n"
            "Ответ: краткий список действий/навыков для каждого домена."
        )
        response = await self._call_llm(task_type=TaskType.STRATEGY, prompt=prompt, estimated_tokens=900)
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        return TaskResult(success=True, output=response)
