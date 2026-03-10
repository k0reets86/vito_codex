from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

try:
    from telethon import TelegramClient, events
except Exception:  # pragma: no cover - optional runtime dependency
    TelegramClient = None
    events = None


@dataclass
class TestResult:
    test_id: str
    command: str
    success: bool
    response: str
    response_time: float
    expected_keyword: str = ""
    error: str = ""
    log_snippet: str = ""


class VITOTesterClient:
    """MTProto user-client wrapper for owner-style Telegram tests."""

    def __init__(
        self,
        *,
        session_name: str = "vito_tester_session",
        api_id: int | None = None,
        api_hash: str | None = None,
        bot_username: str | None = None,
        client_factory: Any | None = None,
    ) -> None:
        import os

        self.session_name = session_name
        self.api_id = int(api_id or os.getenv("TG_API_ID", "0"))
        self.api_hash = api_hash or os.getenv("TG_API_HASH", "")
        self.bot_username = (bot_username or os.getenv("VITO_BOT_USERNAME", "")).lstrip("@")
        self._client_factory = client_factory
        self._client = None
        self._bot_entity = None
        self._response_queue: asyncio.Queue[str] = asyncio.Queue()

    @property
    def session_path(self) -> Path:
        return Path(f"{self.session_name}.session")

    def _build_client(self):
        if self._client_factory is not None:
            return self._client_factory(self.session_name, self.api_id, self.api_hash)
        if TelegramClient is None:
            raise RuntimeError(
                "telethon is not installed. Install requirements_tester.txt or inject client_factory."
            )
        return TelegramClient(self.session_name, self.api_id, self.api_hash)

    async def start(self) -> None:
        if not self.bot_username:
            raise RuntimeError("VITO_BOT_USERNAME is not configured")
        self._client = self._build_client()
        await self._client.start()
        self._bot_entity = await self._client.get_entity(self.bot_username)

        if events is not None:
            @self._client.on(events.NewMessage(from_users=self._bot_entity))
            async def _handler(event):
                text = getattr(getattr(event, "message", None), "text", "") or ""
                await self._response_queue.put(text)

    async def send(self, message: str) -> None:
        if self._client is None or self._bot_entity is None:
            raise RuntimeError("VITOTesterClient is not started")
        await self._client.send_message(self._bot_entity, message)

    async def clear_responses(self) -> None:
        while not self._response_queue.empty():
            try:
                self._response_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def wait_response(self, *, timeout: int = 30, collect_all: bool = False) -> str:
        started = time.time()
        collected: list[str] = []
        while True:
            remaining = timeout - (time.time() - started)
            if remaining <= 0:
                break
            try:
                msg = await asyncio.wait_for(self._response_queue.get(), timeout=min(remaining, 2.0))
            except asyncio.TimeoutError:
                if collected:
                    break
                continue
            collected.append(msg)
            if not collect_all:
                break
        return "\n".join(collected)

    async def run_test(
        self,
        *,
        test_id: str,
        command: str,
        expected_keyword: str,
        timeout: int = 30,
        inverted: bool = False,
        collect_all: bool = False,
    ) -> TestResult:
        await self.clear_responses()
        started = time.time()
        await self.send(command)
        response = await self.wait_response(timeout=timeout, collect_all=collect_all)
        elapsed = round(time.time() - started, 2)
        normalized = response.lower()
        expected = expected_keyword.lower()
        if expected:
            found = expected in normalized
            success = (not found) if inverted else found
            if not success:
                polarity = "NOT " if inverted else ""
                error = f'Expected {polarity}"{expected_keyword}" in response'
            else:
                error = ""
        else:
            success = bool(response.strip())
            error = "" if success else "Expected any non-empty response"
        return TestResult(
            test_id=test_id,
            command=command,
            success=success,
            response=response,
            response_time=elapsed,
            expected_keyword=expected_keyword,
            error=error,
        )

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.disconnect()
            self._client = None
            self._bot_entity = None
