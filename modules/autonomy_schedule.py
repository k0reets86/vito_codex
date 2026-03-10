from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from config.settings import settings


class AutonomyScheduleState:
    def __init__(self, sqlite_path: Optional[str] = None):
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
                CREATE TABLE IF NOT EXISTS autonomy_schedule_state (
                    hook_name TEXT PRIMARY KEY,
                    last_tick INTEGER DEFAULT 0,
                    cadence_ticks INTEGER DEFAULT 0,
                    last_run_at TEXT DEFAULT '',
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    def is_due(self, hook_name: str, current_tick: int, cadence_ticks: int) -> bool:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT last_tick FROM autonomy_schedule_state WHERE hook_name = ? LIMIT 1",
                (str(hook_name or "").strip(),),
            ).fetchone()
            if not row:
                return True
            return int(current_tick or 0) - int(row["last_tick"] or 0) >= int(cadence_ticks or 0)
        finally:
            conn.close()

    def mark_run(self, hook_name: str, current_tick: int, cadence_ticks: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO autonomy_schedule_state (hook_name, last_tick, cadence_ticks, last_run_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(hook_name) DO UPDATE SET
                    last_tick=excluded.last_tick,
                    cadence_ticks=excluded.cadence_ticks,
                    last_run_at=excluded.last_run_at,
                    updated_at=excluded.updated_at
                """,
                (str(hook_name or "").strip(), int(current_tick or 0), int(cadence_ticks or 0), now, now),
            )
            conn.commit()
        finally:
            conn.close()
