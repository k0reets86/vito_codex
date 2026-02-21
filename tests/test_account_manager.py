"""Тесты AccountManager — 5 тестов."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from agents.base_agent import TaskResult


class TestAccountManager:
    @pytest.fixture
    def agent(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        from agents.account_manager import AccountManager
        return AccountManager(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
        )

    def test_init(self, agent):
        assert agent.name == "account_manager"
        assert "account_management" in agent.capabilities

    @pytest.mark.asyncio
    async def test_list_accounts(self, agent):
        result = await agent.list_accounts()
        assert result.success is True
        assert isinstance(result.output, list)

    @pytest.mark.asyncio
    async def test_check_account(self, agent):
        result = await agent.check_account("gumroad")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_monitor_limits(self, agent):
        result = await agent.monitor_limits()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_task(self, agent):
        result = await agent.execute_task("account_management")
        assert result.success is True
