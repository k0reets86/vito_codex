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
        assert result.output["auth_state"] == "inventory"
        assert isinstance(result.output["accounts"], list)
        assert "skill_pack" in result.output

    @pytest.mark.asyncio
    async def test_check_account(self, agent):
        result = await agent.check_account("gumroad")
        assert result.success is True
        assert "skill_pack" in result.output

    @pytest.mark.asyncio
    async def test_monitor_limits(self, agent):
        result = await agent.monitor_limits()
        assert result.success is True
        assert result.output["auth_state"] == "limits_snapshot"

    @pytest.mark.asyncio
    async def test_execute_task(self, agent):
        result = await agent.execute_task("account_management")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_fetch_email_code_missing_credentials_returns_remediation(self, agent, monkeypatch):
        monkeypatch.setattr("agents.account_manager.settings.GMAIL_ADDRESS", "", raising=False)
        monkeypatch.setattr("agents.account_manager.settings.GMAIL_PASSWORD", "", raising=False)
        result = await agent.fetch_email_code()
        assert result.success is True
        assert result.output["auth_state"] == "missing_credentials"
        assert "next_actions" in result.output
