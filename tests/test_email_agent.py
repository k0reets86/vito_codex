"""Тесты EmailAgent — 5 тестов."""

import pytest
from unittest.mock import AsyncMock

from agents.base_agent import TaskResult


class TestEmailAgent:
    @pytest.fixture
    def agent(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        from agents.email_agent import EmailAgent
        return EmailAgent(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
        )

    def test_init(self, agent):
        assert agent.name == "email_agent"
        assert "email" in agent.capabilities
        assert "newsletter" in agent.capabilities

    @pytest.mark.asyncio
    async def test_create_newsletter(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="Subject: Weekly AI News\n\nDear reader...")
        result = await agent.create_newsletter("AI trends", "tech professionals")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_create_sequence(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="Email 1: Welcome...\nEmail 2: Value...")
        result = await agent.create_sequence("onboard new users", emails_count=3)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_manage_subscribers(self, agent):
        result = await agent.manage_subscribers("list", {})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_task(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="newsletter content")
        result = await agent.execute_task("newsletter", topic="weekly digest", audience="subscribers")
        assert result.success is True
