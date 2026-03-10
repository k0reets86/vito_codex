from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import settings


@dataclass
class AgentEvent:
    event: str
    source_agent: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AgentEventBus:
    """Agent handoff trace bus with in-memory cache + SQLite persistence."""

    def __init__(self, limit: int = 500, sqlite_path: str | None = None):
        self.limit = max(int(limit or 500), 10)
        self._events: list[AgentEvent] = []
        raw_path = str(sqlite_path or getattr(settings, "SQLITE_PATH", "") or "").strip()
        self._sqlite_path = Path(raw_path) if raw_path else None
        self._init_db()

    def _init_db(self) -> None:
        if not self._sqlite_path:
            return
        self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._sqlite_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event TEXT NOT NULL,
                    source_agent TEXT,
                    data_json TEXT,
                    timestamp TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_events_ts ON agent_events(timestamp DESC)"
            )
            conn.commit()

    async def emit(self, event: str, data: dict[str, Any] | None = None, source_agent: str = "") -> None:
        item = AgentEvent(
            event=str(event or "").strip(),
            source_agent=str(source_agent or "").strip(),
            data=dict(data or {}),
        )
        self._events.append(item)
        if len(self._events) > self.limit:
            self._events = self._events[-self.limit :]
        if self._sqlite_path:
            with sqlite3.connect(self._sqlite_path) as conn:
                conn.execute(
                    """
                    INSERT INTO agent_events(event, source_agent, data_json, timestamp)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        item.event,
                        item.source_agent,
                        json.dumps(item.data or {}, ensure_ascii=False),
                        item.timestamp,
                    ),
                )
                conn.commit()

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        size = max(int(limit or 50), 1)
        if self._sqlite_path and self._sqlite_path.exists():
            with sqlite3.connect(self._sqlite_path) as conn:
                rows = conn.execute(
                    """
                    SELECT event, source_agent, data_json, timestamp
                    FROM agent_events
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (size,),
                ).fetchall()
            if rows:
                return [
                    {
                        "event": event,
                        "source_agent": source_agent or "",
                        "data": json.loads(data_json or "{}"),
                        "timestamp": timestamp,
                    }
                    for event, source_agent, data_json, timestamp in reversed(rows)
                ]
        return [
            {
                "event": x.event,
                "source_agent": x.source_agent,
                "data": dict(x.data or {}),
                "timestamp": x.timestamp,
            }
            for x in self._events[-size:]
        ]

    def clear(self) -> None:
        self._events.clear()
        if self._sqlite_path and self._sqlite_path.exists():
            with sqlite3.connect(self._sqlite_path) as conn:
                conn.execute("DELETE FROM agent_events")
                conn.commit()
