"""Policy-driven short->long memory consolidation runtime."""

from __future__ import annotations

import sqlite3
from typing import Any

from config.logger import get_logger
from config.settings import settings

logger = get_logger("memory_consolidation", agent="memory_consolidation")


class MemoryConsolidationEngine:
    def __init__(self, memory_manager, sqlite_path: str | None = None):
        self.memory = memory_manager
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self._conn: sqlite3.Connection | None = None
        self._init_tables()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.sqlite_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_tables(self) -> None:
        conn = self._get_conn()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_consolidation_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                promoted INTEGER NOT NULL DEFAULT 0,
                expired_preview INTEGER NOT NULL DEFAULT 0,
                drift_alerts INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                details_json TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()

    def latest_run(self) -> dict[str, Any] | None:
        row = self._get_conn().execute(
            "SELECT * FROM memory_consolidation_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def run_cycle(self, *, min_age_days: int = 5, limit: int = 25) -> dict[str, Any]:
        preview = self.memory.cleanup_expired_memory(limit=max(limit, 50), dry_run=True)
        drift = self.memory.retention_drift_alerts(days=30)
        promoted = self.memory.consolidate_short_term_memory(min_age_days=min_age_days, limit=limit)
        expired_preview = int(preview.get("expired_found", 0) or 0)
        drift_alerts = len((drift.get("alerts") if isinstance(drift, dict) else []) or [])
        status = "clean"
        if promoted > 0:
            status = "promoted"
        if drift_alerts > 0:
            status = "warning"
        if expired_preview > 0 and promoted == 0:
            status = "backlog"
        result = {
            "promoted": promoted,
            "expired_preview": expired_preview,
            "drift_alerts": drift_alerts,
            "status": status,
            "preview": preview,
            "drift": drift,
        }
        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO memory_consolidation_runs (
                promoted, expired_preview, drift_alerts, status, details_json
            ) VALUES (?, ?, ?, ?, json(?))
            """,
            (promoted, expired_preview, drift_alerts, status, __import__("json").dumps(result, ensure_ascii=False)),
        )
        conn.commit()
        logger.info(
            "memory_consolidation_cycle",
            extra={"event": "memory_consolidation_cycle", "context": result},
        )
        return result
