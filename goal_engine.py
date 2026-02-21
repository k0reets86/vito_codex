"""Goal Engine — управление целями по циклу Goal → Plan → Execute → Learn.

Каждое действие VITO проходит через этот цикл. Динамическая приоритизация:
  - Срочные задачи (одобрение ждёт >30 мин) → первая очередь
  - Высокий ROI-потенциал → приоритет над рутиной
  - Финансовый контроллер проверяет лимиты перед платным действием
  - Quality Judge оценивает результат перед публикацией
"""

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from config.logger import get_logger
from config.settings import settings

logger = get_logger("goal_engine", agent="goal_engine")


class GoalStatus(Enum):
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GoalPriority(Enum):
    CRITICAL = 1   # одобрение ждёт >30 мин, критические ошибки
    HIGH = 2       # высокий ROI, срочные задачи от владельца
    MEDIUM = 3     # обычная работа: создание контента, публикация
    LOW = 4        # исследования, обновление знаний, оптимизация
    BACKGROUND = 5 # мониторинг трендов, ночная консолидация


@dataclass
class Goal:
    goal_id: str
    title: str
    description: str
    priority: GoalPriority = GoalPriority.MEDIUM
    status: GoalStatus = GoalStatus.PENDING
    source: str = "system"  # system / owner / trend_scout / self_healer
    estimated_cost_usd: float = 0.0
    estimated_roi: float = 0.0
    plan: list[str] = field(default_factory=list)
    results: dict[str, Any] = field(default_factory=dict)
    lessons_learned: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    parent_goal_id: Optional[str] = None


class GoalEngine:
    def __init__(self):
        self._goals: dict[str, Goal] = {}
        self._active_goal: Optional[str] = None
        logger.info("GoalEngine инициализирован", extra={"event": "init"})

    def create_goal(
        self,
        title: str,
        description: str,
        priority: GoalPriority = GoalPriority.MEDIUM,
        source: str = "system",
        estimated_cost_usd: float = 0.0,
        estimated_roi: float = 0.0,
        parent_goal_id: Optional[str] = None,
    ) -> Goal:
        """Создаёт новую цель."""
        goal = Goal(
            goal_id=str(uuid.uuid4())[:8],
            title=title,
            description=description,
            priority=priority,
            source=source,
            estimated_cost_usd=estimated_cost_usd,
            estimated_roi=estimated_roi,
            parent_goal_id=parent_goal_id,
        )
        self._goals[goal.goal_id] = goal
        logger.info(
            f"Цель создана: [{goal.goal_id}] {title}",
            extra={
                "event": "goal_created",
                "context": {
                    "goal_id": goal.goal_id,
                    "priority": priority.name,
                    "source": source,
                    "estimated_cost": estimated_cost_usd,
                },
            },
        )
        return goal

    def plan_goal(self, goal_id: str, steps: list[str]) -> None:
        """Фаза PLAN: составляет план выполнения."""
        goal = self._goals.get(goal_id)
        if not goal:
            logger.error(f"Цель не найдена: {goal_id}", extra={"event": "goal_not_found"})
            return

        goal.plan = steps
        goal.status = GoalStatus.PLANNING
        logger.info(
            f"План составлен для [{goal_id}]: {len(steps)} шагов",
            extra={
                "event": "goal_planned",
                "context": {"goal_id": goal_id, "steps_count": len(steps), "steps": steps},
            },
        )

    def start_execution(self, goal_id: str) -> bool:
        """Фаза EXECUTE: начинает выполнение цели."""
        goal = self._goals.get(goal_id)
        if not goal:
            logger.error(f"Цель не найдена: {goal_id}", extra={"event": "goal_not_found"})
            return False

        if goal.estimated_cost_usd > settings.DAILY_LIMIT_USD:
            logger.warning(
                f"Цель [{goal_id}] превышает дневной лимит: ${goal.estimated_cost_usd:.2f}",
                extra={
                    "event": "goal_over_budget",
                    "context": {"goal_id": goal_id, "cost": goal.estimated_cost_usd},
                },
            )
            goal.status = GoalStatus.WAITING_APPROVAL
            return False

        goal.status = GoalStatus.EXECUTING
        goal.started_at = datetime.now(timezone.utc)
        self._active_goal = goal_id
        logger.info(
            f"Выполнение начато: [{goal_id}] {goal.title}",
            extra={"event": "goal_execution_started", "context": {"goal_id": goal_id}},
        )
        return True

    def complete_goal(self, goal_id: str, results: dict[str, Any], lessons: str = "") -> None:
        """Фаза LEARN: завершает цель и сохраняет уроки."""
        goal = self._goals.get(goal_id)
        if not goal:
            logger.error(f"Цель не найдена: {goal_id}", extra={"event": "goal_not_found"})
            return

        goal.status = GoalStatus.COMPLETED
        goal.completed_at = datetime.now(timezone.utc)
        goal.results = results
        goal.lessons_learned = lessons

        duration = None
        if goal.started_at:
            duration = (goal.completed_at - goal.started_at).total_seconds()

        if self._active_goal == goal_id:
            self._active_goal = None

        logger.info(
            f"Цель завершена: [{goal_id}] {goal.title}",
            extra={
                "event": "goal_completed",
                "context": {
                    "goal_id": goal_id,
                    "duration_seconds": duration,
                    "lessons": lessons[:200] if lessons else "",
                },
            },
        )

    def fail_goal(self, goal_id: str, reason: str) -> None:
        """Отмечает цель как проваленную."""
        goal = self._goals.get(goal_id)
        if not goal:
            return

        goal.status = GoalStatus.FAILED
        goal.completed_at = datetime.now(timezone.utc)
        goal.results = {"failure_reason": reason}

        if self._active_goal == goal_id:
            self._active_goal = None

        logger.warning(
            f"Цель провалена: [{goal_id}] {reason}",
            extra={"event": "goal_failed", "context": {"goal_id": goal_id, "reason": reason}},
        )

    def get_next_goal(self) -> Optional[Goal]:
        """Выбирает следующую цель по приоритету (динамическая приоритизация).

        Порядок:
        1. Ожидающие одобрения > 30 минут → CRITICAL
        2. По приоритету (1 → 5)
        3. При равном приоритете — по ROI (выше лучше)
        """
        pending = [g for g in self._goals.values() if g.status == GoalStatus.PENDING]
        if not pending:
            return None

        now = datetime.now(timezone.utc)

        # Эскалация: ожидание одобрения > 30 мин
        for g in self._goals.values():
            if g.status == GoalStatus.WAITING_APPROVAL:
                wait_minutes = (now - g.created_at).total_seconds() / 60
                if wait_minutes > 30:
                    g.priority = GoalPriority.CRITICAL
                    logger.info(
                        f"Эскалация: [{g.goal_id}] ожидает одобрения {wait_minutes:.0f} мин",
                        extra={"event": "goal_escalated", "context": {"goal_id": g.goal_id}},
                    )

        pending.sort(key=lambda g: (g.priority.value, -g.estimated_roi))
        return pending[0]

    def get_all_goals(self, status: Optional[GoalStatus] = None) -> list[Goal]:
        goals = list(self._goals.values())
        if status:
            goals = [g for g in goals if g.status == status]
        return sorted(goals, key=lambda g: g.created_at, reverse=True)

    def get_stats(self) -> dict:
        """Статистика целей для утреннего отчёта."""
        all_goals = list(self._goals.values())
        completed = [g for g in all_goals if g.status == GoalStatus.COMPLETED]
        failed = [g for g in all_goals if g.status == GoalStatus.FAILED]

        return {
            "total": len(all_goals),
            "pending": len([g for g in all_goals if g.status == GoalStatus.PENDING]),
            "executing": len([g for g in all_goals if g.status == GoalStatus.EXECUTING]),
            "completed": len(completed),
            "failed": len(failed),
            "success_rate": len(completed) / max(len(completed) + len(failed), 1),
            "total_estimated_cost": sum(g.estimated_cost_usd for g in all_goals),
        }
