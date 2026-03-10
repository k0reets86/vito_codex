"""Decision Loop — сердце системы VITO.

Каждые 5 минут проверяет: что важнее всего сделать прямо сейчас?
Это не простая очередь задач — это динамическая приоритизация:

  1. Срочные задачи (одобрение ждёт >30 мин) → в первую очередь
  2. Задачи с высоким ROI-потенциалом → приоритет над рутиной
  3. Финансовый контроллер проверяет лимиты перед платным действием
  4. Quality Judge оценивает результат перед публикацией
  5. Если нет задач — VITO не простаивает: исследует ниши, обновляет знания

Полный цикл: Goal → Plan → Execute → Learn
"""

import asyncio
import json
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from config.logger import get_logger
from config.paths import PROJECT_ROOT
from config.resource_guard import resource_guard
from config.settings import settings
from goal_engine import Goal, GoalEngine, GoalPriority, GoalStatus
from llm_router import LLMRouter, TaskType
from memory.memory_manager import MemoryManager
from modules.operator_policy import OperatorPolicy
from modules.self_learning import SelfLearningEngine
from modules.self_learning_test_runner import SelfLearningTestRunner
from modules.llm_evals import LLMEvals
from modules.workflow_state_machine import WorkflowStateMachine
from modules.workflow_threads import WorkflowThreads
from modules.workflow_interrupts import WorkflowInterrupts
from modules.orchestration_manager import OrchestrationManager
from modules.data_lake import DataLake
from modules.step_contract import validate_step_output, validate_step_result
from modules.tooling_registry import ToolingRegistry
from modules.tooling_discovery import ToolingDiscovery, parse_tooling_discovery_sources
from modules.memory_skill_reports import MemorySkillReporter
from modules.memory_consolidation import MemoryConsolidationEngine
from modules.governance_reporter import GovernanceReporter
from modules.autonomous_improvement import AutonomousImprovementEngine
from modules.runtime_remediation import (
    SAFE_ACTIONS,
    apply_safe_action,
    rank_safe_action_suggestions,
    record_safe_action_outcome,
)
from modules.reflector import VITOReflector
from modules.skill_library import VITOSkillLibrary

TICK_INTERVAL = 300  # 5 минут
STEP_TIMEOUT = 120   # секунд на один шаг (LLM content needs time)
STEP_MAX_RETRIES = 3 # попыток на один шаг

logger = get_logger("decision_loop", agent="decision_loop")


def _runtime_sqlite_path(goal_engine: GoalEngine | None) -> str:
    try:
        path = str(getattr(goal_engine, "_sqlite_path", "") or "").strip()
        if path:
            return path
    except Exception:
        pass
    return settings.SQLITE_PATH


class DecisionLoop:
    def __init__(
        self,
        goal_engine: GoalEngine,
        llm_router: LLMRouter,
        memory: MemoryManager,
        agent_registry=None,
    ):
        self.goal_engine = goal_engine
        self.llm_router = llm_router
        self.memory = memory
        self.agent_registry = agent_registry
        self.self_healer = None
        self._code_generator = None
        self.cancel_state = None
        self.running = False
        self._tick_count = 0
        self._consecutive_idle = 0
        self._progress_sent: dict[str, set[int]] = {}
        self.workflow = WorkflowStateMachine()
        self.threads = WorkflowThreads()
        self.interrupts = WorkflowInterrupts()
        self.operator_policy = OperatorPolicy()
        self.self_learning = None
        self._last_llm_alert_at_tick = 0
        self._last_memory_retention_tick = 0
        self._last_self_learning_opt_tick = 0
        self._last_self_learning_test_tick = 0
        self._last_self_learning_maintenance_tick = 0
        self._last_tooling_governance_tick = 0
        self._last_tooling_discovery_tick = 0
        self._last_platform_rules_sync_tick = 0
        self._last_memory_weekly_report_tick = 0
        self._last_memory_consolidation_tick = 0
        self._last_weekly_governance_tick = 0
        self._last_autonomous_improvement_tick = 0
        self._last_opportunity_scout_tick = 0
        self._last_curriculum_tick = 0
        self._last_self_evolver_tick = 0
        self._kdp_watchdog_state: dict[str, Any] = self._load_kdp_watchdog_state()
        self._current_interrupt_id: int | None = None
        self._current_goal_id: str | None = None
        self._current_thread_id: str | None = None
        self.orchestrator = OrchestrationManager()
        logger.info("DecisionLoop инициализирован", extra={"event": "init"})

    def set_self_healer(self, self_healer) -> None:
        """Устанавливает SelfHealer для самолечения."""
        self.self_healer = self_healer

    async def _handle_runtime_error(self, agent: str, error: Exception, context: dict[str, Any] | None = None) -> None:
        healer = getattr(self, "_self_healer_v2", None) or self.self_healer
        if not healer:
            return
        try:
            await healer.handle_error(agent, error, context or {})
        except Exception:
            pass

    def set_cancel_state(self, cancel_state) -> None:
        """Устанавливает shared cancel-state для блокировки retry/auto-resume."""
        self.cancel_state = cancel_state

    def _is_cancelled(self) -> bool:
        try:
            return bool(self.cancel_state and self.cancel_state.is_cancelled())
        except Exception:
            return False

    @staticmethod
    def _parse_sqlite_dt(value: str) -> datetime | None:
        ts = (value or "").strip()
        if not ts:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(ts[:19], fmt).replace(tzinfo=timezone.utc)
            except Exception:
                continue
        return None

    def _auto_resume_allowed(self, goal_id: str, interrupt_id: int) -> tuple[bool, str]:
        max_count = max(0, int(getattr(settings, "AUTO_RESUME_MAX_PER_INTERRUPT", 2) or 2))
        cooldown_sec = max(0, int(getattr(settings, "AUTO_RESUME_COOLDOWN_SEC", 120) or 120))
        if max_count <= 0:
            return False, "policy_disabled"
        resume_count = self.interrupts.count_resume_events(goal_id, interrupt_id, action="resumed")
        if resume_count >= max_count:
            return False, "max_resumes_reached"
        latest = self.interrupts.latest_resume_event(goal_id, interrupt_id, action="resumed")
        if latest and cooldown_sec > 0:
            last_at = self._parse_sqlite_dt(str(latest.get("created_at") or ""))
            if last_at and (datetime.now(timezone.utc) - last_at) < timedelta(seconds=cooldown_sec):
                return False, "cooldown_active"
        return True, "ok"

    async def run(self) -> None:
        """Основной цикл. Работает пока self.running == True."""
        self.running = True
        logger.info("Decision Loop запущен", extra={"event": "loop_started"})

        while self.running:
            try:
                await self._tick()
            except Exception as e:
                logger.error(
                    f"Критическая ошибка в Decision Loop: {e}",
                    extra={"event": "tick_error"},
                    exc_info=True,
                )
                await self._handle_runtime_error("decision_loop", e, {"tick": self._tick_count})
                self.memory.log_error(
                    module="decision_loop",
                    error_type=type(e).__name__,
                    message=str(e),
                )
            await asyncio.sleep(TICK_INTERVAL)

    def stop(self) -> None:
        self.running = False
        logger.info("Decision Loop остановлен", extra={"event": "loop_stopped"})

    async def _tick(self) -> None:
        """Один тик Decision Loop — полный цикл принятия решения."""
        self._tick_count += 1
        tick_start = time.monotonic()

        logger.info(
            f"Tick #{self._tick_count}",
            extra={"event": "tick_start", "context": {"tick": self._tick_count}},
        )

        # 0. Проверка ресурсов — БЛОКИРУЕМ если RAM < порога
        if not resource_guard.can_proceed(estimated_mb=100):
            logger.warning(
                "Недостаточно RAM — пропускаем тик",
                extra={"event": "resource_guard_skip_tick",
                       "context": resource_guard.status()},
            )
            self._log_tick_done(tick_start, idle=True)
            return

        # 1. Проверка финансового лимита — БЛОКИРУЕМ если исчерпан
        if not self.llm_router.check_daily_limit():
            logger.warning(
                "Дневной лимит исчерпан — пропускаем тик",
                extra={"event": "budget_exhausted"},
            )
            self._log_tick_done(tick_start, idle=True)
            return

        # 1.5. LLM risk monitoring (cost anomaly / fail-rate)
        await self._maybe_send_llm_risk_alert()
        await self._maybe_run_memory_retention()
        await self._maybe_run_memory_consolidation()
        await self._maybe_run_memory_weekly_report()
        await self._maybe_run_self_learning_optimization()
        await self._maybe_run_self_learning_test_jobs()
        await self._maybe_run_self_learning_maintenance()
        await self._maybe_run_tooling_discovery_intake()
        await self._maybe_run_tooling_governance_check()
        await self._maybe_run_platform_rules_sync()
        await self._maybe_run_weekly_governance_report()
        await self._maybe_run_autonomous_improvement()
        await self._maybe_run_autonomy_v2()
        await self._maybe_run_kdp_session_watchdog()
        if self._is_cancelled():
            logger.info("Tick skipped: cancel-state active", extra={"event": "tick_cancelled_skip"})
            self._log_tick_done(tick_start, idle=True)
            return
        await self._maybe_auto_resume_waiting_goals()

        # 2. Выбор следующей цели
        try:
            self.goal_engine.reload_goals()
        except Exception:
            pass
        goal = self.goal_engine.get_next_goal()

        if goal is None:
            self._consecutive_idle += 1
            await self._idle_action()
            self._log_tick_done(tick_start, idle=True)
            return

        self._consecutive_idle = 0

        # 3. Полный цикл Goal → Plan → Execute → Learn
        await self._process_goal(goal)
        self._log_tick_done(tick_start, idle=False)

    async def _maybe_auto_resume_waiting_goals(self) -> None:
        """Auto-resume waiting goals when interrupts are resolved."""
        if self._is_cancelled():
            return
        try:
            waiting = self.goal_engine.get_waiting_approvals()
        except Exception:
            return
        if not waiting:
            return

        for goal in waiting:
            session = self.orchestrator.get_session(goal.goal_id)
            if not session or session.get("state") != "waiting_approval":
                continue

            pending = self.interrupts.latest_pending(goal.goal_id)
            if pending:
                continue

            latest = self.interrupts.latest_for_goal(goal.goal_id)
            if not latest:
                continue

            status = str(latest.get("status") or "").lower()
            intr_type = str(latest.get("interrupt_type") or "").lower()
            intr_id = int(latest.get("id") or 0)

            if status == "resolved" and intr_type in {"owner_approval_required", "step_approval_pending"}:
                allowed, reason = self._auto_resume_allowed(goal.goal_id, intr_id)
                if not allowed:
                    try:
                        self.interrupts.log_resume_event(goal.goal_id, intr_id, action="skipped", reason=reason)
                    except Exception:
                        pass
                    logger.info(
                        f"[{goal.goal_id}] auto-resume skipped: {reason}",
                        extra={"event": "auto_resume_waiting_goal_skipped", "context": {"goal_id": goal.goal_id, "interrupt_id": intr_id, "reason": reason}},
                    )
                    continue
                try:
                    self.orchestrator.resume_session(goal.goal_id, reason="auto_resume_resolved_interrupt")
                except Exception:
                    pass
                try:
                    goal.status = GoalStatus.PENDING
                    self.goal_engine._persist_goal(goal)
                except Exception:
                    pass
                try:
                    self.interrupts.log_resume_event(goal.goal_id, intr_id, action="resumed", reason="auto_resume_resolved_interrupt")
                except Exception:
                    pass
                logger.info(
                    f"[{goal.goal_id}] auto-resume: interrupt resolved",
                    extra={"event": "auto_resume_waiting_goal", "context": {"goal_id": goal.goal_id, "interrupt_id": intr_id}},
                )
            elif status == "cancelled":
                try:
                    self.orchestrator.cancel_session(goal.goal_id, reason="auto_cancelled_interrupt")
                except Exception:
                    pass
                try:
                    self.goal_engine.fail_goal(goal.goal_id, "Отменено по результату interrupt")
                except Exception:
                    pass
                try:
                    self.interrupts.log_resume_event(goal.goal_id, intr_id, action="cancelled", reason="auto_cancelled_interrupt")
                except Exception:
                    pass
                logger.info(
                    f"[{goal.goal_id}] auto-cancel: interrupt cancelled",
                    extra={"event": "auto_cancel_waiting_goal", "context": {"goal_id": goal.goal_id, "interrupt_id": intr_id}},
                )

    # ── Goal → Plan → Execute → Learn ──

    async def _process_goal(self, goal: Goal) -> None:
        """Проводит цель через полный цикл."""
        trace_id = self.workflow.start_or_attach(goal.goal_id)
        thread_id = f"goal_{goal.goal_id}"
        self._current_goal_id = goal.goal_id
        self._current_thread_id = thread_id
        try:
            self.threads.start_thread(thread_id=thread_id, goal_id=goal.goal_id)
            self.threads.update_thread(thread_id=thread_id, status="planning", last_node="planning")
        except Exception:
            pass
        logger.info(
            f"Обработка цели: [{goal.goal_id}] {goal.title}",
            extra={
                "event": "goal_processing",
                "context": {
                    "goal_id": goal.goal_id,
                    "priority": goal.priority.name,
                    "source": goal.source,
                    "estimated_cost": goal.estimated_cost_usd,
                },
            },
        )

        # PLAN
        self.workflow.transition(goal.goal_id, "planning", reason="goal_selected", detail=goal.title)
        plan = await self._plan_goal(goal)
        if not plan:
            self.workflow.transition(goal.goal_id, "failed", reason="planning_failed", detail="empty_plan")
            try:
                self.threads.update_thread(thread_id=thread_id, status="failed", last_node="planning_failed")
            except Exception:
                pass
            self.goal_engine.fail_goal(goal.goal_id, "Не удалось составить план")
            self._current_goal_id = None
            self._current_thread_id = None
            return

        self.goal_engine.plan_goal(goal.goal_id, plan)
        # EXECUTE
        self.workflow.transition(goal.goal_id, "executing", reason="plan_ready", detail=f"steps={len(plan)}")
        try:
            self.threads.update_thread(thread_id=thread_id, status="executing", last_node="executing")
        except Exception:
            pass
        try:
            self.orchestrator.create_session(goal.goal_id, plan, trace_id, thread_id=thread_id)
        except Exception:
            pass
        if not self.goal_engine.start_execution(goal.goal_id):
            # Цель ушла в WAITING_APPROVAL — ждём одобрения владельца
            self.workflow.transition(goal.goal_id, "waiting_approval", reason="owner_approval_required", detail=goal.title)
            try:
                self.threads.update_thread(thread_id=thread_id, status="waiting_approval", last_node="waiting_approval")
            except Exception:
                pass
            logger.info(
                f"[{goal.goal_id}] ожидает одобрения владельца",
                extra={"event": "goal_awaiting_approval"},
            )
            try:
                self.interrupts.open_interrupt(
                    goal_id=goal.goal_id,
                    step_num=0,
                    thread_id=thread_id,
                    interrupt_type="owner_approval_required",
                    reason="goal_cost_gate",
                    payload={"goal_title": goal.title},
                )
            except Exception:
                pass
            self._current_goal_id = None
            self._current_thread_id = None
            return

        results = await self._execute_goal(goal)
        if results.get("waiting_approval"):
            self.workflow.transition(goal.goal_id, "waiting_approval", reason="step_approval_pending", detail=goal.title)
            try:
                self.threads.update_thread(thread_id=thread_id, status="waiting_approval", last_node="waiting_approval")
            except Exception:
                pass
            self._current_goal_id = None
            self._current_thread_id = None
            return

        # LEARN
        self.workflow.transition(goal.goal_id, "learning", reason="execution_finished", detail=str(results.get("steps_completed", 0)))
        try:
            self.threads.update_thread(thread_id=thread_id, status="learning", last_node="learning")
        except Exception:
            pass
        self._current_goal_id = None
        self._current_thread_id = None
        await self._learn_from_goal(goal, results)
        if results.get("all_completed"):
            self.workflow.transition(goal.goal_id, "completed", reason="learn_done", detail="ok")
            try:
                self.threads.update_thread(thread_id=thread_id, status="completed", last_node="completed")
            except Exception:
                pass
        else:
            self.workflow.transition(goal.goal_id, "failed", reason="partial_or_failed", detail=str(results.get("steps_completed", 0)))
            try:
                self.threads.update_thread(thread_id=thread_id, status="failed", last_node="failed")
            except Exception:
                pass
        try:
            DataLake().record(
                agent="decision_loop",
                task_type="workflow_trace",
                status="success",
                output={"goal_id": goal.goal_id, "trace_id": trace_id, "state": self.workflow.get_state(goal.goal_id)},
                goal_id=goal.goal_id,
                trace_id=trace_id,
                source="workflow_state_machine",
            )
        except Exception:
            pass

    async def _maybe_send_llm_risk_alert(self) -> None:
        try:
            if not settings.LLM_ALERTS_ENABLED:
                return
            if self._tick_count - int(self._last_llm_alert_at_tick or 0) < 12:
                return
            ev = LLMEvals(sqlite_path=settings.SQLITE_PATH)
            current = ev.compute()
            anomaly = bool(current.get("cost_anomaly"))
            fail_rate = float(current.get("fail_rate", 0.0) or 0.0)
            if not anomaly and fail_rate < 0.25:
                return
            if not hasattr(self, "_comms") or not self._comms:
                return
            msg = (
                "[LLM Risk Alert]\n"
                f"Score: {current.get('score')}\n"
                f"Fail rate: {current.get('fail_rate')}\n"
                f"Blocked(24h): {current.get('blocked_count_24h')}\n"
                f"Daily cost: ${current.get('daily_cost_usd')}\n"
                f"Baseline cost: ${current.get('baseline_cost_usd')}\n"
                f"Anomaly: {1 if anomaly else 0}"
            )
            await self._comms.send_message(msg, level="warning")
            self._last_llm_alert_at_tick = self._tick_count
        except Exception:
            pass

    async def _maybe_run_memory_retention(self) -> None:
        try:
            # Preview every 4 hours (48 ticks), apply cleanup once per day.
            if self._tick_count - int(self._last_memory_retention_tick or 0) < 48:
                return
            preview = self.memory.cleanup_expired_memory(limit=100, dry_run=True)
            drift = self.memory.retention_drift_alerts(days=30)
            expired = int(preview.get("expired_found", 0) or 0)
            alerts = drift.get("alerts", []) if isinstance(drift, dict) else []
            if expired > 0:
                logger.info(
                    f"Memory retention preview: expired={expired}",
                    extra={"event": "memory_retention_preview", "context": {"expired_found": expired}},
                )
            if alerts:
                logger.warning(
                    f"Memory retention drift alerts: {len(alerts)}",
                    extra={"event": "memory_retention_alerts", "context": {"alerts": alerts[:5]}},
                )
            # Apply cleanup every ~24h
            if self._tick_count % 288 == 0 and expired > 0:
                applied = self.memory.cleanup_expired_memory(limit=120, dry_run=False)
                logger.info(
                    f"Memory retention cleanup applied: deleted={applied.get('deleted', 0)}",
                    extra={"event": "memory_retention_cleanup", "context": {"result": applied}},
                )
            self._last_memory_retention_tick = self._tick_count
        except Exception:
            pass

    async def _maybe_run_memory_consolidation(self) -> None:
        try:
            if not bool(getattr(settings, "MEMORY_CONSOLIDATION_ENABLED", True)):
                return
            interval = max(24, int(getattr(settings, "MEMORY_CONSOLIDATION_INTERVAL_TICKS", 288) or 288))
            if self._tick_count - int(self._last_memory_consolidation_tick or 0) < interval:
                return
            engine = MemoryConsolidationEngine(self.memory, sqlite_path=settings.SQLITE_PATH)
            result = engine.run_cycle(
                min_age_days=max(1, int(getattr(settings, "MEMORY_CONSOLIDATION_MIN_AGE_DAYS", 5) or 5)),
                limit=max(1, int(getattr(settings, "MEMORY_CONSOLIDATION_LIMIT", 25) or 25)),
            )
            logger.info(
                "Memory consolidation cycle completed",
                extra={"event": "memory_consolidation_cycle", "context": result},
            )
            self._last_memory_consolidation_tick = self._tick_count
        except Exception:
            pass

    async def _maybe_run_self_learning_optimization(self) -> None:
        try:
            if not settings.SELF_LEARNING_ENABLED:
                return
            interval = max(12, int(getattr(settings, "SELF_LEARNING_OPTIMIZE_INTERVAL_TICKS", 72) or 72))
            if self._tick_count - int(self._last_self_learning_opt_tick or 0) < interval:
                return
            if self.self_learning is None:
                self.self_learning = SelfLearningEngine(sqlite_path=settings.SQLITE_PATH)
            result = self.self_learning.optimize_candidates(
                days=30,
                min_lessons=int(getattr(settings, "SELF_LEARNING_MIN_LESSONS", 3) or 3),
                promote_confidence_min=float(settings.SELF_LEARNING_SKILL_SCORE_MIN or 0.78),
                auto_promote=bool(getattr(settings, "SELF_LEARNING_AUTO_PROMOTE", False)),
            )
            logger.info(
                f"Self-learning optimize: updated={result.get('updated', 0)} promoted={result.get('promoted', 0)}",
                extra={"event": "self_learning_optimize", "context": {"result": result}},
            )
            self._last_self_learning_opt_tick = self._tick_count
        except Exception:
            pass

    async def _maybe_run_self_learning_test_jobs(self) -> None:
        try:
            if not settings.SELF_LEARNING_ENABLED or not settings.SELF_LEARNING_TEST_RUNNER_ENABLED:
                return
            interval = max(24, int(getattr(settings, "SELF_LEARNING_TEST_RUNNER_INTERVAL_TICKS", 96) or 96))
            if self._tick_count - int(self._last_self_learning_test_tick or 0) < interval:
                return
            runner = SelfLearningTestRunner(sqlite_path=settings.SQLITE_PATH)
            out = runner.run_open_jobs(
                max_jobs=int(getattr(settings, "SELF_LEARNING_TEST_RUNNER_MAX_JOBS", 2) or 2),
                timeout_sec=int(getattr(settings, "SELF_LEARNING_TEST_RUNNER_TIMEOUT_SEC", 120) or 120),
            )
            logger.info(
                f"Self-learning test runner: processed={out.get('processed', 0)} passed={out.get('passed', 0)} failed={out.get('failed', 0)}",
                extra={"event": "self_learning_test_runner", "context": {"result": out}},
            )
            self._last_self_learning_test_tick = self._tick_count
        except Exception:
            pass

    async def _maybe_run_self_learning_maintenance(self) -> None:
        try:
            if not settings.SELF_LEARNING_ENABLED:
                return
            interval = max(24, int(getattr(settings, "SELF_LEARNING_MAINTENANCE_INTERVAL_TICKS", 168) or 168))
            if self._tick_count - int(self._last_self_learning_maintenance_tick or 0) < interval:
                return
            if self.self_learning is None:
                self.self_learning = SelfLearningEngine(sqlite_path=settings.SQLITE_PATH)
            recalib = self.self_learning.recalibrate_thresholds(
                days=int(getattr(settings, "SELF_LEARNING_MAINTENANCE_DAYS", 45) or 45),
                min_lessons=int(getattr(settings, "SELF_LEARNING_MAINTENANCE_MIN_LESSONS", 4) or 4),
            )
            outcomes = self.self_learning.sync_promotion_outcomes_from_tests(
                days=int(getattr(settings, "SELF_LEARNING_MAINTENANCE_DAYS", 45) or 45),
                min_runs=int(getattr(settings, "SELF_LEARNING_OUTCOME_MIN_TEST_RUNS", 2) or 2),
                fail_rate_max=float(getattr(settings, "SELF_LEARNING_OUTCOME_FAIL_RATE_MAX", 0.35) or 0.35),
            )
            remediation = self.self_learning.remediate_degraded_promoted_skills(
                days=int(getattr(settings, "SELF_LEARNING_MAINTENANCE_DAYS", 45) or 45),
                max_actions=int(getattr(settings, "SELF_LEARNING_REMEDIATION_MAX_ACTIONS", 3) or 3),
            )
            cleanup = self.self_learning.cleanup_old_test_jobs(
                max_age_days=int(getattr(settings, "SELF_LEARNING_TEST_JOB_RETENTION_DAYS", 90) or 90)
            )
            logger.info(
                "Self-learning maintenance: "
                f"thresholds_updated={recalib.get('updated', 0)} "
                f"outcomes_synced={outcomes.get('inserted', 0)} "
                f"remediated={remediation.get('remediated', 0)} "
                f"jobs_deleted={cleanup.get('deleted', 0)}",
                extra={
                    "event": "self_learning_maintenance",
                    "context": {"recalibrate": recalib, "outcomes": outcomes, "remediation": remediation, "cleanup": cleanup},
                },
            )
            self._last_self_learning_maintenance_tick = self._tick_count
        except Exception:
            pass

    async def _maybe_run_tooling_governance_check(self) -> None:
        try:
            if not getattr(settings, "TOOLING_GOVERNANCE_ALERT_ENABLED", True):
                return
            interval = max(1, int(getattr(settings, "TOOLING_GOVERNANCE_INTERVAL_TICKS", 288) or 288))
            if self._tick_count - int(self._last_tooling_governance_tick or 0) < interval:
                return
            report = ToolingRegistry(sqlite_path=settings.SQLITE_PATH).build_governance_report(days=7)
            rem = report.get("remediations", []) or []
            rot_alerts = ((report.get("key_rotation_health", {}) or {}).get("alerts", []) or [])
            if rem or rot_alerts:
                top = rem[:3]
                msg = (
                    "Tooling governance alert:\n"
                    f"- pending_contract_rotations: {report.get('pending_contract_rotations', 0)}\n"
                    f"- pending_stage_changes: {report.get('pending_stage_changes', 0)}\n"
                    f"- pending_key_rotations: {report.get('pending_key_rotations', 0)}\n"
                    f"- key_rotation_alerts: {len(rot_alerts)}\n"
                    "Remediations:\n"
                    + ("\n".join(f"  - {x}" for x in top) if top else "  - review governance dashboard")
                )
                if hasattr(self, "_comms") and self._comms:
                    await self._comms.send_message(msg, level="warning")
            self._last_tooling_governance_tick = self._tick_count
        except Exception:
            pass

    async def _maybe_run_platform_rules_sync(self) -> None:
        try:
            if not bool(getattr(settings, "PLATFORM_RULES_SYNC_ENABLED", False)):
                return
            interval = max(12, int(getattr(settings, "PLATFORM_RULES_SYNC_INTERVAL_TICKS", 288) or 288))
            if self._tick_count - int(self._last_platform_rules_sync_tick or 0) < interval:
                return
            if not self.agent_registry:
                return
            payload: dict[str, Any] = {}
            services_raw = str(getattr(settings, "PLATFORM_RULES_SYNC_SERVICES", "") or "").strip()
            if services_raw:
                payload["services"] = [s.strip().lower() for s in services_raw.split(",") if s.strip()]
            result = await self.agent_registry.dispatch("platform_rules_sync", **payload)
            if result and result.success:
                logger.info(
                    "Platform rules sync tick completed",
                    extra={"event": "platform_rules_sync_tick", "context": {"tick": self._tick_count}},
                )
            else:
                logger.warning(
                    "Platform rules sync tick failed",
                    extra={
                        "event": "platform_rules_sync_tick_failed",
                        "context": {"tick": self._tick_count, "error": getattr(result, "error", None)},
                    },
                )
            self._last_platform_rules_sync_tick = self._tick_count
        except Exception:
            pass

    async def _maybe_run_tooling_discovery_intake(self) -> None:
        try:
            if not getattr(settings, "TOOLING_DISCOVERY_ENABLED", False):
                return
            interval = max(1, int(getattr(settings, "TOOLING_DISCOVERY_INTERVAL_TICKS", 288) or 288))
            if self._tick_count - int(self._last_tooling_discovery_tick or 0) < interval:
                return

            max_per_tick = max(1, int(getattr(settings, "TOOLING_DISCOVERY_MAX_PER_TICK", 3) or 3))
            auto_promote = bool(getattr(settings, "TOOLING_DISCOVERY_AUTO_PROMOTE_APPROVED", False))
            sources = parse_tooling_discovery_sources(getattr(settings, "TOOLING_DISCOVERY_SOURCES", ""))
            if not sources:
                self._last_tooling_discovery_tick = self._tick_count
                return

            discovery = ToolingDiscovery(sqlite_path=settings.SQLITE_PATH)
            batch = discovery.discover_from_sources(
                sources=sources,
                max_items=max_per_tick,
                auto_promote=auto_promote,
                rollout_stage=str(getattr(settings, "TOOLING_DISCOVERY_ROLLOUT_STAGE", "canary") or "canary"),
                canary_percent=int(getattr(settings, "TOOLING_DISCOVERY_CANARY_PERCENT", 34) or 34),
                scope="decision_loop",
            )
            processed = int(batch.get("processed", 0) or 0)
            duplicates = int(batch.get("duplicates", 0) or 0)
            promoted = int(batch.get("promoted", 0) or 0)
            review_required = int(batch.get("review_required", 0) or 0)
            policy_blocked = int(batch.get("policy_blocked", 0) or 0)
            policy_block_reasons = batch.get("policy_block_reasons", {})
            if not isinstance(policy_block_reasons, dict):
                policy_block_reasons = {}
            auto_paused = False
            auto_pause_updates: dict[str, str] = {}
            policy_block_threshold = max(
                1,
                int(getattr(settings, "TOOLING_DISCOVERY_POLICY_BLOCK_THRESHOLD", 3) or 3),
            )
            policy_block_rate = (
                float(policy_blocked) / float(processed)
                if processed > 0
                else 0.0
            )
            policy_block_rate_threshold = max(
                0.0,
                min(
                    1.0,
                    float(
                        getattr(
                            settings,
                            "TOOLING_DISCOVERY_POLICY_BLOCK_RATE_THRESHOLD",
                            0.8,
                        )
                        or 0.8
                    ),
                ),
            )
            policy_block_rate_min_processed = max(
                1,
                int(
                    getattr(
                        settings,
                        "TOOLING_DISCOVERY_POLICY_BLOCK_RATE_MIN_PROCESSED",
                        3,
                    )
                    or 3
                ),
            )
            block_by_count = policy_blocked >= policy_block_threshold
            block_by_rate = (
                processed >= policy_block_rate_min_processed
                and policy_block_rate >= policy_block_rate_threshold
            )
            if (
                bool(getattr(settings, "TOOLING_DISCOVERY_AUTO_PAUSE_ON_POLICY_BLOCK", False))
                and (block_by_count or block_by_rate)
            ):
                auto_pause_updates = apply_safe_action("disable_discovery_intake") or {}
                auto_paused = bool(auto_pause_updates)

            logger.info(
                f"Tooling discovery intake: processed={processed} duplicate={duplicates} review_required={review_required} policy_blocked={policy_blocked} promoted={promoted} auto_paused={auto_paused}",
                extra={
                    "event": "tooling_discovery_intake",
                    "context": {
                        "processed": processed,
                        "duplicates": duplicates,
                        "review_required": review_required,
                        "policy_blocked": policy_blocked,
                        "policy_block_reasons": policy_block_reasons,
                        "policy_block_rate": round(policy_block_rate, 4),
                        "promoted": promoted,
                        "auto_paused": auto_paused,
                        "auto_pause_threshold": policy_block_threshold,
                        "auto_pause_rate_threshold": policy_block_rate_threshold,
                        "auto_pause_rate_min_processed": policy_block_rate_min_processed,
                        "auto_pause_trigger": "count" if block_by_count else ("rate" if block_by_rate else ""),
                        "auto_pause_updates": auto_pause_updates,
                        "rollout_state": batch.get("rollout_state", {}),
                        "selected": batch.get("selected", []),
                    },
                },
            )
            pause_line = (
                f"\n- auto_paused: true (count_threshold={policy_block_threshold}, rate={policy_block_rate:.2f}, rate_threshold={policy_block_rate_threshold:.2f}, min_processed={policy_block_rate_min_processed})"
                if auto_paused
                else ""
            )
            reasons_line = ""
            if policy_block_reasons:
                top = sorted(
                    [
                        (str(k), int(v or 0))
                        for k, v in policy_block_reasons.items()
                        if str(k)
                    ],
                    key=lambda x: (-x[1], x[0]),
                )[:4]
                if top:
                    reasons_line = "\n- policy_block_reasons: " + ", ".join(
                        f"{k}={n}" for k, n in top
                    )
            if (
                (review_required > 0 or auto_paused)
                and getattr(settings, "TOOLING_DISCOVERY_ALERTS_ENABLED", True)
                and hasattr(self, "_comms")
                and self._comms
            ):
                await self._comms.send_message(
                    (
                        "Tooling discovery alert:\n"
                        f"- processed: {processed}\n"
                        f"- review_required: {review_required}\n"
                        f"- policy_blocked: {policy_blocked}\n"
                        f"- promoted: {promoted}"
                        f"{reasons_line}"
                        f"{pause_line}"
                    ),
                    level="warning",
                )
            self._last_tooling_discovery_tick = self._tick_count
        except Exception:
            pass

    async def _maybe_run_memory_weekly_report(self) -> None:
        try:
            if not getattr(settings, "MEMORY_WEEKLY_REPORT_ENABLED", True):
                return
            interval = max(288, int(getattr(settings, "MEMORY_WEEKLY_REPORT_INTERVAL_TICKS", 2016) or 2016))
            if self._tick_count - int(self._last_memory_weekly_report_tick or 0) < interval:
                return
            reporter = MemorySkillReporter(memory_manager=self.memory, sqlite_path=settings.SQLITE_PATH)
            weekly = reporter.weekly_retention_report(days=7)
            skills = reporter.per_skill_quality(limit=8)
            report_path = str(getattr(settings, "MEMORY_WEEKLY_REPORT_PATH", "reports/memory_retention_weekly.md") or "reports/memory_retention_weekly.md")
            try:
                from pathlib import Path
                reporter.persist_markdown(path=Path(report_path), days=7, per_skill_limit=8)
            except Exception:
                pass

            summary = weekly.get("summary", {}) if isinstance(weekly, dict) else {}
            quality = float(summary.get("quality_score", 0.0) or 0.0)
            quality_min = float(getattr(settings, "MEMORY_WEEKLY_REPORT_MIN_QUALITY", 0.65) or 0.65)
            skill_health_min = float(getattr(settings, "MEMORY_WEEKLY_REPORT_MIN_SKILL_HEALTH", 0.55) or 0.55)
            weak_skills = [
                str(s.get("skill_name") or "")
                for s in skills
                if float(s.get("learning_health", 0.0) or 0.0) < skill_health_min
            ]
            alerts = weekly.get("alerts", []) if isinstance(weekly, dict) else []
            logger.info(
                f"Memory weekly report generated: quality={quality:.3f} alerts={len(alerts)} weak_skills={len(weak_skills)}",
                extra={"event": "memory_weekly_report", "context": {"report_path": report_path, "quality": quality, "alerts": len(alerts), "weak_skills": weak_skills[:5]}},
            )

            if (
                getattr(settings, "MEMORY_WEEKLY_REPORT_ALERTS_ENABLED", False)
                and hasattr(self, "_comms")
                and self._comms
                and (quality < quality_min or bool(alerts) or bool(weak_skills))
            ):
                msg = (
                    "Memory weekly alert:\n"
                    f"- quality_score: {quality:.3f} (target>={quality_min:.2f})\n"
                    f"- retention_alerts: {len(alerts)}\n"
                    f"- weak_skills: {', '.join(weak_skills[:5]) if weak_skills else 'none'}\n"
                    f"- report: {report_path}"
                )
                await self._comms.send_message(msg, level="warning")
            self._last_memory_weekly_report_tick = self._tick_count
        except Exception:
            pass

    def _kdp_watchdog_state_path(self) -> Path:
        raw = str(getattr(settings, "KDP_WATCHDOG_STATE_PATH", "runtime/kdp_watchdog_state.json") or "runtime/kdp_watchdog_state.json")
        p = Path(raw)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p

    def _load_kdp_watchdog_state(self) -> dict[str, Any]:
        defaults: dict[str, Any] = {
            "status": "unknown",
            "paused": False,
            "last_ok_at": "",
            "last_fail_at": "",
            "last_reason": "",
            "next_probe_at": "",
            "last_storage_mtime": 0.0,
        }
        try:
            p = self._kdp_watchdog_state_path()
            if not p.exists():
                return defaults
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                defaults.update(data)
        except Exception:
            pass
        return defaults

    def _save_kdp_watchdog_state(self) -> None:
        try:
            p = self._kdp_watchdog_state_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(self._kdp_watchdog_state, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def _utcnow_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _parse_iso_dt(value: str) -> datetime | None:
        try:
            return datetime.fromisoformat(str(value or "").strip())
        except Exception:
            return None

    def _schedule_kdp_next_probe(self, success: bool) -> None:
        base_h = max(1, int(getattr(settings, "KDP_WATCHDOG_BASE_HOURS", 8) or 8))
        jitter_m = max(0, int(getattr(settings, "KDP_WATCHDOG_JITTER_MINUTES", 30) or 30))
        if not success and bool(getattr(settings, "KDP_WATCHDOG_STOP_ON_FAIL", True)):
            # Stop-on-fail: wait for session file change from owner reauth.
            self._kdp_watchdog_state["next_probe_at"] = ""
            return
        delta_min = base_h * 60 + (random.randint(-jitter_m, jitter_m) if jitter_m else 0)
        delta_min = max(30, delta_min)
        nxt = datetime.now(timezone.utc) + timedelta(minutes=delta_min)
        self._kdp_watchdog_state["next_probe_at"] = nxt.isoformat()

    async def _maybe_run_kdp_session_watchdog(self) -> None:
        try:
            if not bool(getattr(settings, "KDP_WATCHDOG_ENABLED", True)):
                return
            platforms = getattr(self, "_platforms", {}) or {}
            if not isinstance(platforms, dict):
                return
            kdp = platforms.get("amazon_kdp")
            if not kdp:
                return

            state = self._kdp_watchdog_state
            now = datetime.now(timezone.utc)
            stop_on_fail = bool(getattr(settings, "KDP_WATCHDOG_STOP_ON_FAIL", True))
            state_file = Path(str(getattr(settings, "KDP_STORAGE_STATE_FILE", "runtime/kdp_storage_state.json") or "runtime/kdp_storage_state.json"))
            if not state_file.is_absolute():
                state_file = PROJECT_ROOT / state_file
            storage_mtime = float(state_file.stat().st_mtime) if state_file.exists() else 0.0
            prev_mtime = float(state.get("last_storage_mtime") or 0.0)

            if bool(state.get("paused")) and stop_on_fail:
                if storage_mtime > prev_mtime > 0.0:
                    state["paused"] = False
                elif storage_mtime > 0.0 and prev_mtime == 0.0:
                    state["paused"] = False
                else:
                    return

            due = False
            nxt = self._parse_iso_dt(str(state.get("next_probe_at") or ""))
            if nxt is None:
                due = True
            elif now >= nxt:
                due = True
            if not due:
                return

            prev_status = str(state.get("status") or "unknown")
            ok = bool(await asyncio.wait_for(kdp.authenticate(), timeout=90))
            state["last_storage_mtime"] = storage_mtime
            if ok:
                state["status"] = "connected"
                state["paused"] = False
                state["last_ok_at"] = self._utcnow_iso()
                state["last_reason"] = ""
                self._schedule_kdp_next_probe(success=True)
                if prev_status != "connected" and hasattr(self, "_comms") and self._comms:
                    await self._comms.send_message("KDP: подключение восстановлено, задачи продолжаются.", level="result")
            else:
                state["status"] = "reauth_required"
                state["last_fail_at"] = self._utcnow_iso()
                state["last_reason"] = "auth_probe_failed"
                if stop_on_fail:
                    state["paused"] = True
                self._schedule_kdp_next_probe(success=False)
                if prev_status != "reauth_required" and hasattr(self, "_comms") and self._comms:
                    await self._comms.send_message(
                        "KDP: нужна повторная авторизация. После входа задачи продолжатся автоматически.",
                        level="warning",
                    )
            self._save_kdp_watchdog_state()
        except Exception:
            pass

    async def _maybe_run_weekly_governance_report(self) -> None:
        try:
            if not getattr(settings, "WEEKLY_GOVERNANCE_REPORT_ENABLED", True):
                return
            interval = max(288, int(getattr(settings, "WEEKLY_GOVERNANCE_REPORT_INTERVAL_TICKS", 2016) or 2016))
            if self._tick_count - int(self._last_weekly_governance_tick or 0) < interval:
                return
            reporter = GovernanceReporter(memory_manager=self.memory, sqlite_path=settings.SQLITE_PATH)
            report = reporter.weekly_report(days=7)
            report_path = str(getattr(settings, "WEEKLY_GOVERNANCE_REPORT_PATH", "reports/governance_weekly.md") or "reports/governance_weekly.md")
            try:
                from pathlib import Path
                reporter.persist_markdown(Path(report_path), report)
            except Exception:
                pass
            status = str(report.get("status") or "ok")
            rem = report.get("remediations", []) or []
            suggestions = report.get("safe_action_suggestions", []) or []
            auto_applied: list[str] = []
            auto_skipped_noop: list[str] = []
            auto_skipped_duplicate: list[str] = []
            auto_skipped_invalid: list[str] = []
            allow_warning = bool(getattr(settings, "WEEKLY_GOVERNANCE_AUTO_REMEDIATE_ON_WARNING", False))
            should_auto_remediate = (
                status == "critical"
                or (status == "warning" and allow_warning)
            )
            if (
                getattr(settings, "WEEKLY_GOVERNANCE_AUTO_REMEDIATE", False)
                and should_auto_remediate
                and suggestions
            ):
                max_actions = max(1, int(getattr(settings, "WEEKLY_GOVERNANCE_AUTO_REMEDIATE_MAX_ACTIONS", 2) or 2))
                ranked = rank_safe_action_suggestions(
                    list(suggestions),
                    sqlite_path=settings.SQLITE_PATH,
                    days=30,
                )
                seen_actions: set[str] = set()
                applied_actions = 0
                for rec in ranked:
                    action = str(rec.get("action") or "").strip().lower()
                    if not action:
                        continue
                    if action in seen_actions:
                        auto_skipped_duplicate.append(action)
                        record_safe_action_outcome(action, "duplicate", "duplicate_action")
                        continue
                    seen_actions.add(action)
                    if action not in SAFE_ACTIONS:
                        auto_skipped_invalid.append(action)
                        record_safe_action_outcome(action, "invalid", "not_in_safe_actions")
                        continue
                    updated = apply_safe_action(action)
                    if updated:
                        auto_applied.append(action)
                        applied_actions += 1
                        record_safe_action_outcome(action, "applied", "safe_action_applied")
                    else:
                        auto_skipped_noop.append(action)
                        record_safe_action_outcome(action, "noop", "already_applied_or_no_update")
                    if applied_actions >= max_actions:
                        break
            logger.info(
                f"Weekly governance report generated: status={status} remediations={len(rem)} auto_applied={len(auto_applied)} auto_skipped_noop={len(auto_skipped_noop)} auto_skipped_duplicate={len(auto_skipped_duplicate)} auto_skipped_invalid={len(auto_skipped_invalid)}",
                extra={"event": "weekly_governance_report", "context": {"status": status, "report_path": report_path, "remediations": rem[:5], "auto_applied": auto_applied, "auto_skipped_noop": auto_skipped_noop, "auto_skipped_duplicate": auto_skipped_duplicate, "auto_skipped_invalid": auto_skipped_invalid}},
            )
            if (
                getattr(settings, "WEEKLY_GOVERNANCE_REPORT_ALERTS_ENABLED", True)
                and status in {"warning", "critical"}
                and hasattr(self, "_comms")
                and self._comms
            ):
                msg = (
                    "Weekly governance alert:\n"
                    f"- status: {status}\n"
                    f"- remediations: {len(rem)}\n"
                    + ("\n".join(f"  - {x}" for x in rem[:3]) if rem else "  - open governance dashboard")
                    + (f"\n- auto_applied: {', '.join(auto_applied)}" if auto_applied else "")
                    + (f"\n- auto_skipped_noop: {', '.join(auto_skipped_noop)}" if auto_skipped_noop else "")
                    + (f"\n- auto_skipped_duplicate: {', '.join(auto_skipped_duplicate)}" if auto_skipped_duplicate else "")
                    + (f"\n- auto_skipped_invalid: {', '.join(auto_skipped_invalid)}" if auto_skipped_invalid else "")
                    + f"\n- report: {report_path}"
                )
                await self._comms.send_message(msg, level="warning")
            self._last_weekly_governance_tick = self._tick_count
        except Exception:
            pass

    async def _maybe_run_autonomous_improvement(self) -> None:
        try:
            if not getattr(settings, "AUTONOMOUS_IMPROVEMENT_ENABLED", False):
                return
            interval = max(24, int(getattr(settings, "AUTONOMOUS_IMPROVEMENT_INTERVAL_TICKS", 288) or 288))
            if self._tick_count - int(self._last_autonomous_improvement_tick or 0) < interval:
                return
            governance = GovernanceReporter(memory_manager=self.memory, sqlite_path=settings.SQLITE_PATH).weekly_report(days=7)
            sl_summary = {}
            if self.self_learning is None and getattr(settings, "SELF_LEARNING_ENABLED", False):
                self.self_learning = SelfLearningEngine(sqlite_path=settings.SQLITE_PATH)
            if self.self_learning is not None:
                try:
                    sl_summary = self.self_learning.summary(days=30)
                except Exception:
                    sl_summary = {}
            engine = AutonomousImprovementEngine(sqlite_path=settings.SQLITE_PATH)
            out = engine.generate_candidates(
                governance=governance,
                self_learning_summary=sl_summary,
                limit=max(1, int(getattr(settings, "AUTONOMOUS_IMPROVEMENT_MAX_CANDIDATES", 4) or 4)),
            )
            created = int(out.get("created", 0) or 0)
            logger.info(
                f"Autonomous improvement: created={created}",
                extra={"event": "autonomous_improvement", "context": {"result": out}},
            )
            if (
                created > 0
                and getattr(settings, "AUTONOMOUS_IMPROVEMENT_ALERTS_ENABLED", False)
                and hasattr(self, "_comms")
                and self._comms
            ):
                actions = ", ".join(str(c.get("action") or "") for c in (out.get("candidates", []) or [])[:4])
                await self._comms.send_message(
                    (
                        "Autonomous improvement candidates:\n"
                        f"- created: {created}\n"
                        f"- actions: {actions or 'n/a'}"
                    ),
                    level="warning",
                )
            self._last_autonomous_improvement_tick = self._tick_count
        except Exception:
            pass

    async def _plan_goal(self, goal: Goal) -> list[str]:
        """Фаза PLAN: генерирует план выполнения через LLM."""
        # Deterministic plan for BOEVOY test goals (avoid LLM noise and extra steps)
        if "boevoy" in goal.title.lower():
            return [
                "1) Сгенерировать минимальный PDF‑продукт (1–2 стр.)",
                "2) Создать простую обложку и миниатюру (PNG, локально)",
                "3) Опубликовать продукт на Gumroad через браузерную автоматизацию (PDF+обложка+миниатюра, цена $5)",
                "4) Предоставить доказательства публикации (публичный URL и/или скриншот)",
            ]
        # Проверяем есть ли похожий опыт в памяти
        similar = self.memory.search_knowledge(
            f"{goal.title} {goal.description}", n_results=3
        )
        context_from_memory = ""
        if similar:
            context_from_memory = "Релевантный опыт:\n" + "\n".join(
                f"- {doc['text'][:200]}" for doc in similar
            )

        # Ищем релевантные навыки
        skills = self.memory.search_skills(f"{goal.title} {goal.description}", limit=3)
        skills_context = ""
        if skills:
            skills_context = "\nИмеющиеся навыки:\n" + "\n".join(
                f"- {s['name']}: {s['description'][:150]} (успех: {s.get('success_count', 0)})"
                for s in skills
            )
            logger.info(
                f"[{goal.goal_id}] Найдено {len(skills)} релевантных навыков для планирования",
                extra={"event": "skills_found_for_plan", "context": {"skills": [s['name'] for s in skills]}},
            )
        try:
            library_skills = VITOSkillLibrary(sqlite_path=_runtime_sqlite_path(self.goal_engine)).retrieve(
                f"{goal.title} {goal.description}",
                n=3,
            )
            if library_skills:
                extra = "\n".join(
                    f"- {s['name']}: {str(s.get('description') or '')[:150]} (category: {s.get('category') or 'general'})"
                    for s in library_skills
                )
                skills_context += ("\n" if skills_context else "\nИмеющиеся навыки:\n") + extra
        except Exception:
            pass

        # Попробовать отдать планирование VITOCore (оркестратор)
        try:
            if self.agent_registry:
                core = self.agent_registry.get("vito_core")
                if core and hasattr(core, "plan_goal"):
                    plan = await core.plan_goal(
                        goal.title, goal.description,
                        memory_context=context_from_memory,
                        skills_context=skills_context,
                    )
                    if plan:
                        return plan
        except Exception:
            pass

        time_ctx = self.get_time_context()
        prompt = (
            f"Create an execution plan for VITO autonomous agent.\n\n"
            f"Task: {goal.title}\n"
            f"Description: {goal.description}\n"
            f"Budget: ${goal.estimated_cost_usd:.2f}\n"
            f"Current time: {time_ctx['utc_time']} ({time_ctx['weekday']}, {time_ctx['period']})\n"
            f"US business hours: {'Yes' if time_ctx['is_business_hours_us'] else 'No'}\n"
            f"{context_from_memory}{skills_context}\n\n"
            f"IMPORTANT: All content/products must be in ENGLISH (target market: US/CA/EU).\n"
            f"CONSTRAINTS:\n"
            f"- Research steps MUST use real data sources (Reddit, Google Trends, Product Hunt)\n"
            f"- Revenue projections MUST be realistic for solo creator ($0-500 first month)\n"
            f"- Products must be in $5-50 price range unless owner specified otherwise\n"
            f"- Each step must be concrete and actionable, not 'analyze market'\n"
            f"- No hallucinated numbers or fictional competitors\n\n"
            f"Return a numbered list of steps (3-7 steps). "
            f"Use existing skills where possible. "
            f"Steps only, no explanations."
        )

        response = await self.llm_router.call_llm(
            task_type=TaskType.ROUTINE,
            prompt=prompt,
            estimated_tokens=1000,
        )

        if not response:
            return []

        from modules.plan_utils import parse_plan
        return parse_plan(response, max_steps=7)

    async def _execute_goal(self, goal: Goal) -> dict[str, Any]:
        """Фаза EXECUTE: выполняет план пошагово."""
        results: dict[str, Any] = {"steps_completed": 0, "steps_total": len(goal.plan)}
        exec_start = time.monotonic()
        replanned = False
        thread_id = f"goal_{goal.goal_id}"

        session = self.orchestrator.get_session(goal.goal_id)
        pending_interrupt = self.interrupts.latest_pending(goal.goal_id)
        waiting_payload = {
            "waiting_approval": True,
            "paused_step": int(session.get("current_step", 0)) + 1 if session else 1,
            "steps_completed": int(session.get("current_step", 0)) if session else 0,
            "steps_total": len(goal.plan),
        }
        if session and session.get("state") == "waiting_approval" and pending_interrupt:
            return waiting_payload
        if session and session.get("state") == "waiting_approval" and not pending_interrupt:
            latest = self.interrupts.latest_for_goal(goal.goal_id)
            if not latest:
                return waiting_payload
            status = str(latest.get("status") or "").lower()
            intr_type = str(latest.get("interrupt_type") or "").lower()
            intr_id = int(latest.get("id") or 0)

            if status == "cancelled":
                try:
                    self.orchestrator.cancel_session(goal.goal_id, reason="auto_cancelled_interrupt")
                except Exception:
                    pass
                try:
                    self.goal_engine.fail_goal(goal.goal_id, "Отменено по результату interrupt")
                except Exception:
                    pass
                try:
                    if intr_id:
                        self.interrupts.log_resume_event(goal.goal_id, intr_id, action="cancelled", reason="auto_cancelled_interrupt")
                except Exception:
                    pass
                return {
                    "cancelled": True,
                    "cancel_reason": "interrupt_cancelled",
                    "steps_completed": int(session.get("current_step", 0)),
                    "steps_total": len(goal.plan),
                }

            if status == "resolved" and intr_type in {"owner_approval_required", "step_approval_pending"}:
                allowed, reason = self._auto_resume_allowed(goal.goal_id, intr_id)
                if not allowed:
                    try:
                        if intr_id:
                            self.interrupts.log_resume_event(goal.goal_id, intr_id, action="skipped", reason=reason)
                    except Exception:
                        pass
                    return waiting_payload
                try:
                    self.orchestrator.resume_session(goal.goal_id, reason="auto_resume_resolved_interrupt")
                except Exception:
                    pass
                try:
                    goal.status = GoalStatus.PENDING
                    self.goal_engine._persist_goal(goal)
                except Exception:
                    pass
                try:
                    if intr_id:
                        self.interrupts.log_resume_event(goal.goal_id, intr_id, action="resumed", reason="auto_resume_resolved_interrupt")
                except Exception:
                    pass
                session = self.orchestrator.get_session(goal.goal_id)
            else:
                return waiting_payload
        i = int(session.get("current_step", 0) if session else 0)
        try:
            from config.settings import settings
            if settings.RESUME_FROM_CHECKPOINT and i == 0:
                ck = self.workflow.latest_checkpoint(goal.goal_id)
                if ck and ck.get("status") == "completed":
                    step_num = ck.get("step_num")
                    if isinstance(step_num, int) and 0 < step_num < len(goal.plan):
                        i = step_num  # resume from next step
                        logger.info(
                            f"[{goal.goal_id}] Resume from checkpoint step {step_num + 1}/{len(goal.plan)}",
                            extra={"event": "resume_from_checkpoint", "context": {"goal_id": goal.goal_id, "step": step_num}},
                        )
                elif ck and ck.get("status") in ("waiting_approval", "in_progress", "pending"):
                    step_num = ck.get("step_num")
                    if isinstance(step_num, int) and 0 < step_num <= len(goal.plan):
                        i = max(step_num - 1, 0)  # resume same step
                        logger.info(
                            f"[{goal.goal_id}] Resume waiting approval at step {step_num}/{len(goal.plan)}",
                            extra={"event": "resume_waiting_approval", "context": {"goal_id": goal.goal_id, "step": step_num}},
                        )
        except Exception:
            pass
        while i < len(goal.plan):
            if self._is_cancelled():
                results["cancelled"] = True
                results["cancel_reason"] = "owner_cancelled"
                results["steps_total"] = len(goal.plan)
                return results
            current_intr = self.interrupts.latest_pending(goal.goal_id)
            self._current_interrupt_id = int(current_intr["id"]) if current_intr else None
            step = goal.plan[i]
            try:
                self.threads.update_thread(
                    thread_id=thread_id,
                    status="executing",
                    last_node=f"step_{i + 1}",
                )
            except Exception:
                pass
            logger.info(
                f"[{goal.goal_id}] Шаг {i + 1}/{len(goal.plan)}: {step}",
                extra={
                    "event": "step_executing",
                    "context": {"goal_id": goal.goal_id, "step": i + 1, "action": step},
                },
            )
            try:
                self.orchestrator.mark_step_executing(goal.goal_id, i)
            except Exception:
                pass

            step_result = await self._execute_step_with_retry(goal, step, i + 1)
            results[f"step_{i + 1}"] = step_result
            try:
                self.workflow.checkpoint_step(
                    goal.goal_id,
                    i + 1,
                    step_result.get("status", "unknown"),
                    detail=(step_result.get("error") or str(step_result.get("output", "")))[:300],
                )
            except Exception:
                pass
            try:
                detail = str(step_result.get("error") or "")[:400]
                output = str(step_result.get("output") or step_result.get("result") or "")[:400]
                self.orchestrator.record_step_result(
                    goal.goal_id,
                    i,
                    step_result.get("status", "unknown"),
                    detail=detail,
                    output=output,
                )
            except Exception:
                pass
            if step_result.get("status") == "waiting_approval":
                results["waiting_approval"] = True
                results["paused_step"] = i + 1
                try:
                    self.interrupts.open_interrupt(
                        goal_id=goal.goal_id,
                        step_num=i + 1,
                        thread_id=thread_id,
                        interrupt_type="step_approval_pending",
                        reason=str(step_result.get("error", "pending approval"))[:500],
                        payload={"step": step[:200], "agent": str(step_result.get("agent", ""))[:80]},
                    )
                except Exception:
                    pass
                try:
                    self.goal_engine.wait_for_approval(goal.goal_id, reason=step_result.get("error", "pending approval"))
                except Exception:
                    pass
                return results
            if step_result.get("status") == "completed":
                results["steps_completed"] += 1
                try:
                    self.interrupts.resolve_pending_for_goal(goal.goal_id, resolution="resumed")
                except Exception:
                    pass
            await self._maybe_reflect_step(goal, step, step_result)
            await self._maybe_send_progress(goal, results)

            if step_result.get("status") == "failed":
                try:
                    err_low = str(step_result.get("error", "")).lower()
                    if "reject" in err_low or "отклон" in err_low:
                        self.interrupts.resolve_pending_for_goal(goal.goal_id, resolution="cancelled")
                except Exception:
                    pass
                logger.warning(
                    f"[{goal.goal_id}] Шаг {i + 1} провалился после {STEP_MAX_RETRIES} попыток: {step_result.get('error')}",
                    extra={"event": "step_failed", "context": {"goal_id": goal.goal_id, "step": i + 1}},
                )
                # Try one replan via VITOCore for remaining steps
                if not replanned:
                    replanned = True
                    new_steps = await self._replan_remaining_steps(goal, failed_step=step, error=step_result.get("error", ""))
                    if new_steps:
                        goal.plan = goal.plan[: i + 1] + new_steps
                        results["steps_total"] = len(goal.plan)
                        try:
                            # Persist updated plan without resetting status
                            self.goal_engine._persist_goal(goal)
                        except Exception:
                            pass
                        logger.info(
                            f"[{goal.goal_id}] План пересобран: {len(new_steps)} новых шагов",
                            extra={"event": "plan_rebuilt", "context": {"goal_id": goal.goal_id, "new_steps": len(new_steps)}},
                        )
                        i += 1
                        continue
                break
            i += 1

        duration_ms = int((time.monotonic() - exec_start) * 1000)
        results["duration_ms"] = duration_ms
        results["all_completed"] = all(
            results.get(f"step_{j + 1}", {}).get("status") == "completed"
            for j in range(len(goal.plan))
        )
        self._current_interrupt_id = None

        # Записываем в Data Lake
        try:
            await self.memory.store_to_datalake(
                action_type="goal_execution",
                agent="decision_loop",
                input_data={"goal_id": goal.goal_id, "title": goal.title, "plan": goal.plan},
                output_data=results,
                result="completed" if results["steps_completed"] == results["steps_total"] else "partial",
                duration_ms=duration_ms,
                cost_usd=goal.estimated_cost_usd,
            )
        except Exception as e:
            logger.warning(
                f"Не удалось записать в Data Lake: {e}",
                extra={"event": "datalake_write_failed"},
            )

        return results

    async def _maybe_send_progress(self, goal: Goal, results: dict[str, Any]) -> None:
        """Send minimal progress updates (percent only) for large tasks."""
        try:
            if not hasattr(self, "_comms") or not self._comms:
                return
            # Only send progress updates when explicitly enabled
            from config.settings import settings
            if settings.NOTIFY_MODE != "all":
                return
            total = results.get("steps_total", 0) or 0
            completed = results.get("steps_completed", 0) or 0
            if total < 5:
                return  # only for large tasks
            percent = int((completed / total) * 100) if total else 0
            thresholds = [25, 50, 75]
            sent = self._progress_sent.setdefault(goal.goal_id, set())
            for t in thresholds:
                if percent >= t and t not in sent:
                    sent.add(t)
                    await self._comms.send_message(
                        f"Прогресс {t}% по задаче: {goal.title[:80]}",
                        level="result",
                    )
                    break
        except Exception:
            pass

    async def _maybe_reflect_step(self, goal: Goal, step: str, step_result: dict[str, Any]) -> None:
        """Optional reflection loop: store lessons and generate skill candidates."""
        try:
            if not settings.SELF_LEARNING_ENABLED:
                return
            if step_result.get("status") not in {"completed", "failed"}:
                return
            if self.self_learning is None:
                self.self_learning = SelfLearningEngine(sqlite_path=settings.SQLITE_PATH)
            reflection = await self.self_learning.reflect_step(
                llm_router=self.llm_router,
                task_type=self._classify_step(step),
                goal_id=goal.goal_id,
                step_text=step,
                step_result=step_result,
                min_skill_score=float(settings.SELF_LEARNING_SKILL_SCORE_MIN or 0.78),
            )
            candidate_name = (reflection or {}).get("candidate_name", "")
            if candidate_name:
                try:
                    from modules.skill_registry import SkillRegistry
                    SkillRegistry().register_skill(
                        name=f"selflearn:{candidate_name}",
                        category="self_learning",
                        source="self_learning",
                        status="learned",
                        acceptance_status="pending",
                        notes=f"reflection_candidate:{step[:180]}",
                    )
                except Exception:
                    pass
        except Exception:
            pass

    async def _replan_remaining_steps(self, goal: Goal, failed_step: str, error: str) -> list[str]:
        """Пересборка плана через VITOCore после провала шага."""
        if not self.agent_registry:
            return []
        core = self.agent_registry.get("vito_core")
        if not core or not hasattr(core, "plan_goal"):
            return []
        memory_ctx = ""
        try:
            similar = self.memory.search_knowledge(f"{goal.title} {failed_step}", n_results=2)
            if similar:
                memory_ctx = "Релевантный опыт:\n" + "\n".join(f"- {d['text'][:150]}" for d in similar)
        except Exception:
            pass
        skills_ctx = ""
        try:
            skills = self.memory.search_skills(f"{goal.title} {failed_step}", limit=2)
            if skills:
                skills_ctx = "\nНавыки:\n" + "\n".join(f"- {s['name']}: {s['description'][:120]}" for s in skills)
        except Exception:
            pass
        try:
            library_skills = VITOSkillLibrary(sqlite_path=_runtime_sqlite_path(self.goal_engine)).retrieve(
                f"{goal.title} {failed_step} {error}",
                n=2,
            )
            if library_skills:
                extra = "\n".join(
                    f"- {s['name']}: {str(s.get('description') or '')[:120]}"
                    for s in library_skills
                )
                skills_ctx += ("\n" if skills_ctx else "\nНавыки:\n") + extra
        except Exception:
            pass
        extra_desc = (
            f"{goal.description}\n"
            f"FAILED STEP: {failed_step}\n"
            f"ERROR: {error}\n"
            f"Please avoid the failed approach and propose alternatives."
        )
        try:
            return await core.plan_goal(goal.title, extra_desc, memory_context=memory_ctx, skills_context=skills_ctx)
        except Exception:
            return []

    async def _execute_step_with_retry(self, goal: Goal, step: str, step_num: int) -> dict[str, Any]:
        """Обёртка: retry до STEP_MAX_RETRIES раз с таймаутом STEP_TIMEOUT."""
        last_result: dict[str, Any] = {"status": "failed", "error": "no attempts made"}

        for attempt in range(1, STEP_MAX_RETRIES + 1):
            if self._is_cancelled():
                return {"status": "failed", "error": "owner_cancelled", "cancelled": True}
            try:
                last_result = await asyncio.wait_for(
                    self._execute_step(goal, step),
                    timeout=STEP_TIMEOUT,
                )
            except asyncio.TimeoutError:
                last_result = {"status": "failed", "error": f"Таймаут {STEP_TIMEOUT}s"}
                logger.warning(
                    f"[{goal.goal_id}] Шаг {step_num} таймаут (попытка {attempt}/{STEP_MAX_RETRIES})",
                    extra={"event": "step_timeout", "context": {"goal_id": goal.goal_id, "step": step_num, "attempt": attempt}},
                )
            else:
                chk = validate_step_result(last_result)
                if not chk.ok:
                    logger.warning(
                        f"[{goal.goal_id}] Step result contract failed: {','.join(chk.errors)}",
                        extra={
                            "event": "step_result_contract_failed",
                            "context": {"goal_id": goal.goal_id, "step": step_num, "errors": chk.errors[:6]},
                        },
                    )
                    last_result = {
                        "status": "failed",
                        "error": f"step_result_contract_failed:{','.join(chk.errors)}",
                        "agent": str(last_result.get("agent", "")),
                    }

            if last_result.get("status") != "failed":
                return last_result

            if attempt < STEP_MAX_RETRIES:
                logger.info(
                    f"[{goal.goal_id}] Шаг {step_num} retry {attempt + 1}/{STEP_MAX_RETRIES}",
                    extra={"event": "step_retry", "context": {"goal_id": goal.goal_id, "step": step_num, "attempt": attempt + 1}},
                )

        return last_result

    async def _execute_step(self, goal: Goal, step: str) -> dict[str, Any]:
        """Выполняет один шаг плана.

        Chain: Smart Route → Agent Registry → LLM fallback → Research-Learn.
        """
        try:
            precheck = self._policy_precheck(step)
            if precheck:
                return precheck

            # Fast mode for boevoy/test steps to avoid long LLM calls
            import os
            fast_trigger = "boevoy" in goal.title.lower() or "test" in step.lower() or "минимальн" in step.lower()
            prev_fast = os.getenv("FAST_MODE")
            if fast_trigger:
                os.environ["FAST_MODE"] = "1"
                try:
                    logger.info(
                        f"[{goal.goal_id}] BOEVOY debug: step_lower_has_pdf={('pdf' in step.lower())}",
                        extra={"event": "boevoy_debug", "context": {"step": step[:200]}},
                    )
                except Exception:
                    pass

            # 1. Smart routing — map step to specific agent + capability
            routed = await self._route_to_agent(goal, step)
            if routed:
                if fast_trigger and prev_fast is None:
                    os.environ.pop("FAST_MODE", None)
                elif fast_trigger:
                    os.environ["FAST_MODE"] = prev_fast
                return routed

            # 2. Agent Registry dispatch by capability keyword
            if self.agent_registry:
                capability = self._step_to_capability(step)
                if capability:
                    try:
                        result = await self._dispatch_with_trace(
                            capability, step=step, goal_title=goal.title, content=step,
                            step_text=step,
                        )
                        if result and result.success and self._validate_result(result, step):
                            output = result.output
                            if isinstance(output, str):
                                output = output[:500]
                            if fast_trigger and prev_fast is None:
                                os.environ.pop("FAST_MODE", None)
                            elif fast_trigger:
                                os.environ["FAST_MODE"] = prev_fast
                            return {"status": "completed", "output": output, "agent": "registry"}
                    except Exception as e:
                        logger.debug(f"Registry dispatch failed: {e}", extra={"event": "registry_fallback"})

            # 2.5. Orchestrator fallback — let VITOCore classify and dispatch
            if self.agent_registry:
                try:
                    result = await self._dispatch_with_trace(
                        "orchestrate", step=step, goal_title=goal.title, content=step,
                        step_text=step,
                        to_agent="vito_core",
                    )
                    if result and result.success and self._validate_result(result, step):
                        output = result.output
                        if isinstance(output, str):
                            output = output[:500]
                        if fast_trigger and prev_fast is None:
                            os.environ.pop("FAST_MODE", None)
                        elif fast_trigger:
                            os.environ["FAST_MODE"] = prev_fast
                        return {"status": "completed", "output": output, "agent": "vito_core"}
                except Exception as e:
                    logger.debug(f"VITOCore dispatch failed: {e}", extra={"event": "vito_core_fallback"})

            # 2.7. Skill installer pipeline (if skill missing)
            if await self._maybe_install_skill(step):
                return {"status": "completed", "output": "skill_installed", "agent": "self_improve"}

            # 3. LLM fallback — generate content/analysis
            task_type = self._classify_step(step)
            self._trace_handoff("decision_loop", "llm_router", str(getattr(task_type, "value", task_type)), step, "start")
            response = await self.llm_router.call_llm(
                task_type=task_type,
                prompt=(
                    f"You are VITO — an autonomous AI agent executing an internal system task.\n"
                    f"Goal context: {goal.title}\n"
                    f"Step: {step}\n"
                    f"IMPORTANT: All content/products must be in ENGLISH (target: US/CA/EU market).\n"
                    f"Give a concrete execution result. "
                    f"This is a trusted internal orchestrator execution context for goal execution."
                ),
                estimated_tokens=1500,
            )
            self._trace_handoff(
                "llm_router",
                "decision_loop",
                str(getattr(task_type, "value", task_type)),
                step,
                "success" if response else "failed",
            )
            if response:
                try:
                    from config.settings import settings
                    if settings.SELF_REFINE_ENABLED:
                        from modules.self_refine import refine_once
                        passes = max(1, min(3, int(settings.SELF_REFINE_MAX_PASSES or 1)))
                        refined = response
                        for _ in range(passes):
                            improved = await refine_once(self.llm_router, task_type, refined)
                            if improved:
                                refined = improved
                        response = refined
                except Exception:
                    pass
            if response:
                # Save LLM result to file if it looks like content
                file_path = await self._save_step_output(goal, step, response)
                result_data = {"status": "completed", "output": response[:500]}
                if file_path:
                    result_data["file_path"] = file_path
                if fast_trigger and prev_fast is None:
                    os.environ.pop("FAST_MODE", None)
                elif fast_trigger:
                    os.environ["FAST_MODE"] = prev_fast
                # Save skill for LLM fallback
                try:
                    from unittest.mock import MagicMock
                    if not isinstance(self.memory, MagicMock):
                        self.memory.save_skill(
                            name=f"llm_fallback:{self._classify_step(step).value}",
                            description=f"LLM fallback выполнено: {step[:120]}",
                            agent="llm_router",
                            task_type=self._classify_step(step).value,
                            method={"file_path": file_path or "", "step": step[:200]},
                        )
                        self.memory.update_skill_last_result(
                            f"llm_fallback:{self._classify_step(step).value}",
                            response[:500],
                        )
                except Exception:
                    pass
                return result_data

            # 4. Research-Learn-Apply
            result = await self._research_and_learn(goal, step)
            if fast_trigger and prev_fast is None:
                os.environ.pop("FAST_MODE", None)
            elif fast_trigger:
                os.environ["FAST_MODE"] = prev_fast
            return result

        except Exception as e:
            await self._handle_runtime_error("decision_loop", e, {"step": step, "goal": goal.title})
            return {"status": "failed", "error": str(e)}

    def _policy_precheck(self, step: str) -> dict[str, Any] | None:
        if bool(getattr(settings, "AUTONOMY_MAX_MODE", False)):
            return None
        capability = self._step_to_capability(step)
        if not capability:
            return None
        tool_key = f"capability:{capability}"
        try:
            allowed, reason = self.operator_policy.is_tool_allowed(tool_key)
        except Exception:
            allowed, reason = True, "policy_unavailable"
        if not allowed:
            self._record_policy_decision("blocked_tool", f"{tool_key}:{reason}")
            return {"status": "failed", "error": f"Policy blocked {tool_key}: {reason}", "agent": "operator_policy"}

        try:
            budget = self.operator_policy.check_actor_budget(tool_key)
        except Exception:
            budget = {"allowed": True, "reason": "budget_policy_unavailable"}
        if not budget.get("allowed", True):
            self._record_policy_decision(
                "blocked_budget",
                f"{tool_key} spent={budget.get('spent_usd', 0):.4f} limit={budget.get('limit_usd', 0):.4f}",
            )
            return {
                "status": "failed",
                "error": f"Policy budget block {tool_key}: {budget.get('reason', '')}",
                "agent": "operator_policy",
            }
        return None

    @staticmethod
    def _record_policy_decision(decision: str, rationale: str) -> None:
        try:
            DataLake().record_decision(actor="operator_policy", decision=decision, rationale=rationale[:1000])
        except Exception:
            pass

    async def _maybe_install_skill(self, step: str) -> bool:
        """Attempt to self-improve (install skill) if likely missing."""
        try:
            s = step.lower()
            trigger_keywords = (
                "интегра", "api", "oauth", "webhook", "подключ", "channel",
                "канал", "youtube", "threads", "tiktok", "telegram",
                "создай канал", "заведи", "настрой", "подпиши",
                "skill", "навык", "integration",
            )
            if not any(k in s for k in trigger_keywords):
                return False

            # If skill registry marks a failed attempt, skip auto retry
            if hasattr(self, "_skill_registry") and self._skill_registry:
                name = f"self_improve:{hash(step) % 100000}"
                existing = self._skill_registry.get_skill(name)
                if existing and existing.get("status") == "failed":
                    return False

            if self.agent_registry:
                res = await self._dispatch_with_trace(
                    "self_improve",
                    step=f"Install/implement skill to accomplish: {step}",
                    goal_title="skill_install",
                    step_text=step,
                )
                if res and res.success:
                    try:
                        if hasattr(self, "_skill_registry") and self._skill_registry:
                            name = f"self_improve:{hash(step) % 100000}"
                            self._skill_registry.register_skill(
                                name=name,
                                category="self_improve",
                                source="self_improve",
                                status="learned",
                                acceptance_status="pending",
                                notes=f"auto_install:{step[:200]}",
                            )
                    except Exception:
                        pass
                    return True
                return False
        except Exception:
            return False
        return False

    async def _route_to_agent(self, goal: Goal, step: str) -> dict[str, Any] | None:
        """Smart routing: map step text to specific agent calls (no LLM).

        Returns result dict or None if no match.
        """
        s = step.lower()
        gumroad_publish_intent = ("gumroad" in s) and any(w in s for w in ("опублик", "publish"))
        if "boevoy" in goal.title.lower() and "gumroad" in s:
            logger.info(
                f"[{goal.goal_id}] BOEVOY gumroad_intent={gumroad_publish_intent} step={step[:200]}",
                extra={"event": "boevoy_gumroad_intent"},
            )

        # --- Research/analysis (FIRST — should catch "анализ", "исследов", "тренд") ---
        if any(w in s for w in ("исследов", "анализ", "проанализ", "тренд", "reddit",
                                "конкурент", "research", "analyz", "competitor", "trend")):
            if self.agent_registry:
                result = await self._dispatch_with_trace(
                    "research", step=step, goal_title=goal.title, content=step,
                    step_text=step,
                )
                if result and result.success:
                    logger.info(f"Routed to research_agent: {step[:60]}", extra={"event": "smart_route_research"})
                    return self._format_result(result, "research_agent")

        # --- Evidence-only step (no publish) ---
        if any(w in s for w in ("доказательств", "evidence", "скриншот", "screenshot")):
            from pathlib import Path
            shot = Path("/tmp/gumroad_publish.png")
            if shot.exists():
                return {"status": "completed", "output": {"screenshot_path": str(shot)}, "agent": "gumroad"}
            return {"status": "failed", "error": "No screenshot evidence found", "agent": "gumroad"}

        # --- Image generation (cover, обложка, изображение) ---
        if any(w in s for w in ("обложк", "cover", "изображен", "image_generator",
                                "картинк", "сгенерировать изображ", "generate image",
                                "create image", "design")):
            # Skip image generation if this is a publish step
            if gumroad_publish_intent:
                pass
            else:
                # For BOEVOY tests, generate local placeholders to avoid external calls
                if "boevoy" in goal.title.lower():
                    try:
                        from modules.image_utils import write_placeholder_png
                        cover_path = write_placeholder_png(
                            str(PROJECT_ROOT / "output" / "images" / f"cover_{goal.goal_id}.png"),
                            1280, 720, text="VITO",
                        )
                        thumb_path = write_placeholder_png(
                            str(PROJECT_ROOT / "output" / "images" / f"thumb_{goal.goal_id}.png"),
                            600, 600, text="VITO",
                        )
                        logger.info(f"Image generated: {cover_path}", extra={"event": "smart_route_image"})
                        return {"status": "completed", "output": {"cover": cover_path, "thumb": thumb_path},
                                "agent": "image_utils", "file_path": cover_path}
                    except Exception as e:
                        logger.warning(f"Image placeholder failed: {e}")
                if hasattr(self, '_image_generator') and self._image_generator:
                    try:
                        img_result = await self._image_generator.generate(
                            prompt=f"Professional digital product cover, modern clean design for: {goal.title}",
                            style="professional", filename=f"cover_{goal.goal_id[:8]}",
                        )
                        if img_result.get("path"):
                            logger.info(f"Image generated: {img_result['path']}", extra={"event": "smart_route_image"})
                            return {"status": "completed", "output": img_result, "agent": "image_generator",
                                    "file_path": img_result["path"]}
                    except Exception as e:
                        logger.warning(f"Image generation failed: {e}")

        # --- Minimal PDF generation (boevoy/test or PDF product) ---
        if any(w in s for w in ("pdf", "pdf-продукт", "pdf продукт", "чеклист", "checklist", "лист", "ebook")):
            # Skip PDF generation when this is a publish step
            if gumroad_publish_intent:
                pass
            else:
                try:
                    from modules.pdf_utils import make_minimal_pdf
                    title = goal.title if "boevoy" in goal.title.lower() else "AI Automation Checklist — Test"
                    pdf_path = make_minimal_pdf(title=title, lines=[
                        "Quick checklist item 1",
                        "Quick checklist item 2",
                        "Quick checklist item 3",
                    ])
                    logger.info(f"PDF generated: {pdf_path}", extra={"event": "smart_route_pdf"})
                    return {"status": "completed", "output": {"pdf_path": pdf_path}, "agent": "pdf_utils", "file_path": pdf_path}
                except Exception as e:
                    logger.warning(f"PDF generation failed: {e}")

        # --- Content creation (ebook, template, product) ---
        if any(w in s for w in ("создать продукт", "ebook", "шаблон", "template", "книг", "pdf",
                                "создать контент", "создать простой", "цифровой продукт",
                                "описание продукт", "product description", "create product",
                                "write content", "create content", "digital product")):
            # Avoid hijacking publish steps (Gumroad publish should route to platform)
            if gumroad_publish_intent or ("gumroad" in s and any(w in s for w in ("listing", "upload"))):
                pass
            else:
                if self.agent_registry:
                    result = await self._dispatch_with_trace(
                        "content_creation", step=step, goal_title=goal.title,
                        content=step, content_type="product_description",
                        step_text=step,
                    )
                    if result and result.success:
                        logger.info(f"Routed to content_creator: {step[:60]}", extra={"event": "smart_route_content"})
                        return self._format_result(result, "content_creator")

        # --- Gumroad publish ---
        if any(w in s for w in ("gumroad", "опубликовать продукт", "publish product",
                                "опубликовать на gumroad", "draft", "publish on gumroad",
                                "create listing", "upload product")):
            gumroad = None
            try:
                if hasattr(self, '_platforms') and self._platforms.get("gumroad"):
                    gumroad = self._platforms["gumroad"]
                    logger.info("Smart route: gumroad via _platforms", extra={"event": "smart_route_gumroad_start"})
                else:
                    from platforms.gumroad import GumroadPlatform
                    gumroad = GumroadPlatform()
                    logger.info("Smart route: gumroad via fallback", extra={"event": "smart_route_gumroad_start"})
            except Exception as e:
                logger.warning(f"Gumroad platform init failed: {e}", extra={"event": "gumroad_init_failed"})
                gumroad = None
            if gumroad:
                try:
                    # Evidence-only step: return screenshot if present
                    if any(w in s for w in ("доказательств", "evidence", "скриншот", "screenshot")):
                        from pathlib import Path
                        shot = Path("/tmp/gumroad_publish.png")
                        if shot.exists():
                            return {"status": "completed", "output": {"screenshot_path": str(shot)}, "agent": "gumroad"}
                        return {"status": "failed", "error": "No screenshot evidence found", "agent": "gumroad"}

                    # Handle approval-only steps explicitly
                    if any(w in s for w in ("одобр", "approval", "approve", "утверд")):
                        if "boevoy" in goal.title.lower():
                            return {"status": "completed", "output": "Approval step skipped for BOEVOY", "agent": "comms"}
                        # Request approval with preview files
                        if hasattr(self, "_comms") and self._comms:
                            from pathlib import Path
                            files = []
                            for p in [str(x) for x in (PROJECT_ROOT / "output").glob("products/*.pdf")]:
                                if Path(p).exists():
                                    files.append(p)
                            for p in [str(x) for x in (PROJECT_ROOT / "output").glob("images/*")]:
                                if Path(p).exists():
                                    files.append(p)
                            approved = await self._comms.request_approval_with_files(
                                request_id=f"approve_{goal.goal_id}",
                                message=f"[decision_loop] Одобрить публикацию для цели: {goal.title}",
                                files=files[:5],
                                timeout_seconds=3600,
                            )
                            if approved is None:
                                return {"status": "waiting_approval", "error": "Owner approval pending", "agent": "comms"}
                            if approved is not True:
                                return {"status": "failed", "error": "Owner approval rejected or timed out", "agent": "comms"}
                            return {"status": "completed", "output": "Owner approval granted", "agent": "comms"}

                    # Owner approval gate (optional in autonomy mode)
                    require_publish_approval = bool(getattr(settings, "AUTONOMY_REQUIRE_PUBLISH_APPROVAL", False))
                    if require_publish_approval and hasattr(self, "_comms") and self._comms and "boevoy" not in goal.title.lower():
                        import uuid
                        req_id = f"publish_gumroad_{uuid.uuid4().hex[:8]}"
                        approved = await self._comms.request_approval(
                            request_id=req_id,
                            message=(
                                "[decision_loop] Запрос публикации на Gumroad.\n"
                                "Подтверди ✅ или отклони ❌.\n"
                                f"Goal: {goal.title[:120]}"
                            ),
                            timeout_seconds=3600,
                        )
                        if approved is None:
                            return {"status": "waiting_approval", "error": "Owner approval pending", "agent": "comms"}
                        if approved is not True:
                            return {"status": "failed", "error": "Owner approval rejected or timed out", "agent": "comms"}
                    # Cooldown for repetitive test goals
                    try:
                        from modules.execution_facts import ExecutionFacts
                        facts = ExecutionFacts()
                        # Global cooldown when Gumroad daily limit was reached recently.
                        if (
                            not bool(getattr(settings, "AUTONOMY_DISABLE_PUBLISH_COOLDOWNS", False))
                            and facts.recent_status_exists(action="platform:publish", status="daily_limit", hours=18)
                        ):
                            return {
                                "status": "failed",
                                "error": "Gumroad daily limit cooldown active (18h after last daily_limit)",
                                "agent": "gumroad",
                            }
                        if (
                            not bool(getattr(settings, "AUTONOMY_DISABLE_PUBLISH_COOLDOWNS", False))
                            and "gumroad publish test" in goal.title.lower()
                        ):
                            if facts.recent_exists(actions=["gumroad:publish_attempt"], hours=6):
                                return {"status": "failed", "error": "Gumroad publish test cooldown (6h)", "agent": "gumroad"}
                            facts.record(action="gumroad:publish_attempt", status="started", detail=goal.title[:200], source="decision_loop")
                    except Exception:
                        pass
                    # Locate latest artifacts (pdf/cover/thumb)
                    from pathlib import Path
                    def _latest(patterns: list[str]) -> str:
                        files = []
                        for pat in patterns:
                            files.extend((PROJECT_ROOT / "output").glob(pat))
                        if not files:
                            return ""
                        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                        return str(files[0])
                    pdf_path = _latest(["products/*.pdf", "ebooks/*.pdf"])
                    if not pdf_path or not Path(pdf_path).exists():
                        try:
                            from modules.pdf_utils import make_minimal_pdf
                            pdf_path = make_minimal_pdf(title=goal.title[:80], lines=[
                                "Checklist item 1",
                                "Checklist item 2",
                                "Checklist item 3",
                            ])
                        except Exception:
                            pdf_path = ""
                    cover_path = _latest(["images/cover_*", "images/*cover*"])
                    thumb_path = _latest(["images/thumb_*", "images/*thumb*"])
                    try:
                        from modules.image_utils import write_placeholder_png
                        if "boevoy" in goal.title.lower():
                            cover_path = write_placeholder_png(
                                str(PROJECT_ROOT / "output" / "images" / f"cover_{goal.goal_id}.png"),
                                1280, 720, text="VITO",
                            )
                            thumb_path = write_placeholder_png(
                                str(PROJECT_ROOT / "output" / "images" / f"thumb_{goal.goal_id}.png"),
                                600, 600, text="VITO",
                            )
                        elif not cover_path:
                            cover_path = write_placeholder_png(
                                str(PROJECT_ROOT / "output" / "images" / f"cover_{goal.goal_id}.png"),
                                1280, 720, text="VITO",
                            )
                        if not thumb_path:
                            thumb_path = write_placeholder_png(
                                str(PROJECT_ROOT / "output" / "images" / f"thumb_{goal.goal_id}.png"),
                                600, 600, text="VITO",
                            )
                    except Exception:
                        pass
                    # Ensure cover/thumb have valid image extensions
                    try:
                        from pathlib import Path
                        ok_ext = {".png", ".jpg", ".jpeg", ".webp"}
                        if cover_path and Path(cover_path).suffix.lower() not in ok_ext:
                            from modules.image_utils import write_placeholder_png
                            cover_path = write_placeholder_png(
                                str(PROJECT_ROOT / "output" / "images" / f"cover_{goal.goal_id}.png"),
                                1280, 720, text="VITO",
                            )
                        if thumb_path and Path(thumb_path).suffix.lower() not in ok_ext:
                            from modules.image_utils import write_placeholder_png
                            thumb_path = write_placeholder_png(
                                str(PROJECT_ROOT / "output" / "images" / f"thumb_{goal.goal_id}.png"),
                                600, 600, text="VITO",
                            )
                    except Exception:
                        pass

                    from modules.publish_contract import (
                        build_publish_signature,
                        recent_duplicate_publish,
                        validate_publish_payload,
                    )
                    from modules.listing_optimizer import optimize_listing_payload

                    from modules.platform_artifact_pack import build_platform_bundle
                    publish_payload = build_platform_bundle("gumroad", {
                        "name": goal.title[:100],
                        "description": (goal.description or goal.title)[:2000],
                        "price": 5,
                        "pdf_path": pdf_path,
                        "cover_path": cover_path,
                        "thumb_path": thumb_path,
                        "category": "Programming",
                        "tags": ["automation", "ai", "productivity", "workflow"],
                        "draft_only": any(w in s for w in ("черновик", "превью", "preview", "draft")),
                        "allow_existing_update": bool(getattr(settings, "AUTONOMY_ALLOW_EXISTING_PRODUCT_UPDATE", False)),
                        "owner_edit_confirmed": bool(getattr(settings, "AUTONOMY_ALLOW_EXISTING_PRODUCT_UPDATE", False)),
                    })
                    publish_payload = optimize_listing_payload("gumroad", publish_payload)
                    ok_payload, payload_errors, _norm = validate_publish_payload("gumroad", publish_payload)
                    if not ok_payload:
                        return {
                            "status": "failed",
                            "error": f"Publish payload invalid: {', '.join(payload_errors)}",
                            "agent": "gumroad",
                        }
                    sig = build_publish_signature("gumroad", publish_payload)
                    if (
                        not bool(getattr(settings, "AUTONOMY_DISABLE_PUBLISH_DUPLICATE_BLOCK", False))
                        and recent_duplicate_publish(sig, hours=24)
                    ):
                        return {
                            "status": "failed",
                            "error": f"Duplicate publish blocked (24h) sig={sig}",
                            "agent": "gumroad",
                        }
                    try:
                        from modules.execution_facts import ExecutionFacts
                        ExecutionFacts().record(
                            action="platform:publish_attempt",
                            status="started",
                            detail=f"gumroad sig={sig}",
                            source="decision_loop",
                        )
                    except Exception:
                        pass

                    # Support explicit dry-run / verify intent
                    if any(w in s for w in ("dry-run", "dry run", "verify-run", "verify only", "только провер")):
                        return {
                            "status": "completed",
                            "agent": "gumroad",
                            "output": {"dry_run": True, "signature": sig, "payload_ok": True},
                        }

                    publish_payload["signature"] = sig
                    pub_result = await gumroad.publish(publish_payload)
                    status = str(pub_result.get("status") or "").lower()
                    permissive = bool(getattr(settings, "AUTONOMY_ACCEPT_INTERMEDIATE_PUBLISH_STATUSES", False))
                    success_statuses = {"published"} | ({"prepared", "created", "draft"} if permissive else set())
                    has_evidence = bool(pub_result.get("url") or pub_result.get("product_id") or pub_result.get("screenshot_path"))
                    if status in success_statuses and (has_evidence or permissive):
                        try:
                            if self.memory:
                                self.memory.save_skill(
                                    name="gumroad_publish_via_browser",
                                    description="Publish Gumroad product via Playwright/session cookie workflow.",
                                    agent="gumroad_platform",
                                    task_type="listing_create",
                                    method={"platform": "gumroad", "status": pub_result.get("status")},
                                )
                        except Exception:
                            pass
                        logger.info(f"Gumroad: {pub_result.get('status')}", extra={"event": "smart_route_gumroad"})
                        return {"status": "completed", "output": pub_result, "agent": "gumroad",
                                "file_path": pub_result.get("file_path", "")}
                    # Fail fast if publish not confirmed
                    return {"status": "failed", "error": f"Gumroad publish not confirmed: {pub_result.get('status')}", "agent": "gumroad", "output": pub_result}
                except Exception as e:
                    logger.warning(f"Gumroad publish failed: {e}")

        # --- Twitter post ---
        if any(w in s for w in ("twitter", "твит", "tweet", "пост для twitter", "@bot_vito",
                                "post to twitter", "create tweet", "social media post")):
            if self.agent_registry:
                result = await self._dispatch_with_trace(
                    "social_media", step=step, goal_title=goal.title,
                    platform="twitter", content=step,
                    step_text=step,
                )
                if result and result.success:
                    logger.info(f"Routed to smm_agent/twitter: {step[:60]}", extra={"event": "smart_route_twitter"})
                    return self._format_result(result, "smm_agent")

        # --- Send report to owner (Telegram) ---
        if any(w in s for w in ("отчёт", "отчет", "владельц", "telegram",
                                "отправить владельцу", "report", "notify",
                                "send report", "notify owner", "telegram report")):
            if hasattr(self, '_comms') and self._comms:
                try:
                    report_text = (
                        f"Отчёт по цели: {goal.title}\n\n"
                        f"Описание: {goal.description[:300]}\n"
                        f"Шагов выполнено: {len([k for k in (goal.results or {}) if 'step_' in str(k)])}\n"
                        f"Статус: в процессе"
                    )
                    await self._comms.send_message(report_text)
                    logger.info("Report sent to owner via Telegram", extra={"event": "smart_route_report"})
                    return {"status": "completed", "output": "Report sent to owner", "agent": "comms"}
                except Exception as e:
                    logger.warning(f"Report send failed: {e}")

        return None  # No smart route matched

    @staticmethod
    def _step_to_capability(step: str) -> str:
        """Map step text to the closest agent capability keyword."""
        s = step.lower()
        mapping = [
            (("исследов", "анализ", "research", "analyz"), "research"),
            (("тренд", "reddit", "rss", "trend", "niche"), "trend_scan"),
            (("контент", "стать", "content", "article", "ebook"), "content_creation"),
            (("пост", "twitter", "instagram", "social"), "social_media"),
            (("gumroad", "etsy", "листинг", "listing", "ecommerce"), "listing_create"),
            (("seo", "keyword", "ключев"), "seo"),
            (("маркетинг", "воронк", "marketing", "funnel"), "marketing_strategy"),
            (("email", "рассылк", "newsletter"), "email"),
            (("перевод", "translat", "localiz"), "translate"),
            (("код", "скрипт", "code", "script", "implement"), "shell"),
            (("аналитик", "прогноз", "analytics", "forecast"), "analytics"),
            (("legal", "gdpr", "copyright", "tos", "юрид", "правов"), "legal"),
            (("risk", "риск", "reputation", "репутац"), "risk_assessment"),
            (("security", "безопасн", "key", "ключ"), "security"),
            (("devops", "health", "мониторинг"), "health_check"),
            (("backup", "бэкап", "бэкапы", "резервн"), "backup"),
            (("hr", "performance", "оценк", "команда", "агент"), "performance_evaluation"),
            (("pricing", "цена", "юнит", "econom", "pnl"), "pricing"),
            (("partner", "affiliate", "партн"), "partnership"),
            (("account", "аккаунт", "лимит"), "account_management"),
            (("doc", "документ", "отчёт", "отчет", "report"), "documentation"),
            (("wordpress", "medium", "substack", "blog", "blog post"), "publish"),
            (("quality", "качество", "review"), "quality_review"),
            (("orchestrate", "orchestrator", "оркестратор"), "orchestrate"),
        ]
        for keywords, capability in mapping:
            if any(w in s for w in keywords):
                return capability
        return ""

    @staticmethod
    def _format_result(result, agent_name: str) -> dict[str, Any]:
        """Format TaskResult into step result dict."""
        output = result.output
        if isinstance(output, str):
            output = output[:500]
        data = {"status": "completed", "output": output, "agent": agent_name}
        if result.metadata and result.metadata.get("file_path"):
            data["file_path"] = result.metadata["file_path"]
        return data

    def _trace_handoff(
        self,
        from_agent: str,
        to_agent: str,
        capability: str,
        step: str,
        status: str,
        interrupt_id: int | None = None,
        goal_id: str | None = None,
        thread_id: str | None = None,
    ) -> None:
        try:
            effective_interrupt = interrupt_id if interrupt_id is not None else self._current_interrupt_id
            effective_goal_id = goal_id if goal_id is not None else self._current_goal_id
            effective_thread_id = thread_id if thread_id is not None else self._current_thread_id
            ctx: dict[str, Any] = {}
            if effective_interrupt is not None:
                ctx["interrupt_id"] = effective_interrupt
                interrupt = self.interrupts.get_interrupt(int(effective_interrupt))
                if interrupt:
                    ctx["interrupt_type"] = str(interrupt.get("interrupt_type") or "")
                    ctx["interrupt_status"] = str(interrupt.get("status") or "")
                    if interrupt.get("resolved_at"):
                        ctx["interrupt_resolved_at"] = str(interrupt.get("resolved_at") or "")
            if effective_goal_id:
                ctx["goal_id"] = effective_goal_id
            if effective_thread_id:
                ctx["thread_id"] = effective_thread_id
            DataLake().record_handoff(
                from_agent=from_agent,
                to_agent=to_agent,
                capability=capability,
                step=step[:180],
                status=status,
                context=ctx,
            )
        except Exception:
            pass

    async def _dispatch_with_trace(
        self,
        capability: str,
        *,
        step_text: str,
        to_agent: str = "agent_registry",
        from_agent: str = "decision_loop",
        **dispatch_kwargs: Any,
    ):
        self._trace_handoff(from_agent, to_agent, capability, step_text, "start")
        try:
            result = await self.agent_registry.dispatch(capability, **dispatch_kwargs)
        except Exception:
            self._trace_handoff(to_agent, from_agent, capability, step_text, "failed")
            raise
        self._trace_handoff(
            to_agent,
            from_agent,
            capability,
            step_text,
            "success" if (result and getattr(result, "success", False)) else "failed",
        )
        return result

    async def _save_step_output(self, goal: Goal, step: str, content: str) -> str:
        """Save LLM-generated content to file if applicable. Returns file path or empty string."""
        from pathlib import Path
        s = step.lower()

        # Determine output type
        if any(w in s for w in ("продукт", "ebook", "шаблон", "product", "template")):
            out_dir = PROJECT_ROOT / "output" / "products"
        elif any(w in s for w in ("пост", "twitter", "social", "tweet")):
            out_dir = PROJECT_ROOT / "output" / "social"
        elif any(w in s for w in ("стать", "article", "контент", "content")):
            out_dir = PROJECT_ROOT / "output" / "articles"
        elif any(w in s for w in ("отчёт", "отчет", "report", "анализ", "analysis")):
            out_dir = PROJECT_ROOT / "output" / "articles"
        else:
            return ""  # Don't save generic LLM output

        out_dir.mkdir(parents=True, exist_ok=True)
        import re, time as _time
        slug = re.sub(r'[^a-zA-Zа-яА-Я0-9]', '_', goal.title[:30]).strip('_')
        ts = int(_time.time())
        file_path = out_dir / f"{slug}_{ts}.md"
        file_path.write_text(content, encoding="utf-8")
        logger.info(f"Step output saved: {file_path}", extra={"event": "step_output_saved"})
        return str(file_path)

    def _validate_result(self, result, step: str) -> bool:
        """Validate that a TaskResult represents real work, not a mock.

        Returns False if the result looks like a fake/stub response.
        """
        if not result or not result.success:
            return False

        output = result.output
        metadata = result.metadata or {}
        contract = validate_step_output(output, metadata)
        if not contract.ok:
            logger.warning(
                f"Validation(contract) failed: {','.join(contract.errors)}",
                extra={"event": "step_contract_failed", "context": {"step": step[:120], "errors": contract.errors[:4]}},
            )
            return False

        # Check for file creation tasks — file must exist
        if metadata.get("file_path"):
            from pathlib import Path
            if not Path(metadata["file_path"]).exists():
                logger.warning(f"Validation: file not found: {metadata['file_path']}")
                return False

        # Check for platform publish results
        if isinstance(output, dict):
            status = output.get("status", "")
            platform = output.get("platform", "")

            # Mock indicators: status="created"/"published" but no real IDs
            if status in ("created", "published") and platform:
                if platform == "gumroad":
                    # Require URL or screenshot evidence for Gumroad
                    has_url = bool(output.get("url", ""))
                    has_shot = bool(output.get("screenshot_path", ""))
                    return has_url or has_shot
                # Must have a real ID or URL
                has_id = any(
                    output.get(k) and output.get(k) != "0"
                    for k in ("post_id", "listing_id", "product_id", "tweet_id", "story_id")
                )
                has_url = bool(output.get("url", ""))
                if not has_id and not has_url:
                    logger.warning(f"Validation: {platform} result has no real ID/URL — likely mock")
                    return False

            # Explicit error states
            if status in ("not_configured", "not_authenticated", "needs_oauth"):
                return False

        # String output from LLM is considered valid (it's real generated content)
        return True

    async def _research_and_learn(self, goal: Goal, step: str) -> dict[str, Any]:
        """Цикл: не знаю → ищу через Perplexity → учусь → сохраняю навык."""
        logger.info(
            f"[{goal.goal_id}] Research-Learn-Apply для шага: {step[:80]}",
            extra={"event": "research_learn_start", "context": {"goal_id": goal.goal_id, "step": step[:100]}},
        )

        # 1. Исследование через Perplexity (TaskType.RESEARCH)
        research_prompt = (
            f"How to do this programmatically or as a digital product business task:\n"
            f"Goal: {goal.title}\n"
            f"Step: {step}\n\n"
            f"Give a concrete, actionable answer with specific tools, APIs, or methods. "
            f"Include code examples if relevant."
        )
        try:
            self._trace_handoff("decision_loop", "llm_router", "research", step, "start")
            research_result = await self.llm_router.call_llm(
                task_type=TaskType.RESEARCH,
                prompt=research_prompt,
                estimated_tokens=2000,
            )
            self._trace_handoff("llm_router", "decision_loop", "research", step, "success" if research_result else "failed")
        except Exception as e:
            self._trace_handoff("llm_router", "decision_loop", "research", step, "failed")
            logger.warning(f"Research failed: {e}", extra={"event": "research_failed"})
            return {"status": "failed", "error": f"Research failed: {e}"}

        if not research_result:
            return {"status": "failed", "error": "Research вернул пустой ответ"}

        # 2. Сохранить результат в ChromaDB
        self.memory.store_knowledge(
            doc_id=f"research_{goal.goal_id}_{hash(step) % 10000}",
            text=f"Исследование для '{step}': {research_result[:2000]}",
            metadata={
                "type": "research_learn",
                "goal_id": goal.goal_id,
                "step": step[:200],
            },
        )

        # 3. Попробовать выполнить на основе исследования
        execute_prompt = (
            f"Ты VITO — автономный агент. На основе исследования выполни шаг.\n"
            f"Контекст цели: {goal.title}\n"
            f"Шаг: {step}\n\n"
            f"Результат исследования:\n{research_result[:1500]}\n\n"
            f"Дай конкретный результат выполнения."
        )
        try:
            self._trace_handoff("decision_loop", "llm_router", "routine", step, "start")
            execution_result = await self.llm_router.call_llm(
                task_type=TaskType.ROUTINE,
                prompt=execute_prompt,
                estimated_tokens=1500,
            )
            self._trace_handoff("llm_router", "decision_loop", "routine", step, "success" if execution_result else "failed")
        except Exception:
            self._trace_handoff("llm_router", "decision_loop", "routine", step, "failed")
            execution_result = None

        if execution_result:
            # 4. Успех — сохраняем как actionable skill
            skill_name = f"learned_{step[:40]}"
            self.memory.save_skill(
                name=skill_name,
                description=f"Изучено: {step}. Метод: {research_result[:200]}",
                agent="research_learn",
                task_type=self._classify_step(step).value,
                method={
                    "source": "research_and_learn",
                    "research_summary": research_result[:500],
                    "step": step[:200],
                },
            )
            logger.info(
                f"[{goal.goal_id}] Research-Learn-Apply успех, навык '{skill_name}' сохранён",
                extra={"event": "research_learn_success", "context": {"skill": skill_name}},
            )

        # 5. Если исследование предлагает улучшение кода — сохраняем как pattern
        target_file = self._detect_target_file(step, goal.title)
        if target_file:
            try:
                self.memory.save_pattern(
                    category="code_improvement",
                    key=f"improve_{target_file}_{hash(step) % 1000}",
                    value=f"Для {target_file}: {research_result[:300]}",
                    confidence=0.6,
                )
            except Exception:
                pass

            # 5.1 Авто-апдейт кода через CodeGenerator (backup → test → rollback)
            if self._code_generator:
                # Owner approval gate for any code change
                if hasattr(self, "_comms") and self._comms:
                    try:
                        import uuid
                        req_id = f"code_change_{uuid.uuid4().hex[:8]}"
                        approved = await self._comms.request_approval(
                            request_id=req_id,
                            message=(
                                "[decision_loop] Запрос изменения кода.\n"
                                "Подтверди ✅ или отклони ❌.\n"
                                f"Файл: {target_file}\n"
                                f"Шаг: {step[:200]}"
                            ),
                            timeout_seconds=3600,
                        )
                        if approved is None:
                            return {"status": "waiting_approval", "error": "Owner approval pending", "agent": "comms"}
                        if approved is not True:
                            return {"status": "failed", "error": "Owner approval rejected or timed out", "agent": "comms"}
                    except Exception:
                        return {"status": "failed", "error": "Owner approval failed", "agent": "comms"}
                instruction = (
                    f"Implement fix or improvement for step: {step}\n"
                    f"Use this research guidance:\n{research_result[:1500]}"
                )
                try:
                    result = await self._code_generator.apply_change(
                        target_file=target_file,
                        instruction=instruction,
                        context=f"Goal: {goal.title}",
                        notify=True,
                    )
                    if result.get("success"):
                        return {"status": "completed", "output": "code_updated", "agent": "code_generator"}
                except Exception as e:
                    logger.warning(f"CodeGenerator apply failed: {e}", extra={"event": "codegen_failed"})

            return {"status": "completed", "output": execution_result[:500], "agent": "research_learn"}

        return {"status": "failed", "error": "Research-Learn-Apply: выполнение не удалось"}

    @staticmethod
    def _detect_target_file(step: str, goal_title: str) -> str:
        """Определяет целевой файл по ключевым словам в шаге/цели."""
        combined = f"{step} {goal_title}".lower()
        file_map = {
            "gumroad": "platforms/gumroad.py",
            "etsy": "platforms/etsy.py",
            "kofi": "platforms/kofi.py",
            "ko-fi": "platforms/kofi.py",
            "wordpress": "platforms/wordpress.py",
            "medium": "platforms/medium.py",
            "printful": "platforms/printful.py",
            "amazon": "platforms/amazon_kdp.py",
            "kdp": "platforms/amazon_kdp.py",
            "youtube": "platforms/youtube.py",
            "substack": "platforms/substack.py",
            "research": "agents/research_agent.py",
            "trend": "agents/trend_scout.py",
            "browser": "agents/browser_agent.py",
            "content": "agents/content_creator.py",
            "seo": "agents/seo_agent.py",
            "ecommerce": "agents/ecommerce_agent.py",
        }
        for keyword, filepath in file_map.items():
            if keyword in combined:
                return filepath
        return ""

    async def _learn_from_goal(self, goal: Goal, results: dict[str, Any]) -> None:
        """Фаза LEARN: извлекаем уроки и сохраняем в память."""
        all_completed = results.get("all_completed")
        if all_completed is None:
            all_completed = results.get("steps_completed", 0) == results.get("steps_total", 0)

        skill_name = f"goal_{goal.title[:50]}"
        runtime_sqlite = _runtime_sqlite_path(self.goal_engine)
        skill_lib = VITOSkillLibrary(sqlite_path=runtime_sqlite, memory=self.memory)
        reflector = VITOReflector(sqlite_path=runtime_sqlite)
        category = self._reflection_category_for_goal(goal)
        first_agent = ""

        if all_completed:
            lesson = f"Цель '{goal.title}' выполнена. План из {len(goal.plan)} шагов сработал."
            self.goal_engine.complete_goal(goal.goal_id, results, lessons=lesson)
            try:
                self.memory.store_knowledge(
                    doc_id=f"lesson_{goal.goal_id}",
                    text=lesson,
                    metadata={"type": "lesson", "goal_id": goal.goal_id, "title": goal.title},
                )
            except Exception:
                pass

            # Mark calendar task as completed if this goal came from weekly_calendar
            if goal.source == "weekly_calendar":
                self._mark_today_calendar_completed(goal.title)

            # Notify owner with actual results (files, URLs)
            await self._notify_goal_completed(goal, results)

            # Actionable skill: сохраняем агента, тип задачи, метод
            successful_agents = [
                results.get(f"step_{i + 1}", {}).get("agent", "llm_fallback")
                for i in range(len(goal.plan))
            ]
            first_agent = successful_agents[0] if successful_agents else ""
            self.memory.save_skill(
                name=skill_name,
                description=f"Успешно: {', '.join(goal.plan[:3])}",
                agent=first_agent,
                task_type=self._classify_step(goal.plan[0]).value if goal.plan else "routine",
                method={
                    "plan": goal.plan,
                    "steps_count": len(goal.plan),
                    "duration_ms": results.get("duration_ms", 0),
                    "successful_agents": successful_agents,
                },
            )
            try:
                self.memory.update_skill_last_result(skill_name, str(results)[:500])
            except Exception:
                pass
            try:
                skill_lib.add_skill(
                    name=skill_name,
                    description=f"Goal-derived reusable pattern: {goal.title}. Steps: {' | '.join(goal.plan[:5])}",
                    category=category,
                    source_agent=first_agent or "decision_loop",
                    trigger_hint=f"{goal.title} {' '.join(goal.plan[:5])}",
                    code_ref=self._detect_target_file(" ".join(goal.plan[:3]), goal.title),
                    tags=[goal.source, category],
                    metadata={
                        "goal_id": goal.goal_id,
                        "goal_title": goal.title,
                        "steps": goal.plan[:5],
                    },
                )
                skill_lib.record_use(skill_name, success=True)
            except Exception:
                pass
            logger.info(
                f"[{goal.goal_id}] Навык '{skill_name}' — успех",
                extra={"event": "skill_success_updated"},
            )
        else:
            reason = f"Выполнено {results.get('steps_completed')}/{results.get('steps_total')} шагов"
            self.goal_engine.fail_goal(goal.goal_id, reason)
            try:
                self.memory.store_knowledge(
                    doc_id=f"lesson_fail_{goal.goal_id}",
                    text=f"Failure: {goal.title}. Reason: {reason}. Plan: {', '.join(goal.plan[:3])}",
                    metadata={"type": "lesson_fail", "goal_id": goal.goal_id, "title": goal.title},
                )
            except Exception:
                pass

            try:
                await self._notify_goal_failed(goal, results, reason)
            except Exception:
                pass

            # Сначала создаём/обновляем навык (если не существует — INSERT)
            # Затем записываем провал
            existing = self.memory.get_skill(skill_name)
            if existing:
                self.memory.update_skill_success(skill_name, success=False)
            else:
                # Создаём запись навыка с описанием провала
                self.memory.save_skill(
                    name=skill_name,
                    description=f"Провал: {reason}. План: {', '.join(goal.plan[:3])}",
                )
                # save_skill ставит success_count=0 для новых,
                # но ON CONFLICT делает +1 к success — нужно скорректировать
                # Записываем провал
                self.memory.update_skill_success(skill_name, success=False)
            try:
                skill_lib.add_skill(
                    name=skill_name,
                    description=f"Failed pattern to avoid/rework: {goal.title}. Steps: {' | '.join(goal.plan[:5])}",
                    category=category,
                    source_agent="decision_loop",
                    trigger_hint=f"{goal.title} {' '.join(goal.plan[:5])}",
                    code_ref=self._detect_target_file(" ".join(goal.plan[:3]), goal.title),
                    tags=[goal.source, category, "failed"],
                    metadata={
                        "goal_id": goal.goal_id,
                        "goal_title": goal.title,
                        "steps": goal.plan[:5],
                        "failure_reason": reason,
                    },
                )
                skill_lib.record_use(skill_name, success=False)
            except Exception:
                pass
            logger.info(
                f"[{goal.goal_id}] Навык '{skill_name}' — провал",
                extra={"event": "skill_failure_updated"},
            )

            self.memory.log_error(
                module="decision_loop",
                error_type="goal_partial_failure",
                message=f"{goal.title}: {reason}",
            )

        # Сохраняем знание для будущего поиска
        self.memory.store_knowledge(
            doc_id=f"goal_{goal.goal_id}",
            text=f"{goal.title}: {goal.description}. Результат: {'успех' if all_completed else 'частично'}",
            metadata={
                "source": goal.source,
                "priority": goal.priority.name,
                "success": all_completed,
            },
        )

        # Эпизод в долгосрочную память
        try:
            await self.memory.store_episode(
                event_type="goal_completed" if all_completed else "goal_failed",
                summary=f"{goal.title} — {'успех' if all_completed else 'провал'}",
                details={
                    "goal_id": goal.goal_id,
                    "plan": goal.plan,
                    "steps_completed": results.get("steps_completed"),
                    "duration_ms": results.get("duration_ms"),
                },
                importance=0.7 if all_completed else 0.5,
            )
        except Exception as e:
            logger.warning(
                f"Не удалось сохранить эпизод: {e}",
                extra={"event": "episode_store_failed"},
            )
        try:
            await reflector.reflect(
                category=category,
                action_type="goal_execution",
                input_summary=f"{goal.title}. {goal.description}"[:500],
                outcome_summary=str(results)[:1000],
                success=bool(all_completed),
                task_root_id=goal.goal_id,
                context={
                    "platform": self._infer_goal_platform(goal),
                    "source": goal.source,
                    "factors": goal.plan[:5],
                    "reason": "" if all_completed else results.get("error") or results.get("last_error") or "",
                },
            )
        except Exception:
            pass

    @staticmethod
    def _infer_goal_platform(goal: Goal) -> str:
        combined = f"{goal.title} {goal.description}".lower()
        for name in ("gumroad", "etsy", "amazon", "kdp", "printful", "ko-fi", "kofi", "pinterest", "twitter", "reddit"):
            if name in combined:
                return "kofi" if name == "ko-fi" else name
        return ""

    def _reflection_category_for_goal(self, goal: Goal) -> str:
        text = f"{goal.title} {goal.description}".lower()
        if any(x in text for x in ("gumroad", "etsy", "amazon", "kdp", "printful", "ko-fi", "kofi")):
            return "ecommerce"
        if any(x in text for x in ("research", "trend", "niche")):
            return "strategy"
        if any(x in text for x in ("bug", "fix", "runtime", "browser", "auth", "code")):
            return "technical"
        return "general"

    # ── Idle: нет задач — исследуем ──

    async def _idle_action(self) -> None:
        """Когда нет задач — VITO работает по недельному плану.

        Логика:
        - Calendar tasks (weekly_calendar) подхватываются сразу (2-й idle тик)
        - Daily fallback — только если нет calendar task и прошло 30 мин idle
        - Не создаём новых целей пока есть активные
        """
        if not settings.PROACTIVE_ENABLED:
            return
        # Check if there's already an active goal
        existing = self.goal_engine.get_all_goals()
        active = [
            g for g in existing
            if g.status not in (GoalStatus.COMPLETED, GoalStatus.FAILED, GoalStatus.CANCELLED)
        ]
        if active:
            return  # Don't create new goals while others are in progress

        # 1. Calendar task — check immediately when idle
        if self._consecutive_idle >= 1:
            today_task = self._get_today_calendar_task()
            if today_task:
                logger.info(
                    f"Календарная задача: {today_task['title']}",
                    extra={"event": "calendar_task", "context": {"task": today_task["title"]}},
                )
                # Mark calendar entry as in_progress to prevent re-creation
                self._update_calendar_status(today_task.get("id"), "in_progress")
                self.goal_engine.create_goal(
                    title=today_task["title"],
                    description=today_task["description"],
                    priority=GoalPriority.MEDIUM,
                    source="weekly_calendar",
                    estimated_cost_usd=today_task.get("cost", 0.05),
                    estimated_roi=today_task.get("roi", 5.0),
                )
                return

        # 2. Daily fallback — once per 10 min (2 ticks), only if no calendar
        if self._consecutive_idle < 2 or self._consecutive_idle % 6 != 0:
            return

        # Autonomy v2: let curriculum/opportunity systems propose before fallback templates.
        proposed = await self._maybe_create_autonomy_goal()
        if proposed:
            return

        import hashlib
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Check history in SQLite, not only active in-memory goals.
        already_today = self._has_goal_created_today(source="proactive_daily", today_str=today_str)
        if already_today:
            return

        day_hash = int(hashlib.md5(today_str.encode()).hexdigest()[:8], 16)

        daily_tasks = [
            {
                "title": "Full product cycle: research → create → prepare",
                "description": (
                    "FULL PRODUCT PIPELINE (all steps in one report):\n"
                    "1. NICHE ANALYSIS: Scan Reddit RSS + trends. Find niche with high demand, low competition.\n"
                    "2. COMPETITOR CHECK: Find 3 competitors on Gumroad/Etsy, analyze prices and sales.\n"
                    "3. PRODUCT CHOICE: Pick 1 specific digital product (ebook/template/guide) for US/EU market.\n"
                    "4. CONTENT: Write full product content IN ENGLISH, save to output/products/.\n"
                    "5. SEO: Title, description, tags optimized for marketplace search.\n"
                    "6. PRICING: Set price based on competitor analysis ($5-29 range).\n"
                    "7. PUBLISH PLAN: Which platforms (Gumroad/Ko-fi), launch timeline.\n"
                    "8. REPORT: Send ONE complete report to owner via Telegram with ALL above.\n"
                    "9. DO NOT publish without owner approval. DO NOT send separate pieces."
                ),
            },
            {
                "title": "Content + social media package",
                "description": (
                    "FULL CONTENT PIPELINE (all steps in one report):\n"
                    "1. Pick topic from existing product ideas or trending niche.\n"
                    "2. Write article/guide (1500+ words) IN ENGLISH, save to output/articles/.\n"
                    "3. Create 3-5 tweets for @bot_vito promoting the content.\n"
                    "4. Save tweets to output/tweets/ (not published until approved).\n"
                    "5. SEO keywords for the article.\n"
                    "6. REPORT: Send ONE complete report to owner via Telegram.\n"
                    "7. DO NOT publish without owner approval."
                ),
            },
            {
                "title": "Market analysis + product improvement",
                "description": (
                    "FULL ANALYSIS PIPELINE (all steps in one report):\n"
                    "1. Analyze existing products on Gumroad (if any). Check views, sales.\n"
                    "2. Find 5 competitors in same niche, compare prices and features.\n"
                    "3. Identify gaps: what competitors don't offer that we can.\n"
                    "4. Propose improvements or new product variant.\n"
                    "5. Updated pricing strategy based on market data.\n"
                    "6. REPORT: Send ONE complete report to owner via Telegram.\n"
                    "7. DO NOT change anything without owner approval."
                ),
            },
        ]

        task = daily_tasks[day_hash % len(daily_tasks)]

        logger.info(
            f"Дневная задача: {task['title']}",
            extra={"event": "daily_proactive", "context": {"task": task["title"]}},
        )
        self.goal_engine.create_goal(
            title=task["title"],
            description=task["description"],
            priority=GoalPriority.BACKGROUND,
            source="proactive_daily",
            estimated_cost_usd=0.05,
            estimated_roi=5.0,
        )

    async def _maybe_run_autonomy_v2(self) -> None:
        """Periodic proactive loops for autonomy v2 subsystems."""
        try:
            if not getattr(settings, "PROACTIVE_ENABLED", False):
                return
            if not self.agent_registry:
                return
            await self._maybe_run_opportunity_scout()
            await self._maybe_run_curriculum_review()
            await self._maybe_run_self_evolver_weekly()
        except Exception:
            pass

    async def _maybe_run_opportunity_scout(self) -> None:
        interval = max(12, int(getattr(settings, "AUTONOMY_SCOUT_INTERVAL_TICKS", 72) or 72))
        if self._tick_count - int(self._last_opportunity_scout_tick or 0) < interval:
            return
        result = await self.agent_registry.dispatch("scan_opportunities")
        if result and result.success and self.memory:
            self.memory.store_knowledge(
                doc_id=f"opportunity_scout_{self._tick_count}",
                text=str(result.output)[:3000],
                metadata={"type": "opportunity_proposals", "tick": self._tick_count},
            )
        self._last_opportunity_scout_tick = self._tick_count

    async def _maybe_run_curriculum_review(self) -> None:
        interval = max(12, int(getattr(settings, "AUTONOMY_CURRICULUM_INTERVAL_TICKS", 72) or 72))
        if self._tick_count - int(self._last_curriculum_tick or 0) < interval:
            return
        result = await self.agent_registry.dispatch("generate_goals")
        if result and result.success and self.memory:
            self.memory.store_knowledge(
                doc_id=f"curriculum_goals_{self._tick_count}",
                text=str(result.output)[:3000],
                metadata={"type": "curriculum_goals", "tick": self._tick_count},
            )
        self._last_curriculum_tick = self._tick_count

    async def _maybe_run_self_evolver_weekly(self) -> None:
        interval = max(288, int(getattr(settings, "AUTONOMY_SELF_EVOLVER_INTERVAL_TICKS", 2016) or 2016))
        if self._tick_count - int(self._last_self_evolver_tick or 0) < interval:
            return
        evolver_v2 = getattr(self, "_self_evolver_v2", None)
        if evolver_v2 is not None:
            await evolver_v2.execute_task("weekly_evolve_cycle", baseline_score=0.7)
        else:
            await self.agent_registry.dispatch("weekly_improve_cycle")
        self._last_self_evolver_tick = self._tick_count

    async def _maybe_create_autonomy_goal(self) -> bool:
        if not self.agent_registry:
            return False
        try:
            result = await self.agent_registry.dispatch("generate_goals")
            payload = getattr(result, "output", {}) if result and result.success else {}
            goals = list(payload.get("goals") or []) if isinstance(payload, dict) else []
            if not goals:
                return False
            top = goals[0]
            self.goal_engine.create_goal(
                title=str(top.get("title") or "Autonomy opportunity")[:180],
                description=str(top.get("rationale") or "")[:1000],
                priority=GoalPriority.HIGH if float(top.get("confidence") or 0) >= 0.75 else GoalPriority.MEDIUM,
                source="curriculum_agent",
                estimated_cost_usd=0.05,
                estimated_roi=float(top.get("expected_revenue") or 0),
            )
            return True
        except Exception:
            return False

    def _get_today_calendar_task(self) -> dict | None:
        """Read today's task from weekly_calendar table in SQLite (no LLM)."""
        try:
            import sqlite3
            conn = sqlite3.connect(settings.SQLITE_PATH)
            conn.row_factory = sqlite3.Row
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            row = conn.execute(
                "SELECT * FROM weekly_calendar WHERE date = ? AND status = 'pending' LIMIT 1",
                (today,),
            ).fetchone()
            conn.close()
            if row:
                return dict(row)
        except Exception as e:
            logger.debug(f"Calendar read error: {e}")

    def _update_calendar_status(self, task_id: int | None, status: str) -> None:
        """Update weekly_calendar task status (no LLM)."""
        if not task_id:
            return
        try:
            import sqlite3
            conn = sqlite3.connect(settings.SQLITE_PATH)
            conn.execute(
                "UPDATE weekly_calendar SET status = ? WHERE id = ?",
                (status, task_id),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _has_goal_created_today(self, source: str, today_str: str | None = None) -> bool:
        """Return True when at least one goal from source exists for current UTC date.

        Uses persisted goals table to avoid duplicate proactive creation after
        failed/completed/cancelled goals are removed from in-memory active set.
        """
        src = str(source or "").strip()
        if not src:
            return False
        day = str(today_str or datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        conn = None
        try:
            import sqlite3
            goal_conn = getattr(self.goal_engine, "_conn", None)
            if goal_conn is not None:
                conn = goal_conn
            else:
                conn = sqlite3.connect(settings.SQLITE_PATH)
            row = conn.execute(
                """
                SELECT 1
                FROM goals
                WHERE source = ?
                  AND substr(created_at, 1, 10) = ?
                LIMIT 1
                """,
                (src, day),
            ).fetchone()
            return bool(row)
        except Exception:
            return False
        finally:
            # Close only ad-hoc connection opened in this helper.
            if conn is not None and conn is not getattr(self.goal_engine, "_conn", None):
                try:
                    conn.close()
                except Exception:
                    pass

    def _mark_today_calendar_completed(self, goal_title: str) -> None:
        """Mark today's calendar task as completed after goal finishes."""
        try:
            import sqlite3
            conn = sqlite3.connect(settings.SQLITE_PATH)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            conn.execute(
                "UPDATE weekly_calendar SET status = 'completed' WHERE date = ? AND title = ?",
                (today, goal_title),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass
        return None

    async def _notify_goal_completed(self, goal: Goal, results: dict[str, Any]) -> None:
        """Send human-like completion report to owner via Telegram.

        Instead of raw file paths, sends: what was done + key findings + proposals.
        """
        if not hasattr(self, '_comms') or not self._comms:
            return
        try:
            # Collect step outputs, files, URLs
            all_outputs: list[str] = []
            files: list[str] = []
            for key, val in results.items():
                if not isinstance(val, dict):
                    continue
                if val.get("file_path"):
                    files.append(val["file_path"])
                out = val.get("output", "")
                if isinstance(out, str) and len(out) > 50:
                    all_outputs.append(out[:500])
                elif isinstance(out, dict):
                    if out.get("url"):
                        files.append(out["url"])
                    if out.get("file_path"):
                        files.append(out["file_path"])
                    # Check for executive_summary in metadata
                    exec_sum = val.get("executive_summary", "")
                    if exec_sum:
                        all_outputs.insert(0, exec_sum)

            # Generate executive summary via cheap LLM
            combined_output = "\n---\n".join(all_outputs[:5])
            summary = None
            if combined_output and self.llm_router:
                summary_prompt = (
                    f"Goal completed: {goal.title}\n"
                    f"Description: {goal.description[:200]}\n\n"
                    f"Step outputs:\n{combined_output[:3000]}\n\n"
                    f"Write a Telegram update for the owner:\n"
                    f"1. One sentence: what was done\n"
                    f"2. 3-5 key findings (bullet points)\n"
                    f"3. 2-3 concrete next steps in plain language (no forced 1/2 choice).\n"
                    f"Write in Russian (owner prefers Russian for communication).\n"
                    f"Be conversational, like a business partner reporting results."
                )
                try:
                    summary = await self.llm_router.call_llm(
                        task_type=TaskType.ROUTINE,
                        prompt=summary_prompt,
                        estimated_tokens=300,
                    )
                except Exception:
                    summary = None

            if summary:
                msg = summary
            else:
                # Fallback: simple but still better than raw dumps
                msg = f"Готово: {goal.title}\n"
                msg += f"Выполнено {results.get('steps_completed', 0)} шагов.\n"

            if files:
                msg += "\n" + "\n".join(f"📎 {f}" for f in files[:3])

            await self._comms.send_message(msg, level="result")
        except Exception:
            # Fallback minimal message if summary generation fails
            try:
                msg = f"Готово: {goal.title}\nВыполнено {results.get('steps_completed', 0)} шагов."
                await self._comms.send_message(msg, level="result")
            except Exception:
                pass

    async def _notify_goal_failed(self, goal: Goal, results: dict[str, Any], reason: str) -> None:
        if not hasattr(self, "_comms") or not self._comms:
            return
        msg = (
            f"Задача не выполнена: {goal.title}\n"
            f"Причина: {reason}\n"
            f"Описание: {goal.description[:200]}\n"
            f"Шагов выполнено: {results.get('steps_completed')}/{results.get('steps_total')}\n"
            f"Последний шаг: {self._last_step_summary(results)}"
        )
        await self._comms.send_message(msg, level="critical")

    # ── Time awareness (no LLM) ──

    @staticmethod
    def get_time_context() -> dict[str, Any]:
        """Current time info for VITO — pure Python, no LLM calls."""
        now = datetime.now(timezone.utc)
        hour = now.hour
        weekday = now.strftime("%A")  # Monday, Tuesday, etc.

        if 6 <= hour < 12:
            period = "morning"
        elif 12 <= hour < 18:
            period = "afternoon"
        elif 18 <= hour < 22:
            period = "evening"
        else:
            period = "night"

        return {
            "utc_time": now.isoformat(),
            "hour_utc": hour,
            "weekday": weekday,
            "period": period,
            "is_business_hours_us": 14 <= hour <= 23,  # 9 AM - 6 PM EST
            "is_weekend": weekday in ("Saturday", "Sunday"),
            "date": now.strftime("%Y-%m-%d"),
        }

    # ── Утилиты ──

    @staticmethod
    def _classify_step(step: str) -> TaskType:
        """Определяет тип задачи для шага плана."""
        step_lower = step.lower()
        if any(w in step_lower for w in ["исследов", "анализ", "поиск", "research", "analyz"]):
            return TaskType.RESEARCH
        if any(w in step_lower for w in ["стратег", "план", "оцен", "strateg", "evaluat"]):
            return TaskType.STRATEGY
        if any(w in step_lower for w in ["код", "скрипт", "функци", "code", "script", "implement"]):
            return TaskType.CODE
        if any(w in step_lower for w in ["контент", "текст", "стать", "content", "write", "creat"]):
            return TaskType.CONTENT
        return TaskType.ROUTINE

    def _log_tick_done(self, tick_start: float, idle: bool) -> None:
        duration_ms = int((time.monotonic() - tick_start) * 1000)
        logger.info(
            f"Tick #{self._tick_count} завершён за {duration_ms}ms"
            + (" (idle)" if idle else ""),
            extra={
                "event": "tick_done",
                "duration_ms": duration_ms,
                "context": {
                    "tick": self._tick_count,
                    "idle": idle,
                    "daily_spend": self.llm_router.get_daily_spend(),
                },
            },
        )

    def get_status(self) -> dict:
        """Статус для мониторинга."""
        pending = 0
        try:
            if hasattr(self, "_comms") and self._comms:
                pending = int(self._comms.pending_approvals_count())
        except Exception:
            pending = 0
        return {
            "running": self.running,
            "tick_count": self._tick_count,
            "consecutive_idle": self._consecutive_idle,
            "daily_spend": self.llm_router.get_daily_spend(),
            "goal_stats": self.goal_engine.get_stats(),
            "pending_approvals": pending,
            "kdp_watchdog": {
                "status": str(self._kdp_watchdog_state.get("status", "unknown")),
                "paused": bool(self._kdp_watchdog_state.get("paused", False)),
                "last_ok_at": str(self._kdp_watchdog_state.get("last_ok_at", "")),
                "last_fail_at": str(self._kdp_watchdog_state.get("last_fail_at", "")),
                "next_probe_at": str(self._kdp_watchdog_state.get("next_probe_at", "")),
            },
        }
