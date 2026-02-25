"""PlaybookRegistry — lightweight auto-playbook store from verified runs."""

from __future__ import annotations

import json
import sqlite3
from typing import Optional

from config.settings import settings


class PlaybookRegistry:
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
            CREATE TABLE IF NOT EXISTS agent_playbooks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent TEXT NOT NULL,
                task_type TEXT NOT NULL,
                action TEXT NOT NULL,
                strategy_json TEXT DEFAULT '{}',
                success_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                last_status TEXT DEFAULT '',
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(agent, task_type, action)
            )
            """
        )
        conn.commit()
        conn.close()

    def learn(self, agent: str, task_type: str, action: str, status: str, strategy: dict | None = None) -> None:
        conn = self._conn()
        ok = str(status).lower() in {"success", "completed", "published", "done"}
        conn.execute(
            """
            INSERT INTO agent_playbooks (agent, task_type, action, strategy_json, success_count, fail_count, last_status, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(agent, task_type, action) DO UPDATE SET
              strategy_json = excluded.strategy_json,
              success_count = success_count + ?,
              fail_count = fail_count + ?,
              last_status = excluded.last_status,
              updated_at = datetime('now')
            """,
            (
                agent[:100],
                task_type[:100],
                action[:160],
                json.dumps(strategy or {}, ensure_ascii=False)[:2000],
                1 if ok else 0,
                0 if ok else 1,
                status[:40],
                1 if ok else 0,
                0 if ok else 1,
            ),
        )
        conn.commit()
        conn.close()

    def top(self, limit: int = 50) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """
            SELECT agent, task_type, action, success_count, fail_count, last_status, updated_at
            FROM agent_playbooks
            ORDER BY (success_count - fail_count) DESC, updated_at DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def count(self) -> int:
        conn = self._conn()
        try:
            row = conn.execute("SELECT COUNT(*) n FROM agent_playbooks").fetchone()
            return int(row["n"] or 0)
        finally:
            conn.close()

    def backfill_from_execution_facts(self, limit: int = 1000) -> int:
        """Bootstrap playbooks from existing execution_facts history."""
        conn = self._conn()
        inserted = 0
        try:
            rows = conn.execute(
                """
                SELECT action, status, detail, source
                FROM execution_facts
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            for r in rows:
                action = str(r["action"] or "")
                status = str(r["status"] or "")
                source = str(r["source"] or "")
                detail = str(r["detail"] or "")
                agent = (source or action.split(":", 1)[0] or "system").split(".", 1)[0]
                task_type = action.split(":", 1)[-1] if ":" in action else action
                self.learn(
                    agent=agent,
                    task_type=task_type,
                    action=action,
                    status=status,
                    strategy={"detail": detail[:200]},
                )
                inserted += 1
        finally:
            conn.close()
        return inserted

    def ensure_bootstrap(self, limit: int = 1000) -> int:
        """
        Backfill playbooks once from execution_facts when table is empty.
        Returns number of inserted backfill rows (0 when already populated).
        """
        if self.count() > 0:
            return 0
        return self.backfill_from_execution_facts(limit=limit)
