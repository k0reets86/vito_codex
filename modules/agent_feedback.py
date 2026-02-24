"""AgentFeedback — lightweight structured feedback store for agent outputs."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from config.logger import get_logger
from config.settings import settings

logger = get_logger("agent_feedback", agent="agent_feedback")


class AgentFeedback:
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
                CREATE TABLE IF NOT EXISTS agent_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    output_json TEXT DEFAULT '',
                    error TEXT DEFAULT '',
                    metadata_json TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"AgentFeedback init failed: {e}", extra={"event": "db_init_error"})

    def record(
        self,
        agent: str,
        task_type: str,
        success: bool,
        output=None,
        error: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        try:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO agent_feedback (agent, task_type, success, output_json, error, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    agent,
                    task_type,
                    1 if success else 0,
                    json.dumps(output, ensure_ascii=False)[:4000] if output is not None else "",
                    (error or "")[:500],
                    json.dumps(metadata, ensure_ascii=False)[:2000] if metadata else "",
                ),
            )
            conn.commit()
        except Exception as e:
            logger.warning(f"AgentFeedback record failed: {e}", extra={"event": "record_error"})
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def recent(self, limit: int = 20) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT agent, task_type, success, error, created_at FROM agent_feedback ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [
                {
                    "agent": r[0],
                    "task_type": r[1],
                    "success": bool(r[2]),
                    "error": r[3],
                    "created_at": r[4],
                }
                for r in rows
            ]
        finally:
            conn.close()
