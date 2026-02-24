"""AgentRegistry — реестр и диспетчер агентов VITO.

Управляет жизненным циклом агентов:
  - Регистрация/удаление
  - Tier-based lazy loading (Tier 1 = always, Tier 2 = on-demand, Tier 3 = heavy)
  - Auto-stop idle agents after IDLE_TIMEOUT
  - Поиск по capabilities
  - Диспетчеризация задач к подходящему агенту
"""

import time
from enum import Enum
from typing import Optional

from agents.base_agent import BaseAgent, TaskResult
from config.logger import get_logger

logger = get_logger("agent_registry", agent="registry")

IDLE_TIMEOUT_SEC = 30 * 60  # 30 минут — auto-stop idle агентов


class AgentTier(Enum):
    CORE = 1      # Всегда запущен: vito_core, devops_agent (~20MB)
    ON_DEMAND = 2  # Запуск при первом dispatch: research, content, trend_scout...
    HEAVY = 3      # Тяжёлые (Playwright): browser_agent — только когда реально нужен


# Mapping agent name → tier (default = ON_DEMAND)
TIER_MAP: dict[str, AgentTier] = {
    "vito_core": AgentTier.CORE,
    "devops_agent": AgentTier.CORE,
    "browser_agent": AgentTier.HEAVY,
}


class AgentRegistry:
    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}
        self._last_used: dict[str, float] = {}  # agent_name → timestamp
        self._started: set[str] = set()  # agents that have been start()'d
        logger.info("AgentRegistry инициализирован", extra={"event": "init"})

    def register(self, agent: BaseAgent) -> None:
        """Регистрирует агента в реестре (не запускает)."""
        self._agents[agent.name] = agent
        logger.info(
            f"Агент зарегистрирован: {agent.name} ({', '.join(agent.capabilities)})",
            extra={"event": "agent_registered", "context": {"agent_name": agent.name}},
        )

    def unregister(self, name: str) -> Optional[BaseAgent]:
        """Удаляет агента из реестра."""
        agent = self._agents.pop(name, None)
        self._started.discard(name)
        self._last_used.pop(name, None)
        if agent:
            logger.info(f"Агент удалён: {name}", extra={"event": "agent_unregistered"})
        return agent

    def get(self, name: str) -> Optional[BaseAgent]:
        """Возвращает агента по имени."""
        return self._agents.get(name)

    def _get_tier(self, agent_name: str) -> AgentTier:
        return TIER_MAP.get(agent_name, AgentTier.ON_DEMAND)

    def find_by_capability(self, capability: str) -> list[BaseAgent]:
        """Находит агентов с указанной capability."""
        return [a for a in self._agents.values() if capability in a.capabilities]

    @staticmethod
    def _agent_score(agent: BaseAgent) -> float:
        try:
            completed = int(getattr(agent, "_tasks_completed", 0))
        except Exception:
            completed = 0
        try:
            failed = int(getattr(agent, "_tasks_failed", 0))
        except Exception:
            failed = 0
        total = completed + failed
        success_rate = (completed / total) if total > 0 else 0.5
        return success_rate

    async def _ensure_started(self, agent: BaseAgent) -> None:
        """Lazy start: запускает агента если он ещё не запущен."""
        if agent.name not in self._started:
            try:
                await agent.start()
                self._started.add(agent.name)
                logger.info(
                    f"Lazy start: {agent.name}",
                    extra={"event": "agent_lazy_start", "context": {"agent_name": agent.name}},
                )
            except Exception as e:
                logger.error(
                    f"Ошибка lazy start {agent.name}: {e}",
                    extra={"event": "agent_start_error"},
                )
                raise

    async def dispatch(self, task_type: str, **kwargs) -> Optional[TaskResult]:
        """Диспетчеризует задачу к подходящему агенту (с lazy start)."""
        agents = self.find_by_capability(task_type)
        if not agents:
            logger.debug(
                f"Нет агента для capability: {task_type}",
                extra={"event": "dispatch_no_agent", "context": {"task_type": task_type}},
            )
            return None

        # Try agents by success rate (best first), fallback to others on failure
        candidates = sorted(agents, key=self._agent_score, reverse=True)
        last_error = None
        for agent in candidates:
            # Lazy start on first dispatch
            await self._ensure_started(agent)
            self._last_used[agent.name] = time.monotonic()

            logger.info(
                f"Dispatch: {task_type} → {agent.name}",
                extra={"event": "dispatch", "context": {"task_type": task_type, "agent_name": agent.name}},
            )
            try:
                result = await agent.execute_task(task_type, **kwargs)
                try:
                    if result is not None:
                        md = result.metadata or {}
                        md.setdefault("task_type", task_type)
                        result.metadata = md
                except Exception:
                    pass
                agent._track_result(result)
                # Record execution facts for verified actions
                try:
                    if result and result.success:
                        from modules.execution_facts import ExecutionFacts
                        facts = ExecutionFacts()
                        evidence = ""
                        if isinstance(result.output, dict):
                            for key in ("url", "link", "listing_url", "tweet_url", "post_url"):
                                if result.output.get(key):
                                    evidence = str(result.output.get(key))
                                    break
                            if not evidence and "path" in result.output:
                                evidence = str(result.output.get("path"))
                            if not evidence and "file" in result.output:
                                evidence = str(result.output.get("file"))
                            if not evidence and "id" in result.output:
                                evidence = str(result.output.get("id"))
                            if not evidence and "listing_id" in result.output:
                                evidence = str(result.output.get("listing_id"))
                        evidence_dict = None
                        if isinstance(result.output, dict):
                            evidence_dict = {
                                "url": result.output.get("url") or result.output.get("link"),
                                "id": result.output.get("id") or result.output.get("listing_id") or result.output.get("post_id"),
                                "path": result.output.get("path") or result.output.get("file"),
                                "screenshot": result.output.get("screenshot_path"),
                                "platform": result.output.get("platform"),
                            }
                        facts.record(
                            action=f"{agent.name}:{task_type}",
                            status="success",
                            detail=str(kwargs.get("step", "") or kwargs.get("goal_title", "") or task_type)[:200],
                            evidence=evidence,
                            source="agent_registry",
                            evidence_dict=evidence_dict,
                        )
                except Exception:
                    pass
                # Structured feedback registry (local, lightweight)
                try:
                    from modules.agent_feedback import AgentFeedback
                    feedback = AgentFeedback()
                    feedback.record(
                        agent=agent.name,
                        task_type=task_type,
                        success=bool(result and result.success),
                        output=result.output,
                        error=getattr(result, "error", None),
                        metadata=getattr(result, "metadata", None),
                    )
                except Exception:
                    pass
                # Data lake event log
                try:
                    from modules.data_lake import DataLake
                    lake = DataLake()
                    lake.record(
                        agent=agent.name,
                        task_type=task_type,
                        status="success" if result and result.success else "failed",
                        output=getattr(result, "output", None),
                        error=getattr(result, "error", None) or "",
                    )
                except Exception:
                    pass
                # Save skill on success (agent-aware, reusable)
                try:
                    if result and result.success and agent.memory:
                        step = kwargs.get("step", "") or kwargs.get("content", "") or ""
                        goal_title = kwargs.get("goal_title", "")
                        desc_parts = []
                        if goal_title:
                            desc_parts.append(f"Goal: {goal_title[:80]}")
                        if step:
                            desc_parts.append(f"Step: {step[:120]}")
                        description = " | ".join(desc_parts) or f"Task: {task_type}"
                        skill_name = f"{agent.name}:{task_type}"
                        agent.memory.save_skill(
                            name=skill_name,
                            description=description,
                            agent=agent.name,
                            task_type=task_type,
                            method={"kwargs_keys": list(kwargs.keys())[:10]},
                        )
                        try:
                            agent.memory.update_skill_last_result(skill_name, str(result.output))
                        except Exception:
                            pass
                except Exception:
                    pass
                # Record failures for anti-skill memory
                try:
                    if result and not result.success:
                        from modules.failure_memory import FailureMemory
                        fm = FailureMemory()
                        fm.record(
                            agent=agent.name,
                            task_type=task_type,
                            detail=str(kwargs.get("step", "") or kwargs.get("goal_title", "") or task_type)[:200],
                            error=getattr(result, "error", "") or "unknown_error",
                        )
                except Exception:
                    pass
                if result and result.success:
                    return result
                last_error = getattr(result, "error", None)
            except Exception as e:
                last_error = str(e)
                logger.error(
                    f"Ошибка dispatch {task_type} → {agent.name}: {e}",
                    extra={"event": "dispatch_error"},
                    exc_info=True,
                )

        return TaskResult(success=False, error=last_error or "All agents failed")

    async def start_core(self) -> None:
        """Запускает только Tier 1 (CORE) агентов при старте системы."""
        for name, agent in self._agents.items():
            if self._get_tier(name) == AgentTier.CORE:
                try:
                    await agent.start()
                    self._started.add(name)
                    self._last_used[name] = time.monotonic()
                except Exception as e:
                    logger.error(
                        f"Ошибка запуска core {agent.name}: {e}",
                        extra={"event": "agent_start_error"},
                    )
        started_names = [n for n in self._started]
        logger.info(
            f"Core агенты запущены: {started_names}",
            extra={"event": "core_agents_started", "context": {"agents": started_names}},
        )

    async def start_all(self) -> None:
        """Запускает только core агентов (backward-compatible alias)."""
        await self.start_core()

    async def stop_idle_agents(self) -> int:
        """Останавливает агентов, не использовавшихся > IDLE_TIMEOUT_SEC.

        Returns: количество остановленных агентов.
        """
        now = time.monotonic()
        stopped = 0

        for name in list(self._started):
            # Never stop core agents
            if self._get_tier(name) == AgentTier.CORE:
                continue

            last_used = self._last_used.get(name, 0)
            if now - last_used > IDLE_TIMEOUT_SEC:
                agent = self._agents.get(name)
                if agent:
                    try:
                        await agent.stop()
                        self._started.discard(name)
                        stopped += 1
                        logger.info(
                            f"Auto-stop idle: {name} (idle {int(now - last_used)}s)",
                            extra={"event": "agent_auto_stopped", "context": {"agent_name": name}},
                        )
                    except Exception as e:
                        logger.warning(
                            f"Ошибка auto-stop {name}: {e}",
                            extra={"event": "agent_stop_error"},
                        )

        return stopped

    async def stop_all(self) -> None:
        """Останавливает все запущенные агенты."""
        for name in list(self._started):
            agent = self._agents.get(name)
            if agent:
                try:
                    await agent.stop()
                except Exception as e:
                    logger.error(
                        f"Ошибка остановки {agent.name}: {e}",
                        extra={"event": "agent_stop_error"},
                    )
        self._started.clear()

    def get_all_statuses(self) -> list[dict]:
        """Возвращает статусы всех агентов."""
        statuses = []
        for a in self._agents.values():
            status = a.get_status()
            status["tier"] = self._get_tier(a.name).name
            status["started"] = a.name in self._started
            statuses.append(status)
        return statuses

    @property
    def agents(self) -> dict[str, BaseAgent]:
        return dict(self._agents)
