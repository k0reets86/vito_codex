import pytest
from unittest.mock import AsyncMock


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

    @pytest.mark.asyncio
    async def test_daily_dashboard(self, agent):
        result = await agent.daily_dashboard()
        assert result.success is True
        assert "daily_revenue" in result.output
        assert result.metadata["analytics_runtime_profile"]["health"] in {"ok", "watch"}
        assert "evidence" in result.output

    @pytest.mark.asyncio
    async def test_detect_anomalies(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="No major anomalies")
        result = await agent.detect_anomalies()
        assert result.success is True
        assert "status" in result.output
        assert "analytics_runtime_profile" in result.metadata
        assert "analytics_handoff_targets" in result.metadata

    @pytest.mark.asyncio
    async def test_forecast(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="Forecast looks stable")
        result = await agent.forecast_revenue(14)
        assert result.success is True
        assert result.output["days"] == 14
        assert result.metadata["analytics_runtime_profile"]["forecast_confidence"] in {"low", "medium", "unknown"}
