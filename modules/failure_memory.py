"""FailureMemory — record failed attempts to avoid repeating bad paths."""

from __future__ import annotations

import sqlite3
from typing import Optional

from config.logger import get_logger
from config.settings import settings

logger = get_logger("failure_memory", agent="failure_memory")


class FailureMemory:
    def __init__(self, sqlite_path: Optional[str] = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        try:
            conn = self._get_conn()
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS failure_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    detail TEXT DEFAULT '',
                    error TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"FailureMemory init failed: {e}", extra={"event": "db_init_error"})

    def record(self, agent: str, task_type: str, detail: str = "", error: str = "") -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO failure_memory (agent, task_type, detail, error)
                VALUES (?, ?, ?, ?)
                """,
                (agent, task_type, detail[:500], error[:500]),
            )
            conn.commit()
        except Exception as e:
            logger.warning(f"FailureMemory record failed: {e}", extra={"event": "record_error"})
        finally:
            conn.close()

    def recent(self, limit: int = 20) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT agent, task_type, detail, error, created_at FROM failure_memory ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [
                {
                    "agent": r[0],
                    "task_type": r[1],
                    "detail": r[2],
                    "error": r[3],
                    "created_at": r[4],
                }
                for r in rows
            ]
        finally:
            conn.close()
