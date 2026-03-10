import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional

from config.logger import get_logger
from config.settings import settings

logger = get_logger("memory_blocks", agent="memory_blocks")


class MemoryBlocks:
    """Tracks owner-centric memory blocks and supports short→long consolidation."""

    TABLE = "memory_blocks"

    def __init__(self, sqlite_path: Optional[str] = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self._init_table()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_table(self) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE} (
                    doc_id TEXT PRIMARY KEY,
                    block_type TEXT NOT NULL,
                    summary TEXT DEFAULT '',
                    metadata_json TEXT DEFAULT '{{}}',
                    retention_class TEXT DEFAULT '',
                    stage TEXT DEFAULT 'short',
                    importance REAL DEFAULT 0.5,
                    priority REAL DEFAULT 1.0,
                    status TEXT DEFAULT 'active',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    last_promoted_at TEXT DEFAULT ''
                )
                """
            )
            conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_stage ON {self.TABLE} (stage, status, updated_at)
                """
            )
            conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_retention ON {self.TABLE} (retention_class, stage)
                """
            )
            conn.commit()
        finally:
            conn.close()

    def record_block(
        self,
        doc_id: str,
        block_type: str,
        summary: str,
        metadata: dict[str, Any] | None,
        retention_class: str,
        stage: str,
        importance: float,
        priority: float = 1.0,
    ) -> None:
        conn = self._get_conn()
        payload = json.dumps(metadata or {}, ensure_ascii=False)
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn.execute(
                f"""
                INSERT INTO {self.TABLE} (doc_id, block_type, summary, metadata_json,
                    retention_class, stage, importance, priority, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(doc_id) DO UPDATE SET
                    block_type=excluded.block_type,
                    summary=excluded.summary,
                    metadata_json=excluded.metadata_json,
                    retention_class=excluded.retention_class,
                    stage=excluded.stage,
                    importance=excluded.importance,
                    priority=excluded.priority,
                    status='active',
                    updated_at=excluded.updated_at
                """,
                (doc_id, block_type, summary[:1024], payload, retention_class, stage, importance, priority, now),
            )
            conn.commit()
        finally:
            conn.close()

    def candidates_for_consolidation(
        self,
        min_age_days: int = 3,
        stage: str = "short",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=min_age_days)
        conn = self._get_conn()
        try:
            rows = conn.execute(
                f"""
                SELECT * FROM {self.TABLE}
                WHERE stage = ? AND status = 'active' AND (updated_at <= ? OR last_promoted_at <= ?)
                ORDER BY priority DESC, updated_at ASC
                LIMIT ?
                """,
                (stage, cutoff.isoformat(), cutoff.isoformat(), limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def mark_promoted(
        self,
        doc_id: str,
        new_stage: str,
        reason: str = "consolidated",
    ) -> None:
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn.execute(
                f"""
                UPDATE {self.TABLE}
                SET stage = ?, last_promoted_at = ?, updated_at = ?
                WHERE doc_id = ?
                """,
                (new_stage, now, now, doc_id),
            )
            conn.execute(
                f"""
                INSERT OR IGNORE INTO {self.TABLE} (doc_id, block_type, summary, metadata_json, retention_class, stage, importance, priority, status, created_at, updated_at)
                VALUES (?, '', '', '{{}}', '', '', 0, 0, 'active', ?, ?)
                """,
                (doc_id, now, now),
            )
            conn.commit()
        finally:
            conn.close()

    def get_block(self, doc_id: str) -> Optional[dict[str, Any]]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                f"SELECT * FROM {self.TABLE} WHERE doc_id = ?", (doc_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_blocks(self, doc_ids: Iterable[str]) -> list[dict[str, Any]]:
        items = [str(x).strip() for x in (doc_ids or []) if str(x).strip()]
        if not items:
            return []
        conn = self._get_conn()
        try:
            rows = conn.execute(
                f"SELECT * FROM {self.TABLE} WHERE doc_id IN ({','.join('?' for _ in items)})",
                tuple(items),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def archive_block(self, doc_id: str, status: str = "archived") -> None:
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn.execute(
                f"""
                UPDATE {self.TABLE}
                SET status = ?, updated_at = ?
                WHERE doc_id = ?
                """,
                (status, now, doc_id),
            )
            conn.commit()
        finally:
            conn.close()

    def list_blocks(self, stage: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        conn = self._get_conn()
        try:
            if stage:
                rows = conn.execute(
                    f"SELECT * FROM {self.TABLE} WHERE stage = ? ORDER BY updated_at DESC LIMIT ?",
                    (stage, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT * FROM {self.TABLE} ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def blocks_by_type(
        self,
        block_type: str,
        stage: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        conn = self._get_conn()
        try:
            params = [block_type]
            query = f"SELECT * FROM {self.TABLE} WHERE block_type = ? AND status = 'active'"
            if stage:
                query += " AND stage = ?"
                params.append(stage)
            query += " ORDER BY priority DESC, updated_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, tuple(params)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def find_blocks(
        self,
        *,
        agent: str = "",
        block_types: Iterable[str] | None = None,
        stage: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        conn = self._get_conn()
        try:
            params: list[Any] = []
            query = f"SELECT * FROM {self.TABLE} WHERE status = 'active'"
            if block_types:
                items = [str(x).strip() for x in block_types if str(x).strip()]
                if items:
                    query += f" AND block_type IN ({','.join('?' for _ in items)})"
                    params.extend(items)
            if stage:
                query += " AND stage = ?"
                params.append(stage)
            if agent:
                query += " AND (metadata_json LIKE ? OR doc_id LIKE ?)"
                params.extend([f'%\"agent\": \"{agent}\"%', f"{agent}:%"])
            query += " ORDER BY priority DESC, updated_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, tuple(params)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
