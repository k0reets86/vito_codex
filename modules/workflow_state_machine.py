"""Durable goal workflow state machine (checkpoint + transition history)."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

from config.settings import settings


class WorkflowStateMachine:
    """Persists orchestration states per goal with transition validation."""

    ALLOWED: dict[str, set[str]] = {
        "created": {"planning", "cancelled", "failed"},
        "planning": {"executing", "waiting_approval", "failed", "cancelled"},
        "waiting_approval": {"executing", "failed", "cancelled"},
        "executing": {"learning", "waiting_approval", "failed", "cancelled"},
        "learning": {"completed", "failed"},
        "completed": set(),
        "failed": set(),
        "cancelled": set(),
    }

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
            CREATE TABLE IF NOT EXISTS goal_workflows (
                goal_id TEXT PRIMARY KEY,
                trace_id TEXT NOT NULL,
                state TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS goal_workflow_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_id TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                from_state TEXT DEFAULT '',
                to_state TEXT NOT NULL,
                reason TEXT DEFAULT '',
                detail TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()
        conn.close()

    def start_or_attach(self, goal_id: str) -> str:
        """Create workflow row if missing and return trace_id."""
        conn = self._conn()
        row = conn.execute(
            "SELECT trace_id, state FROM goal_workflows WHERE goal_id=?",
            (goal_id,),
        ).fetchone()
        if row:
            trace_id = str(row["trace_id"])
            conn.close()
            return trace_id
        trace_id = f"wf_{uuid.uuid4().hex[:12]}"
        conn.execute(
            """
            INSERT INTO goal_workflows(goal_id, trace_id, state, updated_at)
            VALUES (?, ?, 'created', datetime('now'))
            """,
            (goal_id, trace_id),
        )
        conn.execute(
            """
            INSERT INTO goal_workflow_events(goal_id, trace_id, from_state, to_state, reason, detail)
            VALUES (?, ?, '', 'created', 'bootstrap', '')
            """,
            (goal_id, trace_id),
        )
        conn.commit()
        conn.close()
        return trace_id

    def get_state(self, goal_id: str) -> Optional[str]:
        conn = self._conn()
        row = conn.execute("SELECT state FROM goal_workflows WHERE goal_id=?", (goal_id,)).fetchone()
        conn.close()
        if not row:
            return None
        return str(row["state"])

    def transition(self, goal_id: str, to_state: str, reason: str = "", detail: str = "") -> tuple[bool, str]:
        """Validated transition. Returns (ok, trace_id)."""
        to_state = (to_state or "").strip().lower()
        trace_id = self.start_or_attach(goal_id)
        conn = self._conn()
        row = conn.execute(
            "SELECT state, trace_id FROM goal_workflows WHERE goal_id=?",
            (goal_id,),
        ).fetchone()
        if not row:
            conn.close()
            return False, trace_id
        from_state = str(row["state"] or "created")
        if to_state == from_state:
            conn.close()
            return True, trace_id
        allowed = self.ALLOWED.get(from_state, set())
        if to_state not in allowed:
            conn.execute(
                """
                INSERT INTO goal_workflow_events(goal_id, trace_id, from_state, to_state, reason, detail)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    goal_id,
                    trace_id,
                    from_state,
                    to_state,
                    "invalid_transition",
                    f"{reason}; {detail}"[:800],
                ),
            )
            conn.commit()
            conn.close()
            return False, trace_id
        conn.execute(
            """
            UPDATE goal_workflows
            SET state=?, updated_at=datetime('now')
            WHERE goal_id=?
            """,
            (to_state, goal_id),
        )
        conn.execute(
            """
            INSERT INTO goal_workflow_events(goal_id, trace_id, from_state, to_state, reason, detail)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (goal_id, trace_id, from_state, to_state, reason[:200], detail[:800]),
        )
        conn.commit()
        conn.close()
        return True, trace_id

    def checkpoint_step(self, goal_id: str, step_num: int, status: str, detail: str = "") -> None:
        """Persist step-level checkpoint event (durable resume trail)."""
        trace_id = self.start_or_attach(goal_id)
        conn = self._conn()
        conn.execute(
            """
            INSERT INTO goal_workflow_events(goal_id, trace_id, from_state, to_state, reason, detail)
            VALUES (?, ?, '', 'executing', ?, ?)
            """,
            (
                goal_id,
                trace_id,
                f"step:{int(step_num)}:{(status or '').lower()}"[:200],
                detail[:800],
            ),
        )
        conn.commit()
        conn.close()

    def recent_events(self, goal_id: str, limit: int = 50) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """
            SELECT goal_id, trace_id, from_state, to_state, reason, detail, created_at
            FROM goal_workflow_events
            WHERE goal_id=?
            ORDER BY id DESC
            LIMIT ?
            """,
            (goal_id, int(limit)),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def recent_events_all(self, limit: int = 50) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """
            SELECT goal_id, trace_id, from_state, to_state, reason, detail, created_at
            FROM goal_workflow_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def latest_checkpoint(self, goal_id: str) -> Optional[dict]:
        """Return last step checkpoint for goal (step_num, status, detail, created_at)."""
        conn = self._conn()
        row = conn.execute(
            """
            SELECT reason, detail, created_at
            FROM goal_workflow_events
            WHERE goal_id=? AND reason LIKE 'step:%'
            ORDER BY id DESC
            LIMIT 1
            """,
            (goal_id,),
        ).fetchone()
        conn.close()
        if not row:
            return None
        reason = str(row["reason"] or "")
        parts = reason.split(":")
        step_num = None
        status = ""
        if len(parts) >= 3:
            try:
                step_num = int(parts[1])
            except Exception:
                step_num = None
            status = parts[2] or ""
        return {
            "step_num": step_num,
            "status": status,
            "detail": row["detail"] or "",
            "created_at": row["created_at"] or "",
        }

    def health(self) -> dict:
        conn = self._conn()
        row = conn.execute(
            "SELECT COUNT(*) n, MAX(updated_at) last_ts FROM goal_workflows"
        ).fetchone()
        conn.close()
        return {
            "workflows_total": int(row["n"] or 0),
            "last_update": row["last_ts"] or datetime.now(timezone.utc).isoformat(),
        }
