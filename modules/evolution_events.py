from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from config.settings import settings


class EvolutionEventStore:
    def __init__(self, sqlite_path: str | Path | None = None):
        self.sqlite_path = str(sqlite_path or settings.SQLITE_PATH)
        self._ensure_schema()

    def _connect(self):
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS evolution_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'info',
                    status TEXT NOT NULL DEFAULT 'ok',
                    task_root_id TEXT DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_evolution_events_created ON evolution_events(created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_evolution_events_type ON evolution_events(event_type, created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_evolution_events_status ON evolution_events(status, created_at DESC)")
            conn.commit()
        finally:
            conn.close()

    def record_event(
        self,
        *,
        event_type: str,
        source: str,
        title: str,
        severity: str = 'info',
        status: str = 'ok',
        payload: dict[str, Any] | None = None,
        task_root_id: str = '',
    ) -> dict[str, Any]:
        row = {
            'event_type': str(event_type or '').strip()[:120],
            'source': str(source or '').strip()[:120],
            'title': str(title or '').strip()[:240],
            'severity': str(severity or 'info').strip()[:32] or 'info',
            'status': str(status or 'ok').strip()[:32] or 'ok',
            'task_root_id': str(task_root_id or '').strip()[:120],
            'payload_json': json.dumps(payload or {}, ensure_ascii=False),
        }
        conn = self._connect()
        try:
            cur = conn.execute(
                """
                INSERT INTO evolution_events(event_type, source, title, severity, status, task_root_id, payload_json)
                VALUES(:event_type, :source, :title, :severity, :status, :task_root_id, :payload_json)
                """,
                row,
            )
            conn.commit()
            out = dict(row)
            out['id'] = int(cur.lastrowid or 0)
            out['payload'] = payload or {}
            return out
        finally:
            conn.close()

    def list_events(self, limit: int = 100, event_type: str = '', status: str = '') -> list[dict[str, Any]]:
        limit = max(1, min(int(limit or 100), 500))
        clauses = []
        params: list[Any] = []
        if event_type:
            clauses.append('event_type = ?')
            params.append(str(event_type))
        if status:
            clauses.append('status = ?')
            params.append(str(status))
        where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
        conn = self._connect()
        try:
            rows = conn.execute(
                f"SELECT * FROM evolution_events {where} ORDER BY id DESC LIMIT ?",
                (*params, limit),
            ).fetchall()
            out = []
            for row in rows:
                item = dict(row)
                try:
                    item['payload'] = json.loads(item.get('payload_json') or '{}')
                except Exception:
                    item['payload'] = {}
                out.append(item)
            return out
        finally:
            conn.close()

    def summary(self, days: int = 7) -> dict[str, Any]:
        days = max(1, int(days or 7))
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT status, severity, COUNT(*) AS c
                FROM evolution_events
                WHERE created_at >= datetime('now', ?)
                GROUP BY status, severity
                """,
                (f'-{days} days',),
            ).fetchall()
            totals = {'total': 0, 'statuses': {}, 'severities': {}}
            for row in rows:
                c = int(row['c'] or 0)
                totals['total'] += c
                totals['statuses'][str(row['status'])] = totals['statuses'].get(str(row['status']), 0) + c
                totals['severities'][str(row['severity'])] = totals['severities'].get(str(row['severity']), 0) + c
            return totals
        finally:
            conn.close()
