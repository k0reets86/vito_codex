"""Autonomous improvement backlog generator (safe, evidence-first)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from config.settings import settings


class AutonomousImprovementEngine:
    def __init__(self, sqlite_path: Optional[str] = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._conn()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS autonomous_improvement_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT DEFAULT '',
                    priority INTEGER DEFAULT 5,
                    status TEXT DEFAULT 'open',
                    metadata_json TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_autonomous_improvement_status
                ON autonomous_improvement_actions(status, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_autonomous_improvement_action
                ON autonomous_improvement_actions(action, status, created_at DESC);
                """
            )
            conn.commit()
        finally:
            conn.close()

    def _has_open_recent(self, action: str, reason: str, dedup_hours: int = 72) -> bool:
        conn = self._conn()
        try:
            row = conn.execute(
                """
                SELECT id
                FROM autonomous_improvement_actions
                WHERE status = 'open'
                  AND action = ?
                  AND reason = ?
                  AND created_at >= datetime('now', ?)
                ORDER BY id DESC
                LIMIT 1
                """,
                (str(action)[:120], str(reason)[:300], f"-{max(1, int(dedup_hours or 72))} hours"),
            ).fetchone()
            return bool(row)
        finally:
            conn.close()

    def _add_action(self, source: str, action: str, reason: str, priority: int, metadata: dict[str, Any] | None = None) -> int:
        conn = self._conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO autonomous_improvement_actions
                (source, action, reason, priority, status, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'open', ?, ?, ?)
                """,
                (
                    str(source or "unknown")[:60],
                    str(action or "")[:120],
                    str(reason or "")[:300],
                    max(1, min(9, int(priority or 5))),
                    json.dumps(metadata or {}, ensure_ascii=False)[:5000],
                    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            conn.commit()
            return int(cur.lastrowid or 0)
        finally:
            conn.close()

    def list_actions(self, status: str = "open", limit: int = 50) -> list[dict[str, Any]]:
        conn = self._conn()
        try:
            if status:
                rows = conn.execute(
                    """
                    SELECT * FROM autonomous_improvement_actions
                    WHERE status = ?
                    ORDER BY priority ASC, id DESC
                    LIMIT ?
                    """,
                    (str(status)[:20], int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM autonomous_improvement_actions ORDER BY id DESC LIMIT ?",
                    (int(limit),),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def summary(self, days: int = 7) -> dict[str, Any]:
        conn = self._conn()
        try:
            rows = conn.execute(
                """
                SELECT status, COUNT(*) AS n
                FROM autonomous_improvement_actions
                WHERE created_at >= datetime('now', ?)
                GROUP BY status
                """,
                (f"-{max(1, int(days or 7))} day",),
            ).fetchall()
            by_status = {str(r["status"]): int(r["n"] or 0) for r in rows}
            return {
                "window_days": max(1, int(days or 7)),
                "total": int(sum(by_status.values())),
                "open": int(by_status.get("open", 0)),
                "applied": int(by_status.get("applied", 0)),
                "skipped": int(by_status.get("skipped", 0)),
                "failed": int(by_status.get("failed", 0)),
                "by_status": by_status,
            }
        finally:
            conn.close()

    def generate_candidates(
        self,
        *,
        governance: dict[str, Any] | None = None,
        self_learning_summary: dict[str, Any] | None = None,
        limit: int = 4,
    ) -> dict[str, Any]:
        governance = governance or {}
        self_learning_summary = self_learning_summary or {}
        max_items = max(1, int(limit or 4))
        created: list[dict[str, Any]] = []
        queue: list[dict[str, Any]] = []

        status = str(governance.get("status") or "ok")
        for item in list(governance.get("safe_action_suggestions", []) or []):
            action = str(item.get("action") or "").strip()
            if not action:
                continue
            reason = f"governance:{str(item.get('reason') or status)[:220]}"
            queue.append(
                {
                    "source": "governance",
                    "action": action,
                    "reason": reason,
                    "priority": int(item.get("priority", 5) or 5),
                    "metadata": {"score": float(item.get("score", 0) or 0.0), "status": status},
                }
            )

        open_jobs = int(self_learning_summary.get("open_test_jobs", 0) or 0)
        pending = int(self_learning_summary.get("pending_candidates", 0) or 0)
        if open_jobs > 0:
            queue.append(
                {
                    "source": "self_learning",
                    "action": "run_self_learning_test_jobs",
                    "reason": f"self_learning:open_test_jobs={open_jobs}",
                    "priority": 3,
                    "metadata": {"open_test_jobs": open_jobs},
                }
            )
        if pending > 0:
            queue.append(
                {
                    "source": "self_learning",
                    "action": "optimize_self_learning_candidates",
                    "reason": f"self_learning:pending_candidates={pending}",
                    "priority": 4,
                    "metadata": {"pending_candidates": pending},
                }
            )

        # Keep deterministic order: priority asc, then action.
        queue = sorted(queue, key=lambda x: (int(x.get("priority", 5)), str(x.get("action", ""))))
        dedup_hours = 72
        for candidate in queue:
            if len(created) >= max_items:
                break
            action = str(candidate.get("action") or "")
            reason = str(candidate.get("reason") or "")
            if self._has_open_recent(action=action, reason=reason, dedup_hours=dedup_hours):
                continue
            cid = self._add_action(
                source=str(candidate.get("source") or "unknown"),
                action=action,
                reason=reason,
                priority=int(candidate.get("priority", 5) or 5),
                metadata=candidate.get("metadata", {}),
            )
            created.append(
                {
                    "id": cid,
                    "action": action,
                    "reason": reason,
                    "priority": int(candidate.get("priority", 5) or 5),
                    "source": str(candidate.get("source") or "unknown"),
                }
            )

        return {
            "created": int(len(created)),
            "candidates": created,
            "summary": self.summary(days=7),
        }
