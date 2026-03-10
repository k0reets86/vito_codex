from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from config.settings import settings


class EvolutionArchive:
    """Structured archive for healing/evolution attempts and outcomes."""

    def __init__(self, sqlite_path: str | None = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self._init_db()

    def _conn(self):
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._conn()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS evolution_archive (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    archive_type TEXT NOT NULL,
                    title TEXT DEFAULT '',
                    success INTEGER DEFAULT 0,
                    payload_json TEXT DEFAULT '{}',
                    task_root_id TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_evolution_archive_type
                    ON evolution_archive(archive_type, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_evolution_archive_task
                    ON evolution_archive(task_root_id, created_at DESC);
                """
            )
            conn.commit()
        finally:
            conn.close()

    def record(
        self,
        *,
        archive_type: str,
        title: str,
        payload: dict[str, Any],
        success: bool,
        task_root_id: str = "",
    ) -> int:
        conn = self._conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO evolution_archive
                (archive_type, title, success, payload_json, task_root_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(archive_type or "")[:80],
                    str(title or "")[:240],
                    1 if success else 0,
                    json.dumps(_sanitize(payload or {}), ensure_ascii=False),
                    str(task_root_id or "")[:120],
                ),
            )
            conn.commit()
            return int(cur.lastrowid or 0)
        finally:
            conn.close()

    def recent(self, archive_type: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        conn = self._conn()
        try:
            if archive_type:
                rows = conn.execute(
                    "SELECT * FROM evolution_archive WHERE archive_type = ? ORDER BY id DESC LIMIT ?",
                    (archive_type, max(1, int(limit or 20))),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM evolution_archive ORDER BY id DESC LIMIT ?",
                    (max(1, int(limit or 20)),),
                ).fetchall()
        finally:
            conn.close()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["payload"] = json.loads(item.get("payload_json") or "{}")
            except Exception:
                item["payload"] = {}
            out.append(item)
        return out

    def summary(self, limit: int = 100) -> dict[str, Any]:
        items = self.recent(limit=max(1, int(limit or 100)))
        total = len(items)
        success = sum(1 for item in items if int(item.get("success") or 0) == 1)
        by_type: dict[str, int] = {}
        for item in items:
            key = str(item.get("archive_type") or "unknown")
            by_type[key] = by_type.get(key, 0) + 1
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total": total,
            "success": success,
            "fail": max(0, total - success),
            "success_rate": (success / total) if total else 0.0,
            "by_type": by_type,
        }


def _sanitize(value: Any):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_sanitize(v) for v in value]
    return str(value)
