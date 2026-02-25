"""Workflow threads: lightweight session/thread tracking for long-running work."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from config.settings import settings


class WorkflowThreads:
    def __init__(self, sqlite_path: Optional[str] = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self._init_db()

    def _conn(self):
        c = sqlite3.connect(self.sqlite_path)
        c.row_factory = sqlite3.Row
        return c

    def _init_db(self) -> None:
        conn = self._conn()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_threads (
                thread_id TEXT PRIMARY KEY,
                goal_id TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                last_node TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()
        conn.close()

    def start_thread(self, thread_id: str, goal_id: str = "") -> None:
        conn = self._conn()
        conn.execute(
            """
            INSERT OR REPLACE INTO workflow_threads (thread_id, goal_id, status, last_node, updated_at)
            VALUES (?, ?, 'active', '', ?)
            """,
            (thread_id, goal_id, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()

    def update_thread(self, thread_id: str, status: str = "active", last_node: str = "") -> None:
        conn = self._conn()
        conn.execute(
            """
            UPDATE workflow_threads
            SET status = ?, last_node = ?, updated_at = ?
            WHERE thread_id = ?
            """,
            (status, last_node, datetime.now(timezone.utc).isoformat(), thread_id),
        )
        conn.commit()
        conn.close()

    def get_thread(self, thread_id: str) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM workflow_threads WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def list_threads(self, limit: int = 50) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM workflow_threads ORDER BY updated_at DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
