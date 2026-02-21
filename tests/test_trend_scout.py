"""Тесты TrendScout — 6 тестов."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from agents.base_agent import TaskResult


class TestTrendScout:
    @pytest.fixture
    def agent(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        from agents.trend_scout import TrendScout
        return TrendScout(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
        )

    def test_init(self, agent):
        assert agent.name == "trend_scout"
        assert "trend_scan" in agent.capabilities
        assert "niche_research" in agent.capabilities

    @pytest.mark.asyncio
    async def test_scan_google_trends(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="Top trends: AI, crypto, wellness")
        result = await agent.scan_google_trends(["AI", "crypto"])
        assert result.success is True

    @pytest.mark.asyncio
    async def test_scan_reddit(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="Hot topics: side hustle, passive income")
        result = await agent.scan_reddit(["entrepreneur", "passive_income"])
        assert result.success is True

    @pytest.mark.asyncio
    async def test_suggest_niches(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="1. Digital planners\n2. AI prompts\n3. Templates")
        result = await agent.suggest_niches()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_task_trend_scan(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="trends data")
        result = await agent.execute_task("trend_scan", keywords=["AI"])
        assert result.success is True

    @pytest.mark.asyncio
    async def test_stores_in_memory(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="trend findings")
        await agent.scan_google_trends(["test"])
        agent.memory.store_knowledge.assert_called()
