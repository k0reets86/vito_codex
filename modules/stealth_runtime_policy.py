"""Stealth runtime policy gates and lightweight telemetry for Wave E."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from config.settings import settings


class StealthRuntimePolicy:
    def __init__(self, sqlite_path: Optional[str] = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self._init_db()

    def _conn(self):
        c = sqlite3.connect(self.sqlite_path)
        c.row_factory = sqlite3.Row
        return c

    def _init_db(self) -> None:
        conn = self._conn()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS stealth_runtime_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    risk_score REAL DEFAULT 0.0,
                    blocked INTEGER DEFAULT 0,
                    reason TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_stealth_runtime_events_created
                ON stealth_runtime_events(created_at DESC);
                """
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def evaluate_gate(
        *,
        cdp_enabled: bool,
        legal_gate_enabled: bool,
        owner_approved: bool,
    ) -> dict[str, Any]:
        if not cdp_enabled:
            return {"allowed": False, "blocked": True, "reason": "cdp_disabled", "risk_score": 0.0}
        if not legal_gate_enabled:
            return {"allowed": False, "blocked": True, "reason": "legal_gate_disabled", "risk_score": 0.3}
        if not owner_approved:
            return {"allowed": False, "blocked": True, "reason": "owner_approval_required", "risk_score": 0.5}
        return {"allowed": True, "blocked": False, "reason": "ok", "risk_score": 0.7}

    def record_event(self, *, risk_score: float, blocked: bool, reason: str) -> int:
        conn = self._conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO stealth_runtime_events (risk_score, blocked, reason, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    float(risk_score or 0.0),
                    1 if bool(blocked) else 0,
                    str(reason or "")[:120],
                    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            conn.commit()
            return int(cur.lastrowid or 0)
        finally:
            conn.close()

    def summary(self, days: int = 7) -> dict[str, Any]:
        conn = self._conn()
        try:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_events,
                    SUM(CASE WHEN blocked = 1 THEN 1 ELSE 0 END) AS blocked_events,
                    AVG(risk_score) AS avg_risk_score
                FROM stealth_runtime_events
                WHERE created_at >= datetime('now', ?)
                """,
                (f"-{max(1, int(days or 7))} days",),
            ).fetchone()
            data = dict(row) if row else {}
            total = int(data.get("total_events") or 0)
            blocked = int(data.get("blocked_events") or 0)
            avg_risk = float(data.get("avg_risk_score") or 0.0)
            blocked_rate = (blocked / float(total)) if total > 0 else 0.0
            return {
                "window_days": max(1, int(days or 7)),
                "total_events": total,
                "blocked_events": blocked,
                "blocked_rate": round(blocked_rate, 4),
                "avg_risk_score": round(avg_risk, 4),
            }
        finally:
            conn.close()
