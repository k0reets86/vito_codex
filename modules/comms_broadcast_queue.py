from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar


T = TypeVar("T")


class BroadcastQueue:
    """Serialize outbound Telegram sends without changing public API."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def run(self, factory: Callable[[], Awaitable[T]]) -> T:
        async with self._lock:
            return await factory()
