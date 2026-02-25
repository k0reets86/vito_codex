"""LLM guardrails: prompt-injection detection with auditable events."""

from __future__ import annotations

import sqlite3
from typing import Optional

from config.settings import settings
from modules.prompt_guard import has_prompt_injection_signals


class LLMGuardrails:
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
                CREATE TABLE IF NOT EXISTS llm_guardrail_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    task_type TEXT DEFAULT '',
                    severity TEXT DEFAULT 'warn',
                    blocked INTEGER DEFAULT 0,
                    snippet TEXT DEFAULT '',
                    reason TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_guardrail_created ON llm_guardrail_events (created_at DESC);
                """
            )
            conn.commit()
        finally:
            conn.close()

    def inspect_prompt(self, task_type: str, prompt: str) -> dict:
        signals = bool(has_prompt_injection_signals(prompt or ""))
        if not signals:
            return {"ok": True, "blocked": False, "reason": "clean"}
        block = bool(getattr(settings, "GUARDRAILS_BLOCK_ON_INJECTION", False))
        reason = "prompt_injection_signals"
        self.record_event(
            event_type="prompt_injection",
            task_type=task_type,
            severity="high" if block else "warn",
            blocked=block,
            snippet=(prompt or "")[:220],
            reason=reason,
        )
        return {"ok": not block, "blocked": block, "reason": reason}

    def record_event(
        self,
        event_type: str,
        task_type: str,
        severity: str,
        blocked: bool,
        snippet: str,
        reason: str,
    ) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO llm_guardrail_events
                (event_type, task_type, severity, blocked, snippet, reason)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    (event_type or "")[:60],
                    (task_type or "")[:40],
                    (severity or "warn")[:20],
                    1 if blocked else 0,
                    (snippet or "")[:500],
                    (reason or "")[:200],
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def recent_events(self, limit: int = 100) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT event_type, task_type, severity, blocked, snippet, reason, created_at
                FROM llm_guardrail_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def summary(self, days: int = 7) -> dict:
        conn = self._get_conn()
        try:
            row = conn.execute(
                """
                SELECT
                  COUNT(*) AS total,
                  SUM(CASE WHEN blocked = 1 THEN 1 ELSE 0 END) AS blocked
                FROM llm_guardrail_events
                WHERE created_at >= datetime('now', ?)
                """,
                (f"-{int(days)} day",),
            ).fetchone()
            top = conn.execute(
                """
                SELECT reason, COUNT(*) AS n
                FROM llm_guardrail_events
                WHERE created_at >= datetime('now', ?)
                GROUP BY reason
                ORDER BY n DESC
                LIMIT 10
                """,
                (f"-{int(days)} day",),
            ).fetchall()
            return {
                "days": int(days),
                "total": int((row["total"] if row else 0) or 0),
                "blocked": int((row["blocked"] if row else 0) or 0),
                "top_reasons": [{"reason": r["reason"], "count": int(r["n"])} for r in top],
            }
        finally:
            conn.close()
