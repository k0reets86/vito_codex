from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.paths import PROJECT_ROOT

DB_PATH = PROJECT_ROOT / 'runtime' / 'platform_auth_interrupts.db'


class PlatformAuthInterrupts:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS platform_auth_interrupts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service TEXT NOT NULL,
                    blocker TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    detail TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    resolved_at TEXT DEFAULT ''
                )
                '''
            )
            conn.execute(
                'CREATE INDEX IF NOT EXISTS idx_platform_auth_interrupts_service_status ON platform_auth_interrupts(service, status)'
            )

    def raise_interrupt(self, service: str, blocker: str, detail: str = '') -> int:
        svc = str(service or '').strip().lower()
        blk = str(blocker or '').strip().lower() or 'missing_session'
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            row = conn.execute(
                'SELECT id FROM platform_auth_interrupts WHERE service=? AND status=? ORDER BY id DESC LIMIT 1',
                (svc, 'pending'),
            ).fetchone()
            if row:
                conn.execute(
                    'UPDATE platform_auth_interrupts SET blocker=?, detail=?, created_at=? WHERE id=?',
                    (blk, str(detail or ''), now, int(row['id'])),
                )
                return int(row['id'])
            cur = conn.execute(
                'INSERT INTO platform_auth_interrupts(service, blocker, status, detail, created_at) VALUES(?,?,?,?,?)',
                (svc, blk, 'pending', str(detail or ''), now),
            )
            return int(cur.lastrowid or 0)

    def resolve_interrupt(self, service: str) -> int:
        svc = str(service or '').strip().lower()
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE platform_auth_interrupts SET status='resolved', resolved_at=? WHERE service=? AND status='pending'",
                (now, svc),
            )
            return int(cur.rowcount or 0)

    def list_interrupts(self, status: str = 'pending', limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                'SELECT * FROM platform_auth_interrupts WHERE status=? ORDER BY id DESC LIMIT ?',
                (str(status or 'pending'), int(limit or 50)),
            ).fetchall()
        return [dict(r) for r in rows]
