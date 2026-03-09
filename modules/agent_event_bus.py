from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class AgentEvent:
    event: str
    source_agent: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AgentEventBus:
    """Small in-memory event bus for inter-agent handoff traces."""

    def __init__(self, limit: int = 500):
        self.limit = max(int(limit or 500), 10)
        self._events: list[AgentEvent] = []

    async def emit(self, event: str, data: dict[str, Any] | None = None, source_agent: str = "") -> None:
        item = AgentEvent(
            event=str(event or "").strip(),
            source_agent=str(source_agent or "").strip(),
            data=dict(data or {}),
        )
        self._events.append(item)
        if len(self._events) > self.limit:
            self._events = self._events[-self.limit :]

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        size = max(int(limit or 50), 1)
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
