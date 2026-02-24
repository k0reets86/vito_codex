"""Goal Engine — управление целями по циклу Goal → Plan → Execute → Learn.

Каждое действие VITO проходит через этот цикл. Динамическая приоритизация:
  - Срочные задачи (одобрение ждёт >30 мин) → первая очередь
  - Высокий ROI-потенциал → приоритет над рутиной
  - Финансовый контроллер проверяет лимиты перед платным действием
  - Quality Judge оценивает результат перед публикацией
"""

import json
import sqlite3
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
    def __init__(self, sqlite_path: str = ""):
        self._goals: dict[str, Goal] = {}
        self._active_goal: Optional[str] = None
        self._sqlite_path = sqlite_path or settings.SQLITE_PATH
        self._conn: Optional[sqlite3.Connection] = None
        self._init_goals_db()
        self._load_goals()
        logger.info(
            f"GoalEngine инициализирован, загружено {len(self._goals)} целей",
            extra={"event": "init", "context": {"loaded_goals": len(self._goals)}},
        )

    def _init_goals_db(self) -> None:
        """Создаёт таблицу goals в SQLite."""
        self._conn = sqlite3.connect(self._sqlite_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS goals (
                goal_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                priority INTEGER DEFAULT 3,
                status TEXT DEFAULT 'pending',
                source TEXT DEFAULT 'system',
                estimated_cost_usd REAL DEFAULT 0,
                estimated_roi REAL DEFAULT 0,
                plan TEXT DEFAULT '[]',
                results TEXT DEFAULT '{}',
                lessons_learned TEXT DEFAULT '',
                parent_goal_id TEXT,
                created_at TEXT,
                started_at TEXT,
                completed_at TEXT
            )
        """)
        self._conn.commit()

    def _load_goals(self) -> None:
        """Загружает non-terminal цели из SQLite при старте."""
        try:
            self._goals = {}
            rows = self._conn.execute(
                "SELECT * FROM goals WHERE status NOT IN ('completed', 'failed', 'cancelled')"
            ).fetchall()
            for row in rows:
                row_dict = dict(row)
                goal = Goal(
                    goal_id=row_dict["goal_id"],
                    title=row_dict["title"],
                    description=row_dict["description"] or "",
                    priority=GoalPriority(row_dict["priority"]),
                    status=GoalStatus(row_dict["status"]),
                    source=row_dict["source"] or "system",
                    estimated_cost_usd=row_dict["estimated_cost_usd"] or 0.0,
                    estimated_roi=row_dict["estimated_roi"] or 0.0,
                    plan=json.loads(row_dict["plan"] or "[]"),
                    results=json.loads(row_dict["results"] or "{}"),
                    lessons_learned=row_dict["lessons_learned"] or "",
                    parent_goal_id=row_dict["parent_goal_id"],
                )
                if row_dict["created_at"]:
                    try:
                        goal.created_at = datetime.fromisoformat(row_dict["created_at"])
                    except (ValueError, TypeError):
                        pass
                if row_dict["started_at"]:
                    try:
                        goal.started_at = datetime.fromisoformat(row_dict["started_at"])
                    except (ValueError, TypeError):
                        pass
                if row_dict["completed_at"]:
                    try:
                        goal.completed_at = datetime.fromisoformat(row_dict["completed_at"])
                    except (ValueError, TypeError):
                        pass
                self._goals[goal.goal_id] = goal
            if rows:
                logger.info(
                    f"Загружено {len(rows)} целей из SQLite",
                    extra={"event": "goals_loaded", "context": {"count": len(rows)}},
                )
        except Exception as e:
            logger.error(f"Ошибка загрузки целей: {e}", extra={"event": "goals_load_error"}, exc_info=True)

    def reload_goals(self) -> None:
        """Перезагружает цели из SQLite (non-terminal)."""
        self._load_goals()

    def _persist_goal(self, goal: Goal) -> None:
        """Сохраняет одну цель в SQLite (INSERT OR REPLACE)."""
        try:
            self._conn.execute(
                """INSERT OR REPLACE INTO goals
                   (goal_id, title, description, priority, status, source,
                    estimated_cost_usd, estimated_roi, plan, results,
                    lessons_learned, parent_goal_id, created_at, started_at, completed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    goal.goal_id,
                    goal.title,
                    goal.description,
                    goal.priority.value,
                    goal.status.value,
                    goal.source,
                    goal.estimated_cost_usd,
                    goal.estimated_roi,
                    json.dumps(goal.plan, ensure_ascii=False),
                    json.dumps(goal.results, ensure_ascii=False),
                    goal.lessons_learned,
                    goal.parent_goal_id,
                    goal.created_at.isoformat() if goal.created_at else None,
                    goal.started_at.isoformat() if goal.started_at else None,
                    goal.completed_at.isoformat() if goal.completed_at else None,
                ),
            )
            self._conn.commit()
        except Exception as e:
            logger.error(f"Ошибка сохранения цели {goal.goal_id}: {e}", extra={"event": "goal_persist_error"}, exc_info=True)

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
        # Avoid duplicate active goals with identical title
        try:
            for g in self._goals.values():
                if g.title == title and g.status in {
                    GoalStatus.PENDING,
                    GoalStatus.EXECUTING,
                    GoalStatus.WAITING_APPROVAL,
                    GoalStatus.PLANNING,
                }:
                    logger.info(
                        f"Цель уже существует (active): [{g.goal_id}] {title}",
                        extra={"event": "goal_duplicate_skipped", "context": {"goal_id": g.goal_id}},
                    )
                    return g
        except Exception:
            pass
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
        self._persist_goal(goal)
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
        try:
            from modules.data_lake import DataLake
            DataLake().record(agent="goal_engine", task_type="goal_created", status="success",
                              output={"goal_id": goal.goal_id, "title": title, "priority": priority.name})
        except Exception:
            pass
        return goal

    def plan_goal(self, goal_id: str, steps: list[str]) -> None:
        """Фаза PLAN: составляет план выполнения."""
        goal = self._goals.get(goal_id)
        if not goal:
            logger.error(f"Цель не найдена: {goal_id}", extra={"event": "goal_not_found"})
            return

        goal.plan = steps
        goal.status = GoalStatus.PLANNING
        self._persist_goal(goal)
        logger.info(
            f"План составлен для [{goal_id}]: {len(steps)} шагов",
            extra={
                "event": "goal_planned",
                "context": {"goal_id": goal_id, "steps_count": len(steps), "steps": steps},
            },
        )
        try:
            from modules.data_lake import DataLake
            DataLake().record(agent="goal_engine", task_type="goal_planned", status="success",
                              output={"goal_id": goal_id, "steps": steps[:10]})
        except Exception:
            pass

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
            self._persist_goal(goal)
            return False

        goal.status = GoalStatus.EXECUTING
        goal.started_at = datetime.now(timezone.utc)
        self._active_goal = goal_id
        self._persist_goal(goal)
        logger.info(
            f"Выполнение начато: [{goal_id}] {goal.title}",
            extra={"event": "goal_execution_started", "context": {"goal_id": goal_id}},
        )
        try:
            from modules.data_lake import DataLake
            DataLake().record(agent="goal_engine", task_type="goal_execution_started", status="success",
                              output={"goal_id": goal_id, "title": goal.title})
        except Exception:
            pass
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

        self._persist_goal(goal)
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
        try:
            from modules.data_lake import DataLake
            DataLake().record(agent="goal_engine", task_type="goal_completed", status="success",
                              output={"goal_id": goal_id, "title": goal.title, "lessons": lessons[:200]})
        except Exception:
            pass

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

        self._persist_goal(goal)
        logger.warning(
            f"Цель провалена: [{goal_id}] {reason}",
            extra={"event": "goal_failed", "context": {"goal_id": goal_id, "reason": reason}},
        )
        try:
            from modules.data_lake import DataLake
            DataLake().record(agent="goal_engine", task_type="goal_failed", status="failed",
                              output={"goal_id": goal_id, "title": goal.title}, error=reason)
        except Exception:
            pass

    def delete_goal(self, goal_id: str) -> bool:
        """Удаляет цель из памяти и SQLite."""
        try:
            if goal_id in self._goals:
                if self._active_goal == goal_id:
                    self._active_goal = None
                self._goals.pop(goal_id, None)
            if self._conn:
                self._conn.execute("DELETE FROM goals WHERE goal_id = ?", (goal_id,))
                self._conn.commit()
            logger.info(
                f"Цель удалена: [{goal_id}]",
                extra={"event": "goal_deleted", "context": {"goal_id": goal_id}},
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления цели {goal_id}: {e}", extra={"event": "goal_delete_error"}, exc_info=True)
            return False

    def clear_all_goals(self) -> int:
        """Удаляет все цели (полная очистка очереди)."""
        try:
            count = len(self._goals)
            self._goals = {}
            self._active_goal = None
            if self._conn:
                self._conn.execute("DELETE FROM goals")
                self._conn.commit()
            logger.warning("Все цели удалены", extra={"event": "goals_cleared", "context": {"count": count}})
            return count
        except Exception as e:
            logger.error(f"Ошибка очистки целей: {e}", extra={"event": "goals_clear_error"}, exc_info=True)
            return 0

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

    def get_waiting_approvals(self) -> list[Goal]:
        """Список целей, ожидающих одобрения владельца."""
        return [g for g in self._goals.values() if g.status == GoalStatus.WAITING_APPROVAL]
