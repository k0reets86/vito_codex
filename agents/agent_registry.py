"""AgentRegistry — реестр и диспетчер агентов VITO.

Управляет жизненным циклом агентов:
  - Регистрация/удаление
  - Tier-based lazy loading (Tier 1 = always, Tier 2 = on-demand, Tier 3 = heavy)
  - Auto-stop idle agents after IDLE_TIMEOUT
  - Поиск по capabilities
  - Диспетчеризация задач к подходящему агенту
"""

import json
import time
from enum import Enum
from typing import Optional

from agents.base_agent import BaseAgent, TaskResult
from config.logger import get_logger
from modules.skill_matrix_v2 import build_agent_skill_matrix_v2, validate_agent_skill_matrix_v2
from modules.step_contract import validate_step_output

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

    def get_skill_matrix_v2(self) -> list[dict]:
        """Return Skill Matrix v2 rows for all registered agents."""
        rows: list[dict] = []
        for agent in self._agents.values():
            row = build_agent_skill_matrix_v2(
                agent_name=agent.name,
                capabilities=list(agent.capabilities),
                description=getattr(agent, "description", ""),
            )
            ok, errors = validate_agent_skill_matrix_v2(row)
            row["valid"] = bool(ok)
            if errors:
                row["errors"] = errors
            rows.append(row)
        rows.sort(key=lambda x: str(x.get("agent", "")))
        return rows

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
        orchestration_depth = int(kwargs.pop("__orchestration_depth", 0) or 0)
        orchestrated_by = str(kwargs.pop("__orchestrated_by", "") or "").strip() or None
        exclude_agents_raw = kwargs.pop("__exclude_agents", [])
        exclude_agents = set(exclude_agents_raw or [])
        agents = self.find_by_capability(task_type)
        if exclude_agents:
            agents = [a for a in agents if a.name not in exclude_agents]
        if not agents:
            if task_type.startswith("tooling:"):
                try:
                    from modules.tooling_runner import ToolingRunner
                    adapter_key = task_type.split(":", 1)[1].strip()
                    result = ToolingRunner().run(
                        adapter_key=adapter_key,
                        input_data=kwargs,
                        dry_run=bool(kwargs.get("dry_run", True)),
                    )
                    chk = validate_step_output(result, metadata={"task_type": task_type})
                    return TaskResult(
                        success=(result.get("status") in {"dry_run", "prepared", "ok"} and chk.ok),
                        output=result,
                        error=result.get("error", "") if chk.ok else f"contract_invalid:{','.join(chk.errors)}",
                        metadata={
                            "agent": "tooling_runner",
                            "task_type": task_type,
                            "contract_ok": chk.ok,
                            "contract_errors": chk.errors,
                        },
                    )
                except Exception:
                    pass
            # Try capability packs as fallback
            try:
                from modules.capability_pack_runner import CapabilityPackRunner
                runner = CapabilityPackRunner()
                result = runner.run(task_type, kwargs)
                chk = validate_step_output(result.get("output") or result, metadata={"task_type": task_type})
                return TaskResult(
                    success=(result.get("status") == "ok" and chk.ok),
                    output=result.get("output") or result,
                    error=result.get("error", "") if chk.ok else f"contract_invalid:{','.join(chk.errors)}",
                    metadata={
                        "agent": "capability_pack",
                        "task_type": task_type,
                        "contract_ok": chk.ok,
                        "contract_errors": chk.errors,
                    },
                )
            except Exception:
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
                task_kwargs = dict(kwargs)
                orchestration_plan = {}
                try:
                    orchestration_plan = agent.build_task_orchestration(task_type, **task_kwargs) or {}
                except Exception:
                    orchestration_plan = {}

                delegations = orchestration_plan.get("delegations", []) if isinstance(orchestration_plan, dict) else []
                delegation_results: list[dict] = []
                if delegations and orchestration_depth < 2:
                    for item in delegations:
                        cap = ""
                        d_kwargs: dict = {}
                        if isinstance(item, str):
                            cap = item.strip()
                        elif isinstance(item, dict):
                            cap = str(item.get("capability") or "").strip()
                            if isinstance(item.get("kwargs"), dict):
                                d_kwargs = dict(item.get("kwargs") or {})
                        if not cap:
                            continue
                        delegated = await self.dispatch(
                            cap,
                            __orchestration_depth=orchestration_depth + 1,
                            __orchestrated_by=agent.name,
                            __exclude_agents=list(exclude_agents | {agent.name}),
                            **d_kwargs,
                        )
                        delegation_results.append(
                            {
                                "capability": cap,
                                "success": bool(delegated and delegated.success),
                                "output": getattr(delegated, "output", None),
                                "error": getattr(delegated, "error", None),
                            }
                        )
                    try:
                        task_kwargs = agent.consume_delegation_results(task_type, task_kwargs, delegation_results)
                    except Exception:
                        task_kwargs["__delegations"] = delegation_results

                # Trace orchestration context for every agent execution
                task_kwargs["__owner_orchestrator"] = orchestrated_by
                task_kwargs["__orchestration_depth"] = orchestration_depth
                task_kwargs["__responsible_agent"] = agent.name
                if isinstance(orchestration_plan, dict) and orchestration_plan:
                    task_kwargs["__orchestration_plan"] = orchestration_plan

                result = await agent.execute_task(task_type, **task_kwargs)
                contract_ok = True
                contract_errors: list[str] = []
                if result and result.success:
                    chk = validate_step_output(
                        result.output,
                        metadata=result.metadata if isinstance(result.metadata, dict) else {},
                    )
                    contract_ok = chk.ok
                    contract_errors = chk.errors
                    if not contract_ok:
                        result.success = False
                        result.error = f"contract_invalid:{','.join(contract_errors)}"
                try:
                    if result is not None:
                        md = result.metadata or {}
                        md.setdefault("task_type", task_type)
                        md.setdefault("contract_ok", contract_ok)
                        md.setdefault("responsible_agent", agent.name)
                        if orchestrated_by:
                            md.setdefault("orchestrated_by", orchestrated_by)
                        if delegation_results:
                            md.setdefault("delegations", delegation_results)
                        if isinstance(orchestration_plan, dict) and orchestration_plan.get("resources"):
                            md.setdefault("resources", list(orchestration_plan.get("resources") or []))
                        if contract_errors:
                            md["contract_errors"] = contract_errors
                        result.metadata = md
                except Exception:
                    pass
                # Owner-level verification step (optional)
                verify_cap = ""
                if isinstance(orchestration_plan, dict):
                    verify_cap = str(orchestration_plan.get("verify_with") or "").strip()
                if not verify_cap and task_type in {"listing_create", "publish", "ecommerce", "product_turnkey"}:
                    verify_cap = "quality_review"
                if (
                    result
                    and result.success
                    and verify_cap
                    and orchestration_depth == 0
                    and verify_cap != task_type
                ):
                    verify_content = result.output
                    if not isinstance(verify_content, str):
                        try:
                            verify_content = json.dumps(verify_content, ensure_ascii=False)
                        except Exception:
                            verify_content = str(verify_content)
                    verify_input = {
                        "content": verify_content,
                        "content_type": task_type,
                        "responsible_agent": agent.name,
                    }
                    vr = await self.dispatch(
                        verify_cap,
                        __orchestration_depth=orchestration_depth + 1,
                        __orchestrated_by=agent.name,
                        __exclude_agents=list(exclude_agents | {agent.name}),
                        **verify_input,
                    )
                    if not vr or not vr.success:
                        result.success = False
                        result.error = f"verification_failed:{verify_cap}"
                    else:
                        approved = True
                        if isinstance(vr.output, dict) and "approved" in vr.output:
                            approved = bool(vr.output.get("approved"))
                        if not approved:
                            result.success = False
                            result.error = f"verification_rejected:{verify_cap}"
                        md = result.metadata or {}
                        md["verification"] = {
                            "capability": verify_cap,
                            "success": bool(vr and vr.success),
                            "approved": approved,
                            "output": vr.output,
                        }
                        result.metadata = md
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
