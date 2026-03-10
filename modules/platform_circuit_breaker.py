"""Durable platform circuit breaker for repeated execution failures."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from config.settings import settings


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class PlatformBreakerState:
    platform: str
    is_open: bool
    consecutive_failures: int
    open_until: str
    last_error: str


class PlatformCircuitBreaker:
    def __init__(self, sqlite_path: str | None = None):
        self.sqlite_path = sqlite_path or settings.SQLITE_PATH
        self.fail_threshold = max(1, int(getattr(settings, "PLATFORM_CIRCUIT_BREAKER_FAIL_THRESHOLD", 3) or 3))
        self.cooldown_sec = max(60, int(getattr(settings, "PLATFORM_CIRCUIT_BREAKER_COOLDOWN_SEC", 1800) or 1800))
        self.long_cooldown_sec = max(
            self.cooldown_sec,
            int(getattr(settings, "PLATFORM_CIRCUIT_BREAKER_LONG_COOLDOWN_SEC", 21600) or 21600),
        )
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._conn()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS platform_circuit_breakers (
                platform TEXT PRIMARY KEY,
                consecutive_failures INTEGER DEFAULT 0,
                open_until TEXT DEFAULT '',
                last_error TEXT DEFAULT '',
                last_failure_at TEXT DEFAULT '',
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()
        conn.close()

    @staticmethod
    def _parse_ts(raw: str) -> datetime | None:
        try:
            if raw:
                return datetime.fromisoformat(raw)
        except Exception:
            return None
        return None

    def state(self, platform: str) -> PlatformBreakerState:
        key = str(platform or "").strip().lower()
        conn = self._conn()
        row = conn.execute(
            """
            SELECT platform, consecutive_failures, open_until, last_error
            FROM platform_circuit_breakers
            WHERE platform=?
            """,
            (key,),
        ).fetchone()
        conn.close()
        if not row:
            return PlatformBreakerState(platform=key, is_open=False, consecutive_failures=0, open_until="", last_error="")
        open_until = str(row["open_until"] or "")
        dt = self._parse_ts(open_until)
        return PlatformBreakerState(
            platform=key,
            is_open=bool(dt and dt > _utc_now()),
            consecutive_failures=int(row["consecutive_failures"] or 0),
            open_until=open_until,
            last_error=str(row["last_error"] or ""),
        )

    def allow(self, platform: str) -> tuple[bool, str]:
        st = self.state(platform)
        if not st.is_open:
            return True, ""
        return False, f"platform_circuit_open_until:{st.open_until}"

    def _cooldown_for_error(self, error: str) -> int:
        txt = str(error or "").lower()
        for token in ("daily_limit", "cloudflare", "captcha", "rate_limit", "anti-spam", "too many"):
            if token in txt:
                return self.long_cooldown_sec
        return self.cooldown_sec

    def record_success(self, platform: str) -> None:
        key = str(platform or "").strip().lower()
        conn = self._conn()
        conn.execute(
            """
            INSERT INTO platform_circuit_breakers(platform, consecutive_failures, open_until, last_error, last_failure_at, updated_at)
            VALUES (?, 0, '', '', '', datetime('now'))
            ON CONFLICT(platform) DO UPDATE SET
                consecutive_failures=0,
                open_until='',
                last_error='',
                last_failure_at='',
                updated_at=datetime('now')
            """,
            (key,),
        )
        conn.commit()
        conn.close()

    def record_failure(self, platform: str, error: str) -> PlatformBreakerState:
        prev = self.state(platform)
        failures = int(prev.consecutive_failures or 0) + 1
        open_until = ""
        if failures >= self.fail_threshold:
            open_until = (_utc_now() + timedelta(seconds=self._cooldown_for_error(error))).isoformat()
        key = str(platform or "").strip().lower()
        conn = self._conn()
        conn.execute(
            """
            INSERT INTO platform_circuit_breakers(platform, consecutive_failures, open_until, last_error, last_failure_at, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(platform) DO UPDATE SET
                consecutive_failures=excluded.consecutive_failures,
                open_until=excluded.open_until,
                last_error=excluded.last_error,
                last_failure_at=excluded.last_failure_at,
                updated_at=datetime('now')
            """,
            (key, failures, open_until, str(error or "")[:500], _utc_now().isoformat()),
        )
        conn.commit()
        conn.close()
        return self.state(platform)
