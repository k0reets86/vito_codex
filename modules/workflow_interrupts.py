"""Durable interrupt registry for long-running workflows."""

from __future__ import annotations

import json
import sqlite3
from typing import Optional

from config.settings import settings


class WorkflowInterrupts:
    def __init__(self, sqlite_path: Optional[str] = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflow_interrupts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal_id TEXT NOT NULL,
                    step_num INTEGER DEFAULT 0,
                    thread_id TEXT DEFAULT '',
                    interrupt_type TEXT NOT NULL,
                    reason TEXT DEFAULT '',
                    payload_json TEXT DEFAULT '{}',
                    status TEXT DEFAULT 'pending',
                    created_at TEXT DEFAULT (datetime('now')),
                    resolved_at TEXT DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_workflow_interrupts_goal_status
                ON workflow_interrupts (goal_id, status, created_at DESC);
                """
            )
            conn.commit()
        finally:
            conn.close()

    def open_interrupt(
        self,
        goal_id: str,
        interrupt_type: str,
        reason: str = "",
        step_num: int = 0,
        thread_id: str = "",
        payload: dict | None = None,
    ) -> int:
        conn = self._get_conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO workflow_interrupts
                (goal_id, step_num, thread_id, interrupt_type, reason, payload_json, status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    goal_id[:120],
                    int(step_num or 0),
                    thread_id[:120],
                    interrupt_type[:60],
                    reason[:500],
                    json.dumps(payload or {}, ensure_ascii=False)[:5000],
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def resolve_interrupt(self, interrupt_id: int, resolution: str = "resumed") -> bool:
        status = "resolved" if resolution == "resumed" else "cancelled"
        conn = self._get_conn()
        try:
            cur = conn.execute(
                """
                UPDATE workflow_interrupts
                SET status = ?, resolved_at = datetime('now')
                WHERE id = ? AND status = 'pending'
                """,
                (status, int(interrupt_id)),
            )
            conn.commit()
            return int(cur.rowcount or 0) > 0
        finally:
            conn.close()

    def resolve_pending_for_goal(self, goal_id: str, resolution: str = "resumed") -> int:
        status = "resolved" if resolution == "resumed" else "cancelled"
        conn = self._get_conn()
        try:
            cur = conn.execute(
                """
                UPDATE workflow_interrupts
                SET status = ?, resolved_at = datetime('now')
                WHERE goal_id = ? AND status = 'pending'
                """,
                (status, goal_id),
            )
            conn.commit()
            return int(cur.rowcount or 0)
        finally:
            conn.close()

    def latest_pending(self, goal_id: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                """
                SELECT * FROM workflow_interrupts
                WHERE goal_id = ? AND status = 'pending'
                ORDER BY id DESC
                LIMIT 1
                """,
                (goal_id,),
            ).fetchone()
            if not row:
                return None
            out = dict(row)
            try:
                out["payload"] = json.loads(out.get("payload_json") or "{}")
            except Exception:
                out["payload"] = {}
            return out
        finally:
            conn.close()

    def list_interrupts(self, status: str = "", limit: int = 100) -> list[dict]:
        conn = self._get_conn()
        try:
            if status:
                rows = conn.execute(
                    """
                    SELECT * FROM workflow_interrupts
                    WHERE status = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (status, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM workflow_interrupts
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (int(limit),),
                ).fetchall()
            out = []
            for row in rows:
                d = dict(row)
                try:
                    d["payload"] = json.loads(d.get("payload_json") or "{}")
                except Exception:
                    d["payload"] = {}
                out.append(d)
            return out
        finally:
            conn.close()
