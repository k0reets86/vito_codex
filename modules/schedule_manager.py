"""ScheduleManager — persistent scheduling for reminders and reports."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Iterable
import re

from config.settings import settings


@dataclass
class ScheduledTask:
    id: int
    title: str
    action: str
    schedule_type: str  # once|daily|weekly
    time_of_day: Optional[str]
    weekday: Optional[int]
    run_at: Optional[str]
    next_run: Optional[str]
    last_run: Optional[str]
    status: str


class ScheduleManager:
    def __init__(self, sqlite_path: Optional[str] = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.sqlite_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduled_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                action TEXT NOT NULL,
                schedule_type TEXT NOT NULL,
                time_of_day TEXT,
                weekday INTEGER,
                run_at TEXT,
                next_run TEXT,
                last_run TEXT,
                status TEXT DEFAULT 'active',
                run_lock_owner TEXT DEFAULT '',
                run_lock_until TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        cols = {r[1] for r in conn.execute("PRAGMA table_info(scheduled_tasks)").fetchall()}
        if "run_lock_owner" not in cols:
            conn.execute("ALTER TABLE scheduled_tasks ADD COLUMN run_lock_owner TEXT DEFAULT ''")
        if "run_lock_until" not in cols:
            conn.execute("ALTER TABLE scheduled_tasks ADD COLUMN run_lock_until TEXT DEFAULT ''")
        conn.commit()
        conn.close()

    def _compute_next_run(
        self, schedule_type: str, time_of_day: Optional[str], weekday: Optional[int], run_at: Optional[str]
    ) -> Optional[str]:
        now = datetime.now(timezone.utc)
        if schedule_type == "once" and run_at:
            return run_at
        if schedule_type == "daily" and time_of_day:
            hour, minute = map(int, time_of_day.split(":"))
            candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate <= now:
                candidate += timedelta(days=1)
            return candidate.isoformat()
        if schedule_type == "weekly" and time_of_day and weekday is not None:
            hour, minute = map(int, time_of_day.split(":"))
            candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            days_ahead = (weekday - candidate.weekday()) % 7
            if days_ahead == 0 and candidate <= now:
                days_ahead = 7
            candidate += timedelta(days=days_ahead)
            return candidate.isoformat()
        return None

    def add_task(
        self,
        title: str,
        action: str,
        schedule_type: str,
        time_of_day: Optional[str] = None,
        weekday: Optional[int] = None,
        run_at: Optional[str] = None,
    ) -> int:
        next_run = self._compute_next_run(schedule_type, time_of_day, weekday, run_at)
        conn = sqlite3.connect(self.sqlite_path)
        cur = conn.execute(
            """
            INSERT INTO scheduled_tasks (title, action, schedule_type, time_of_day, weekday, run_at, next_run)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (title, action, schedule_type, time_of_day, weekday, run_at, next_run),
        )
        conn.commit()
        task_id = int(cur.lastrowid)
        conn.close()
        return task_id

    def due_tasks(self) -> list[ScheduledTask]:
        """Legacy non-locking fetch of due tasks. Prefer acquire_due_tasks for runtime."""
        now = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(self.sqlite_path)
        rows = conn.execute(
            """
            SELECT id, title, action, schedule_type, time_of_day, weekday, run_at, next_run, last_run, status
            FROM scheduled_tasks
            WHERE status = 'active' AND next_run IS NOT NULL AND next_run <= ?
            """,
            (now,),
        ).fetchall()
        conn.close()
        return [
            ScheduledTask(*row) for row in rows
        ]

    def acquire_due_tasks(self, owner: str, limit: int = 20, lock_minutes: int = 10) -> list[ScheduledTask]:
        """Atomically claim due tasks to prevent duplicate execution across processes."""
        owner = str(owner or "").strip()[:120] or "worker"
        max_tasks = max(1, int(limit or 20))
        lease_minutes = max(1, int(lock_minutes or 10))
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        lock_until = (now_dt + timedelta(minutes=lease_minutes)).isoformat()

        conn = sqlite3.connect(self.sqlite_path, isolation_level=None)
        try:
            conn.execute("BEGIN IMMEDIATE")
            # Release stale leases first.
            conn.execute(
                """
                UPDATE scheduled_tasks
                SET status = 'active', run_lock_owner = '', run_lock_until = ''
                WHERE status = 'running' AND run_lock_until IS NOT NULL AND run_lock_until != '' AND run_lock_until <= ?
                """,
                (now,),
            )
            candidates = conn.execute(
                """
                SELECT id
                FROM scheduled_tasks
                WHERE status = 'active' AND next_run IS NOT NULL AND next_run <= ?
                ORDER BY next_run ASC, id ASC
                LIMIT ?
                """,
                (now, max_tasks),
            ).fetchall()
            claimed_ids: list[int] = []
            for row in candidates:
                task_id = int(row[0])
                cur = conn.execute(
                    """
                    UPDATE scheduled_tasks
                    SET status = 'running', run_lock_owner = ?, run_lock_until = ?
                    WHERE id = ? AND status = 'active'
                    """,
                    (owner, lock_until, task_id),
                )
                if int(cur.rowcount or 0) == 1:
                    claimed_ids.append(task_id)

            tasks: list[ScheduledTask] = []
            if claimed_ids:
                placeholders = ",".join("?" for _ in claimed_ids)
                rows = conn.execute(
                    f"""
                    SELECT id, title, action, schedule_type, time_of_day, weekday, run_at, next_run, last_run, status
                    FROM scheduled_tasks
                    WHERE id IN ({placeholders})
                    ORDER BY next_run ASC, id ASC
                    """,
                    tuple(claimed_ids),
                ).fetchall()
                tasks = [ScheduledTask(*row) for row in rows]
            conn.commit()
            return tasks
        finally:
            conn.close()

    def mark_run(self, task: ScheduledTask) -> None:
        now = datetime.now(timezone.utc).isoformat()
        next_run = self._compute_next_run(task.schedule_type, task.time_of_day, task.weekday, task.run_at)
        status = task.status
        if task.schedule_type == "once":
            status = "done"
            next_run = None
        conn = sqlite3.connect(self.sqlite_path)
        conn.execute(
            """
            UPDATE scheduled_tasks
            SET last_run = ?, next_run = ?, status = ?, run_lock_owner = '', run_lock_until = ''
            WHERE id = ?
            """,
            (now, next_run, status, task.id),
        )
        conn.commit()
        conn.close()

    def list_tasks(self) -> list[ScheduledTask]:
        conn = sqlite3.connect(self.sqlite_path)
        rows = conn.execute(
            """
            SELECT id, title, action, schedule_type, time_of_day, weekday, run_at, next_run, last_run, status
            FROM scheduled_tasks
            ORDER BY id DESC
            """
        ).fetchall()
        conn.close()
        return [ScheduledTask(*row) for row in rows]

    def find_similar(self, title: str, action: Optional[str] = None, limit: int = 5) -> list[ScheduledTask]:
        """Find similar tasks by token overlap in title and optional action."""
        title_tokens = {t for t in re.split(r"\\W+", title.lower()) if len(t) > 2}
        if not title_tokens:
            return []
        tasks = [t for t in self.list_tasks() if t.status == "active"]
        scored = []
        for t in tasks:
            if action and t.action != action:
                continue
            t_tokens = {x for x in re.split(r"\\W+", (t.title or "").lower()) if len(x) > 2}
            if not t_tokens:
                continue
            overlap = len(title_tokens & t_tokens)
            score = overlap / max(len(title_tokens), 1)
            if score > 0:
                scored.append((score, t))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in scored[:limit]]

    def update_task(
        self,
        task_id: int,
        schedule_type: Optional[str] = None,
        time_of_day: Optional[str] = None,
        weekday: Optional[int] = None,
        run_at: Optional[str] = None,
        title: Optional[str] = None,
        action: Optional[str] = None,
    ) -> None:
        """Update task schedule and recompute next_run."""
        conn = sqlite3.connect(self.sqlite_path)
        row = conn.execute(
            "SELECT schedule_type, time_of_day, weekday, run_at, title, action FROM scheduled_tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        if not row:
            conn.close()
            return
        current = {
            "schedule_type": row[0],
            "time_of_day": row[1],
            "weekday": row[2],
            "run_at": row[3],
            "title": row[4],
            "action": row[5],
        }
        new = {
            "schedule_type": schedule_type or current["schedule_type"],
            "time_of_day": time_of_day or current["time_of_day"],
            "weekday": weekday if weekday is not None else current["weekday"],
            "run_at": run_at or current["run_at"],
            "title": title or current["title"],
            "action": action or current["action"],
        }
        next_run = self._compute_next_run(
            new["schedule_type"], new["time_of_day"], new["weekday"], new["run_at"]
        )
        conn.execute(
            """
            UPDATE scheduled_tasks
            SET schedule_type = ?, time_of_day = ?, weekday = ?, run_at = ?, title = ?, action = ?, next_run = ?, status = 'active'
            WHERE id = ?
            """,
            (
                new["schedule_type"],
                new["time_of_day"],
                new["weekday"],
                new["run_at"],
                new["title"],
                new["action"],
                next_run,
                task_id,
            ),
        )
        conn.commit()
        conn.close()

    def delete_task(self, task_id: int) -> None:
        conn = sqlite3.connect(self.sqlite_path)
        conn.execute("DELETE FROM scheduled_tasks WHERE id = ?", (task_id,))
        conn.commit()
        conn.close()
