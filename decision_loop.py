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
import time
from datetime import datetime, timezone
from typing import Any, Optional

from config.logger import get_logger
from config.settings import settings
from goal_engine import Goal, GoalEngine, GoalPriority, GoalStatus
from llm_router import LLMRouter, TaskType
from memory.memory_manager import MemoryManager

TICK_INTERVAL = 300  # 5 минут
STEP_TIMEOUT = 60    # секунд на один шаг
STEP_MAX_RETRIES = 3 # попыток на один шаг

logger = get_logger("decision_loop", agent="decision_loop")


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
        self.running = False
        self._tick_count = 0
        self._consecutive_idle = 0
        logger.info("DecisionLoop инициализирован", extra={"event": "init"})

    def set_self_healer(self, self_healer) -> None:
        """Устанавливает SelfHealer для самолечения."""
        self.self_healer = self_healer

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
                if self.self_healer:
                    try:
                        await self.self_healer.handle_error(
                            "decision_loop", e, {"tick": self._tick_count}
                        )
                    except Exception:
                        pass
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

        # 1. Проверка финансового лимита
        if not self.llm_router.check_daily_limit():
            logger.warning(
                "Дневной лимит исчерпан — только бесплатные операции",
                extra={"event": "budget_exhausted"},
            )

        # 2. Выбор следующей цели
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

    # ── Goal → Plan → Execute → Learn ──

    async def _process_goal(self, goal: Goal) -> None:
        """Проводит цель через полный цикл."""
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
        plan = await self._plan_goal(goal)
        if not plan:
            self.goal_engine.fail_goal(goal.goal_id, "Не удалось составить план")
            return

        self.goal_engine.plan_goal(goal.goal_id, plan)

        # EXECUTE
        if not self.goal_engine.start_execution(goal.goal_id):
            # Цель ушла в WAITING_APPROVAL — ждём одобрения владельца
            logger.info(
                f"[{goal.goal_id}] ожидает одобрения владельца",
                extra={"event": "goal_awaiting_approval"},
            )
            return

        results = await self._execute_goal(goal)

        # LEARN
        await self._learn_from_goal(goal, results)

    async def _plan_goal(self, goal: Goal) -> list[str]:
        """Фаза PLAN: генерирует план выполнения через LLM."""
        # Проверяем есть ли похожий опыт в памяти
        similar = self.memory.search_knowledge(
            f"{goal.title} {goal.description}", n_results=3
        )
        context_from_memory = ""
        if similar:
            context_from_memory = "Релевантный опыт:\n" + "\n".join(
                f"- {doc['text'][:200]}" for doc in similar
            )

        prompt = (
            f"Составь план выполнения задачи для автономного агента VITO.\n\n"
            f"Задача: {goal.title}\n"
            f"Описание: {goal.description}\n"
            f"Бюджет: ${goal.estimated_cost_usd:.2f}\n"
            f"{context_from_memory}\n\n"
            f"Верни план в виде пронумерованного списка шагов (3-7 шагов). "
            f"Только шаги, без пояснений."
        )

        response = await self.llm_router.call_llm(
            task_type=TaskType.ROUTINE,
            prompt=prompt,
            estimated_tokens=1000,
        )

        if not response:
            return []

        steps = [
            line.strip().lstrip("0123456789.)- ")
            for line in response.strip().split("\n")
            if line.strip() and not line.strip().startswith("#")
        ]
        return steps[:7]

    async def _execute_goal(self, goal: Goal) -> dict[str, Any]:
        """Фаза EXECUTE: выполняет план пошагово."""
        results: dict[str, Any] = {"steps_completed": 0, "steps_total": len(goal.plan)}
        exec_start = time.monotonic()

        for i, step in enumerate(goal.plan):
            logger.info(
                f"[{goal.goal_id}] Шаг {i + 1}/{len(goal.plan)}: {step}",
                extra={
                    "event": "step_executing",
                    "context": {"goal_id": goal.goal_id, "step": i + 1, "action": step},
                },
            )

            step_result = await self._execute_step_with_retry(goal, step, i + 1)
            results[f"step_{i + 1}"] = step_result
            results["steps_completed"] = i + 1

            if step_result.get("status") == "failed":
                logger.warning(
                    f"[{goal.goal_id}] Шаг {i + 1} провалился после {STEP_MAX_RETRIES} попыток: {step_result.get('error')}",
                    extra={"event": "step_failed", "context": {"goal_id": goal.goal_id, "step": i + 1}},
                )
                break

        duration_ms = int((time.monotonic() - exec_start) * 1000)
        results["duration_ms"] = duration_ms

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

    async def _execute_step_with_retry(self, goal: Goal, step: str, step_num: int) -> dict[str, Any]:
        """Обёртка: retry до STEP_MAX_RETRIES раз с таймаутом STEP_TIMEOUT."""
        last_result: dict[str, Any] = {"status": "failed", "error": "no attempts made"}

        for attempt in range(1, STEP_MAX_RETRIES + 1):
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

            if last_result.get("status") != "failed":
                return last_result

            if attempt < STEP_MAX_RETRIES:
                logger.info(
                    f"[{goal.goal_id}] Шаг {step_num} retry {attempt + 1}/{STEP_MAX_RETRIES}",
                    extra={"event": "step_retry", "context": {"goal_id": goal.goal_id, "step": step_num, "attempt": attempt + 1}},
                )

        return last_result

    async def _execute_step(self, goal: Goal, step: str) -> dict[str, Any]:
        """Выполняет один шаг плана. Навык → AgentRegistry → LLM fallback."""
        try:
            # Проверяем навыки в памяти
            skills = self.memory.search_skills(step) if hasattr(self.memory, 'search_skills') else []
            if skills:
                logger.debug(
                    f"Найден навык: {skills[0]['name']}",
                    extra={"event": "skill_found", "context": {"skill": skills[0]["name"]}},
                )

            # Попытка диспатча через реестр агентов
            if self.agent_registry:
                try:
                    result = await self.agent_registry.dispatch(
                        step, step=step, goal_title=goal.title
                    )
                    if result and result.success:
                        output = result.output
                        if isinstance(output, str):
                            output = output[:500]
                        return {"status": "completed", "output": output, "agent": "registry"}
                except Exception as e:
                    logger.debug(
                        f"Registry dispatch failed, falling back to LLM: {e}",
                        extra={"event": "registry_fallback"},
                    )

            # Fallback: прямой вызов LLM
            task_type = self._classify_step(step)

            response = await self.llm_router.call_llm(
                task_type=task_type,
                prompt=(
                    f"Ты VITO — автономный агент. Выполни этот шаг:\n"
                    f"Контекст цели: {goal.title}\n"
                    f"Шаг: {step}\n"
                    f"Дай конкретный результат выполнения."
                ),
                estimated_tokens=1500,
            )

            if response:
                return {"status": "completed", "output": response[:500]}
            return {"status": "failed", "error": "LLM не вернул ответ"}

        except Exception as e:
            if self.self_healer:
                try:
                    await self.self_healer.handle_error(
                        "decision_loop", e,
                        {"step": step, "goal": goal.title},
                    )
                except Exception:
                    pass
            return {"status": "failed", "error": str(e)}

    async def _learn_from_goal(self, goal: Goal, results: dict[str, Any]) -> None:
        """Фаза LEARN: извлекаем уроки и сохраняем в память."""
        all_completed = results.get("steps_completed", 0) == results.get("steps_total", 0)

        if all_completed:
            lesson = f"Цель '{goal.title}' выполнена. План из {len(goal.plan)} шагов сработал."
            self.goal_engine.complete_goal(goal.goal_id, results, lessons=lesson)

            # Сохраняем навык
            self.memory.save_skill(
                name=f"goal_{goal.title[:50]}",
                description=f"Успешно: {', '.join(goal.plan[:3])}",
            )
        else:
            reason = f"Выполнено {results.get('steps_completed')}/{results.get('steps_total')} шагов"
            self.goal_engine.fail_goal(goal.goal_id, reason)

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

    # ── Idle: нет задач — исследуем ──

    async def _idle_action(self) -> None:
        """Когда нет задач — VITO не простаивает."""
        if self._consecutive_idle <= 1:
            logger.debug("Нет задач — ожидание", extra={"event": "idle"})
            return

        # Каждые 3 idle-тика (15 мин) создаём исследовательскую задачу
        if self._consecutive_idle % 3 == 0:
            logger.info(
                "Простой — создаю исследовательскую задачу",
                extra={"event": "idle_research"},
            )
            self.goal_engine.create_goal(
                title="Исследование новых ниш",
                description="Поиск перспективных ниш для цифровых продуктов на основе текущих трендов",
                priority=GoalPriority.BACKGROUND,
                source="decision_loop",
                estimated_cost_usd=0.05,
                estimated_roi=5.0,
            )

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
        return {
            "running": self.running,
            "tick_count": self._tick_count,
            "consecutive_idle": self._consecutive_idle,
            "daily_spend": self.llm_router.get_daily_spend(),
            "goal_stats": self.goal_engine.get_stats(),
        }
