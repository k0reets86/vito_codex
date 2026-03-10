"""System-wide LLM rate limiter with provider-scoped windows."""

from __future__ import annotations

import asyncio
import sqlite3
import time
from dataclasses import dataclass
from typing import Any

from config.logger import get_logger
from config.settings import settings

logger = get_logger("llm_rate_limiter", agent="llm_rate_limiter")


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    wait_seconds: float
    reason: str


class LLMRateLimiter:
    def __init__(self, sqlite_path: str | None = None):
        self._sqlite_path = sqlite_path or settings.SQLITE_PATH
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()
        self._init_tables()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._sqlite_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_tables(self) -> None:
        conn = self._get_conn()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_rate_limit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                task_type TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_llm_rate_limit_window
            ON llm_rate_limit_log(provider, created_at)
            """
        )
        conn.commit()

    @staticmethod
    def _provider_limit(provider: str) -> int:
        mapping = {
            "google": int(getattr(settings, "LLM_RATE_LIMIT_GOOGLE_RPM", 15) or 15),
            "openai": int(getattr(settings, "LLM_RATE_LIMIT_OPENAI_RPM", 60) or 60),
            "anthropic": int(getattr(settings, "LLM_RATE_LIMIT_ANTHROPIC_RPM", 60) or 60),
            "perplexity": int(getattr(settings, "LLM_RATE_LIMIT_PERPLEXITY_RPM", 30) or 30),
            "openrouter": int(getattr(settings, "LLM_RATE_LIMIT_OPENROUTER_RPM", 60) or 60),
        }
        return max(1, int(mapping.get(str(provider or "").strip().lower(), 30) or 30))

    def _prune(self, provider: str, now: float) -> None:
        cutoff = now - 60.0
        conn = self._get_conn()
        conn.execute(
            "DELETE FROM llm_rate_limit_log WHERE provider = ? AND created_at < ?",
            (provider, cutoff),
        )
        conn.commit()

    def peek(self, provider: str) -> RateLimitDecision:
        provider_key = str(provider or "").strip().lower()
        now = time.monotonic()
        self._prune(provider_key, now)
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT created_at FROM llm_rate_limit_log WHERE provider = ? ORDER BY created_at ASC",
            (provider_key,),
        ).fetchall()
        limit = self._provider_limit(provider_key)
        count = len(rows)
        if count < limit:
            return RateLimitDecision(True, 0.0, "ok")
        oldest = float(rows[0]["created_at"])
        wait_seconds = max(0.0, 60.0 - (now - oldest))
        return RateLimitDecision(False, wait_seconds, f"rpm_limit:{provider_key}:{limit}")

    def mark(self, provider: str, model: str, task_type: str) -> None:
        provider_key = str(provider or "").strip().lower()
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO llm_rate_limit_log (provider, model, task_type, created_at) VALUES (?, ?, ?, ?)",
            (provider_key, str(model or ""), str(task_type or ""), time.monotonic()),
        )
        conn.commit()

    async def wait_for_slot(self, provider: str, model: str, task_type: str) -> RateLimitDecision:
        provider_key = str(provider or "").strip().lower()
        async with self._lock:
            decision = self.peek(provider_key)
            raw_max_wait = getattr(settings, "LLM_RATE_LIMIT_MAX_WAIT_SEC", 60)
            try:
                max_wait = max(0, int(raw_max_wait))
            except Exception:
                max_wait = 60
            if not decision.allowed:
                if decision.wait_seconds > max_wait:
                    logger.warning(
                        "llm_rate_limit_blocked",
                        extra={
                            "event": "llm_rate_limit_blocked",
                            "context": {
                                "provider": provider_key,
                                "wait_seconds": round(decision.wait_seconds, 2),
                                "reason": decision.reason,
                            },
                        },
                    )
                    return decision
                logger.info(
                    "llm_rate_limit_wait",
                    extra={
                        "event": "llm_rate_limit_wait",
                        "context": {
                            "provider": provider_key,
                            "wait_seconds": round(decision.wait_seconds, 2),
                        },
                    },
                )
                await asyncio.sleep(decision.wait_seconds)
            self.mark(provider_key, model, task_type)
            return RateLimitDecision(True, 0.0, "ok")

    def stats(self) -> dict[str, Any]:
        conn = self._get_conn()
        out: dict[str, Any] = {}
        for provider in ("google", "openai", "anthropic", "perplexity", "openrouter"):
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM llm_rate_limit_log WHERE provider = ? AND created_at >= ?",
                (provider, time.monotonic() - 60.0),
            ).fetchone()
            out[provider] = {
                "rpm_limit": self._provider_limit(provider),
                "recent_calls": int((row["n"] if row and "n" in row.keys() else 0) or 0),
            }
        return out
