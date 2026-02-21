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


@pytest.fixture
def mock_llm_router():
    """Мок LLMRouter для тестов агентов."""
    router = MagicMock()
    router.call_llm = AsyncMock(return_value="mocked LLM response")
    router.select_model = MagicMock()
    router.get_daily_spend = MagicMock(return_value=0.0)
    router.check_daily_limit = MagicMock(return_value=True)
    return router


@pytest.fixture
def mock_memory():
    """Мок MemoryManager для тестов агентов."""
    mem = MagicMock()
    mem.store_knowledge = MagicMock()
    mem.search_knowledge = MagicMock(return_value=[])
    mem.save_skill = MagicMock()
    mem.get_skill = MagicMock(return_value=None)
    mem.log_error = MagicMock()
    mem.save_pattern = MagicMock()
    mem.store_episode = AsyncMock()
    mem.store_to_datalake = AsyncMock()
    mem.search_episodes = AsyncMock(return_value=[])
    return mem


@pytest.fixture
def mock_finance():
    """Мок FinancialController для тестов агентов."""
    fin = MagicMock()
    fin.record_expense = MagicMock(return_value=1)
    fin.record_income = MagicMock(return_value=1)
    fin.check_expense = MagicMock(return_value={"allowed": True, "action": "auto", "reason": "ok"})
    fin.get_daily_spent = MagicMock(return_value=0.0)
    fin.get_daily_earned = MagicMock(return_value=0.0)
    fin.get_spend_by_agent = MagicMock(return_value=[])
    fin.get_spend_by_category = MagicMock(return_value=[])
    fin.get_product_roi = MagicMock(return_value=[])
    fin.get_pnl = MagicMock(return_value={"total_expenses": 0, "total_income": 0, "net_profit": 0, "profitable": False})
    fin.format_morning_finance = MagicMock(return_value="Finance OK")
    return fin


@pytest.fixture
def mock_comms():
    """Мок CommsAgent для тестов агентов."""
    comms = MagicMock()
    comms.send_message = AsyncMock(return_value=True)
    comms.send_file = AsyncMock(return_value=True)
    comms.request_approval = AsyncMock(return_value=True)
    comms.send_morning_report = AsyncMock(return_value=True)
    comms.notify_error = AsyncMock(return_value=True)
    return comms
