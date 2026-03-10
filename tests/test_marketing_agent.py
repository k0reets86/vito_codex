"""Тесты MarketingAgent — 5 тестов."""

import pytest
from unittest.mock import AsyncMock


class TestMarketingAgent:
    @pytest.fixture
    def agent(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        from agents.marketing_agent import MarketingAgent
        return MarketingAgent(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
        )

    def test_init(self, agent):
        assert agent.name == "marketing_agent"
        assert "marketing_strategy" in agent.capabilities
        assert "funnel" in agent.capabilities

    @pytest.mark.asyncio
    async def test_create_strategy(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="Marketing strategy: target millennials...")
        result = await agent.create_strategy("Digital Planner", "millennials", budget_usd=100)
        assert result.success is True
        assert isinstance(result.output, dict)
        assert result.output["target_audience"] == "millennials"
        assert result.metadata["marketing_runtime_profile"]["budget_profile"] in {"test_and_scale", "lean", "growth"}

    @pytest.mark.asyncio
    async def test_design_funnel(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="Funnel: awareness -> interest -> purchase")
        result = await agent.design_funnel("AI Course")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_create_ad_copy(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="Discover the ultimate planner!")
        result = await agent.create_ad_copy("Digital Planner", "facebook")
        assert result.success is True
        assert isinstance(result.output, dict)
        assert len(result.output["variants"]) == 3
        assert "experiment" in result.output

    @pytest.mark.asyncio
    async def test_execute_task(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="strategy created")
        result = await agent.execute_task("marketing_strategy", product="AI tool", target_audience="developers")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_local_fallback_without_llm(self, mock_memory, mock_finance, mock_comms):
        from agents.marketing_agent import MarketingAgent

        agent = MarketingAgent(
            llm_router=None,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
        )
        strategy = await agent.create_strategy("Planner", "creators", budget_usd=120)
        assert strategy.success is True
        assert strategy.output["target_audience"] == "creators"
        ad_copy = await agent.create_ad_copy("Planner", "facebook")
        assert ad_copy.success is True
        assert "marketing_runtime_profile" in ad_copy.metadata
