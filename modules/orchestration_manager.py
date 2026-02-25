"""Stateful orchestration manager: graph-driven sessions, interrupts, checkpoints."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from config.settings import settings
from modules.workflow_graph import WorkflowGraph
from modules.workflow_interrupts import WorkflowInterrupts
from modules.workflow_state_machine import WorkflowStateMachine


class OrchestrationManager:
    SESSION_TABLE = "workflow_sessions"
    STEP_TABLE = "workflow_session_steps"

    def __init__(self, sqlite_path: Optional[str] = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self._init_db()
        self.graph = WorkflowGraph()
        self.state_machine = WorkflowStateMachine(sqlite_path=self.sqlite_path)
        self.interrupts = WorkflowInterrupts(sqlite_path=self.sqlite_path)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._conn()
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.SESSION_TABLE} (
                goal_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                trace_id TEXT DEFAULT '',
                plan_steps TEXT DEFAULT '[]',
                current_step INTEGER DEFAULT 0,
                state TEXT DEFAULT 'created',
                blocking_reason TEXT DEFAULT '',
                thread_id TEXT DEFAULT '',
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.STEP_TABLE} (
                goal_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                description TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                detail TEXT DEFAULT '',
                last_output TEXT DEFAULT '',
                updated_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY(goal_id, step_index)
            )
            """
        )
        conn.commit()
        conn.close()

    def create_session(
        self,
        goal_id: str,
        plan_steps: Iterable[str],
        trace_id: str,
        thread_id: str,
    ) -> None:
        """Persist plan + step state and mark session running."""
        plan_list = list(plan_steps)
        plan_json = json.dumps(plan_list, ensure_ascii=False)
        session_id = f"session_{uuid.uuid4().hex[:11]}"
        conn = self._conn()
        conn.execute(
            f"""
            INSERT INTO {self.SESSION_TABLE} (goal_id, session_id, trace_id, plan_steps, current_step, state, blocking_reason, thread_id, updated_at)
            VALUES (?, ?, ?, ?, 0, 'executing', '', ?, datetime('now'))
            ON CONFLICT(goal_id) DO UPDATE SET
                plan_steps = excluded.plan_steps,
                current_step = 0,
                state = 'executing',
                blocking_reason = '',
                trace_id = excluded.trace_id,
                thread_id = excluded.thread_id,
                updated_at = excluded.updated_at
            """,
            (goal_id, session_id, trace_id, plan_json, thread_id),
        )
        for idx, step in enumerate(plan_list):
            conn.execute(
                f"""
                INSERT INTO {self.STEP_TABLE} (goal_id, step_index, description, status, updated_at)
                VALUES (?, ?, ?, 'pending', datetime('now'))
                ON CONFLICT(goal_id, step_index) DO UPDATE SET
                    description = excluded.description,
                    status = 'pending',
                    detail = '',
                    last_output = '',
                    updated_at = datetime('now')
                """,
                (goal_id, idx, step),
            )
        conn.commit()
        conn.close()

    def get_plan(self, goal_id: str) -> list[str]:
        conn = self._conn()
        row = conn.execute(
            f"SELECT plan_steps FROM {self.SESSION_TABLE} WHERE goal_id = ?",
            (goal_id,),
        ).fetchone()
        conn.close()
        if not row:
            return []
        try:
            return json.loads(row["plan_steps"] or "[]")
        except Exception:
            return []

    def get_session(self, goal_id: str) -> dict[str, Any]:
        conn = self._conn()
        row = conn.execute(
            f"SELECT goal_id, session_id, trace_id, current_step, state, blocking_reason, thread_id FROM {self.SESSION_TABLE} WHERE goal_id = ?",
            (goal_id,),
        ).fetchone()
        conn.close()
        if not row:
            return {}
        return dict(row)

    def next_step_index(self, goal_id: str) -> Optional[int]:
        conn = self._conn()
        row = conn.execute(
            f"""
            SELECT step_index, status
            FROM {self.STEP_TABLE}
            WHERE goal_id = ? AND status IN ('pending', 'waiting_approval')
            ORDER BY step_index ASC
            LIMIT 1
            """,
            (goal_id,),
        ).fetchone()
        conn.close()
        if not row:
            return None
        return int(row["step_index"])

    def step_description(self, goal_id: str, step_index: int) -> str:
        conn = self._conn()
        row = conn.execute(
            f"""
            SELECT description FROM {self.STEP_TABLE}
            WHERE goal_id = ? AND step_index = ?
            """,
            (goal_id, step_index),
        ).fetchone()
        conn.close()
        return str(row["description"] or "") if row else ""

    def mark_step_executing(self, goal_id: str, step_index: int) -> None:
        self._update_step(goal_id, step_index, status="executing")

    def record_step_result(
        self,
        goal_id: str,
        step_index: int,
        status: str,
        detail: str = "",
        output: str = "",
    ) -> None:
        mapped = self._map_status(status)
        self._update_step(
            goal_id,
            step_index,
            status=mapped,
            detail=detail,
            last_output=output,
        )
        conn = self._conn()
        next_index = step_index + 1
        state_cls = "executing"
        blocking_reason = ""
        if mapped == "waiting_approval":
            state_cls = "waiting_approval"
            blocking_reason = f"step_{step_index}"
            next_index = step_index
        elif mapped == "failed":
            state_cls = "failed"
        elif mapped == "completed":
            state_cls = "executing"
        conn.execute(
            f"""
            UPDATE {self.SESSION_TABLE}
            SET current_step = ?, state = ?, blocking_reason = ?, updated_at = datetime('now')
            WHERE goal_id = ?
            """,
            (next_index, state_cls, blocking_reason, goal_id),
        )
        conn.commit()
        conn.close()

    def pause_session(self, goal_id: str, reason: str) -> None:
        self._set_session_state(goal_id, "waiting_approval", reason)

    def resume_session(self, goal_id: str, reason: str = "owner_resumed") -> None:
        conn = self._conn()
        conn.execute(
            f"""
            UPDATE {self.STEP_TABLE}
            SET status = 'pending', updated_at = datetime('now')
            WHERE goal_id = ? AND status = 'waiting_approval'
            """,
            (goal_id,),
        )
        conn.commit()
        conn.close()
        self._set_session_state(goal_id, "executing", reason, clear_blocking=True)

    def _set_session_state(self, goal_id: str, state: str, reason: str, clear_blocking: bool = False) -> None:
        conn = self._conn()
        blocking = "" if clear_blocking else reason
        conn.execute(
            f"""
            UPDATE {self.SESSION_TABLE}
            SET state = ?, blocking_reason = ?, updated_at = datetime('now')
            WHERE goal_id = ?
            """,
            (state, blocking, goal_id),
        )
        conn.commit()
        conn.close()

    def fetch_step_status(self, goal_id: str, step_index: int) -> dict[str, Any]:
        conn = self._conn()
        row = conn.execute(
            f"""
            SELECT * FROM {self.STEP_TABLE}
            WHERE goal_id = ? AND step_index = ?
            """,
            (goal_id, step_index),
        ).fetchone()
        conn.close()
        return dict(row) if row else {}

    def list_pending_sessions(self) -> list[dict[str, Any]]:
        conn = self._conn()
        rows = conn.execute(
            f"""
            SELECT * FROM {self.SESSION_TABLE}
            WHERE state IN ('waiting_approval', 'executing')
            ORDER BY updated_at DESC
            """
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def _update_step(
        self,
        goal_id: str,
        step_index: int,
        *,
        status: str,
        detail: str = "",
        last_output: str = "",
    ) -> None:
        conn = self._conn()
        conn.execute(
            f"""
            UPDATE {self.STEP_TABLE}
            SET status = ?, detail = ?, last_output = ?, updated_at = datetime('now')
            WHERE goal_id = ? AND step_index = ?
            """,
            (status, detail[:500], last_output[:500], goal_id, step_index),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def _map_status(status: str) -> str:
        low = (status or "").strip().lower()
        if low in {"waiting_approval", "needs_approval", "blocked"}:
            return "waiting_approval"
        if low in {"done", "success", "completed"}:
            return "completed"
        if low in {"error", "failed", "fail"}:
            return "failed"
        if low in {"executing", "running"}:
            return "executing"
        return "pending"

    def list_sessions(self, state_filter: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        conn = self._conn()
        try:
            query = f"""
            SELECT goal_id, session_id, trace_id, plan_steps, current_step, state, blocking_reason, thread_id, updated_at
            FROM {self.SESSION_TABLE}
            """
            params: list[Any] = []
            if state_filter:
                query += " WHERE state = ?"
                params.append(state_filter)
            query += " ORDER BY updated_at DESC LIMIT ?"
            params.append(int(limit))
            rows = conn.execute(query, tuple(params)).fetchall()
        finally:
            conn.close()
        sessions: list[dict[str, Any]] = []
        for row in rows:
            plan_steps = []
            try:
                plan_steps = json.loads(row["plan_steps"] or "[]")
            except Exception:
                plan_steps = []
            sessions.append({
                "goal_id": row["goal_id"] or "",
                "session_id": row["session_id"] or "",
                "trace_id": row["trace_id"] or "",
                "state": row["state"] or "",
                "current_step": int(row["current_step"] or 0),
                "plan_length": len(plan_steps),
                "plan_steps": plan_steps,
                "blocking_reason": row["blocking_reason"] or "",
                "thread_id": row["thread_id"] or "",
                "updated_at": row["updated_at"] or "",
            })
        return sessions

    def list_steps(self, goal_id: str) -> list[dict[str, Any]]:
        conn = self._conn()
        try:
            rows = conn.execute(
                f"""
                SELECT step_index, description, status, detail, last_output, updated_at
                FROM {self.STEP_TABLE}
                WHERE goal_id = ?
                ORDER BY step_index ASC
                """,
                (goal_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def cancel_session(self, goal_id: str, reason: str = "dashboard_cancel") -> None:
        conn = self._conn()
        try:
            conn.execute(
                f"""
                UPDATE {self.SESSION_TABLE}
                SET state = 'cancelled', blocking_reason = ?, updated_at = datetime('now')
                WHERE goal_id = ?
                """,
                (reason, goal_id),
            )
            conn.execute(
                f"""
                UPDATE {self.STEP_TABLE}
                SET status = 'cancelled', detail = ?, last_output = ?, updated_at = datetime('now')
                WHERE goal_id = ?
                """,
                (reason, reason, goal_id),
            )
            conn.commit()
        finally:
            conn.close()
        self._safe_transition(goal_id, "cancelled", reason)

    def reset_session(self, goal_id: str, reason: str = "dashboard_reset") -> None:
        conn = self._conn()
        try:
            conn.execute(
                f"""
                UPDATE {self.SESSION_TABLE}
                SET current_step = 0, state = 'executing', blocking_reason = '', updated_at = datetime('now')
                WHERE goal_id = ?
                """,
                (goal_id,),
            )
            conn.execute(
                f"""
                UPDATE {self.STEP_TABLE}
                SET status = 'pending', detail = '', last_output = '', updated_at = datetime('now')
                WHERE goal_id = ?
                """,
                (goal_id,),
            )
            conn.commit()
        finally:
            conn.close()
        self._safe_transition(goal_id, "executing", reason)

    def _safe_transition(self, goal_id: str, to_state: str, reason: str) -> None:
        try:
            self.state_machine.transition(goal_id, to_state, reason=reason, detail="dashboard_action")
        except Exception:
            pass
