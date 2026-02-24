"""SkillRegistry — local registry for VITO skills."""

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from config.logger import get_logger
from config.settings import settings

logger = get_logger("skill_registry", agent="skill_registry")


class SkillRegistry:
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
                CREATE TABLE IF NOT EXISTS skill_registry (
                    name TEXT PRIMARY KEY,
                    category TEXT DEFAULT '',
                    source TEXT DEFAULT '',
                    status TEXT DEFAULT 'learned',
                    security_status TEXT DEFAULT 'unknown',
                    notes TEXT DEFAULT '',
                    version INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    last_used TEXT DEFAULT ''
                )
                """
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"SkillRegistry init failed: {e}", extra={"event": "db_init_error"})

    def register_skill(self, name: str, category: str = "", source: str = "", status: str = "learned",
                       security_status: str = "unknown", notes: str = "") -> None:
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        try:
            existing = conn.execute("SELECT version, notes FROM skill_registry WHERE name = ?", (name,)).fetchone()
            version = 1
            if existing:
                version = int(existing[0] or 1)
                if notes and notes != (existing[1] or ""):
                    version += 1
            conn.execute(
                """
                INSERT INTO skill_registry (name, category, source, status, security_status, notes, version, updated_at, last_used)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    category=excluded.category,
                    source=excluded.source,
                    status=excluded.status,
                    security_status=excluded.security_status,
                    notes=excluded.notes,
                    version=excluded.version,
                    updated_at=excluded.updated_at
                """,
                (name, category, source, status, security_status, notes, version, now, now),
            )
            conn.commit()
        finally:
            conn.close()

    def update_status(self, name: str, status: str) -> None:
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn.execute(
                "UPDATE skill_registry SET status = ?, updated_at = ? WHERE name = ?",
                (status, now, name),
            )
            conn.commit()
        finally:
            conn.close()

    def record_use(self, name: str) -> None:
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn.execute("UPDATE skill_registry SET last_used = ? WHERE name = ?", (now, name))
            conn.commit()
        finally:
            conn.close()

    def get_skill(self, name: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT * FROM skill_registry WHERE name = ?", (name,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_skills(self, limit: int = 100) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT name, category, status, security_status, version, updated_at FROM skill_registry ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            result = []
            for r in rows:
                result.append({
                    "name": r[0],
                    "category": r[1],
                    "status": r[2],
                    "security": r[3],
                    "version": r[4],
                    "updated_at": r[5],
                })
            return result
        finally:
            conn.close()
