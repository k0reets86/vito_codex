from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
from pathlib import Path
from typing import Any

from config.settings import settings


class EvolutionAuditTrail:
    def __init__(self, sqlite_path: str | Path | None = None, secret: str | None = None):
        self.sqlite_path = str(sqlite_path or settings.SQLITE_PATH)
        self.secret = str(secret or getattr(settings, 'EVOLUTION_AUDIT_SECRET', '') or 'vito-evolution-audit-default')
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
                CREATE TABLE IF NOT EXISTS evolution_apply_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    snapshot_id TEXT DEFAULT '',
                    task_root_id TEXT DEFAULT '',
                    files_json TEXT NOT NULL DEFAULT '[]',
                    success INTEGER NOT NULL DEFAULT 0,
                    details TEXT DEFAULT '',
                    signature TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_evolution_apply_audit_created ON evolution_apply_audit(created_at DESC)")
            conn.commit()
        finally:
            conn.close()

    def _sign(self, payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode('utf-8')
        return hmac.new(self.secret.encode('utf-8'), raw, hashlib.sha256).hexdigest()

    def record(self, *, event_type: str, snapshot_id: str = '', task_root_id: str = '', files: list[str] | None = None, success: bool = False, details: str = '') -> dict[str, Any]:
        payload = {
            'event_type': str(event_type or '').strip()[:120],
            'snapshot_id': str(snapshot_id or '').strip()[:120],
            'task_root_id': str(task_root_id or '').strip()[:120],
            'files': [str(x)[:300] for x in list(files or [])[:200]],
            'success': bool(success),
            'details': str(details or '')[:2000],
        }
        signature = self._sign(payload)
        conn = self._connect()
        try:
            cur = conn.execute(
                """
                INSERT INTO evolution_apply_audit(event_type, snapshot_id, task_root_id, files_json, success, details, signature)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload['event_type'],
                    payload['snapshot_id'],
                    payload['task_root_id'],
                    json.dumps(payload['files'], ensure_ascii=False),
                    1 if payload['success'] else 0,
                    payload['details'],
                    signature,
                ),
            )
            conn.commit()
            payload['id'] = int(cur.lastrowid or 0)
            payload['signature'] = signature
            return payload
        finally:
            conn.close()

    def list_entries(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit or 100), 500))
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM evolution_apply_audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            out = []
            for row in rows:
                item = dict(row)
                try:
                    item['files'] = json.loads(item.get('files_json') or '[]')
                except Exception:
                    item['files'] = []
                item['signature_ok'] = self.verify_entry(item)
                out.append(item)
            return out
        finally:
            conn.close()

    def verify_entry(self, entry: dict[str, Any]) -> bool:
        payload = {
            'event_type': str(entry.get('event_type') or '').strip()[:120],
            'snapshot_id': str(entry.get('snapshot_id') or '').strip()[:120],
            'task_root_id': str(entry.get('task_root_id') or '').strip()[:120],
            'files': [str(x)[:300] for x in list(entry.get('files') or [])[:200]],
            'success': bool(entry.get('success')),
            'details': str(entry.get('details') or '')[:2000],
        }
        expected = self._sign(payload)
        return hmac.compare_digest(expected, str(entry.get('signature') or ''))
