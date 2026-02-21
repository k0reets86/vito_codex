"""Общие фикстуры для тестов VITO."""

import logging
import os
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Подменяем переменные окружения ДО импорта модулей
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_OWNER_CHAT_ID", "123456")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("DAILY_LIMIT_USD", "10")
os.environ.setdefault("OPERATION_NOTIFY_USD", "20")
os.environ.setdefault("OPERATION_APPROVE_USD", "50")

# Сбрасываем глобальную LogRecordFactory чтобы избежать конфликтов
# с extra={"agent": ...} в тестах
logging.setLogRecordFactory(logging.LogRecord)


@pytest.fixture
def tmp_sqlite(tmp_path):
    """Временная SQLite база для тестов."""
    return str(tmp_path / "test.db")


@pytest.fixture
def mock_pg_pool():
    """Мок PostgreSQL pool с async context manager."""
    pool = MagicMock()
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value={"id": 1})

    acm = MagicMock()
    acm.__aenter__ = AsyncMock(return_value=conn)
    acm.__aexit__ = AsyncMock(return_value=False)
    pool.acquire.return_value = acm
    pool.close = AsyncMock()
    return pool
