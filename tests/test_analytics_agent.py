"""Тесты AnalyticsAgent — 5 тестов."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from agents.base_agent import TaskResult


class TestAnalyticsAgent:
    @pytest.fixture
    def agent(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        from agents.analytics_agent import AnalyticsAgent
        return AnalyticsAgent(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
        )

    def test_init(self, agent):
        assert agent.name == "analytics_agent"
        assert "analytics" in agent.capabilities
        assert "dashboard" in agent.capabilities
        assert "forecast" in agent.capabilities

    @pytest.mark.asyncio
    async def test_daily_dashboard(self, agent):
        result = await agent.daily_dashboard()
        assert result.success is True
        assert result.output is not None

    @pytest.mark.asyncio
    async def test_detect_anomalies(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="No anomalies detected")
        result = await agent.detect_anomalies()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_forecast_revenue(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="Forecast: $500 in 30 days")
        result = await agent.forecast_revenue(days=30)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_task(self, agent):
        result = await agent.execute_task("dashboard")
        assert result.success is True
