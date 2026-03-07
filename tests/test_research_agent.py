"""Тесты ResearchAgent — 5 тестов."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from agents.base_agent import TaskResult


class TestResearchAgent:
    @pytest.fixture
    def agent(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        from agents.research_agent import ResearchAgent
        return ResearchAgent(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
        )

    def test_init(self, agent):
        assert agent.name == "research_agent"
        assert "research" in agent.capabilities
        assert "competitor_analysis" in agent.capabilities

    @pytest.mark.asyncio
    async def test_deep_research(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value=(
            "## Executive Summary\nResearch findings on topic X\n\n"
            "```json\n"
            "{\"topic\":\"digital products market\",\"overall_score\":84,"
            "\"recommended_product\":{\"title\":\"AI Prompt Pack\",\"score\":84,\"platform\":\"gumroad\",\"format\":\"pdf\",\"price_band\":\"$9-$19\",\"why_now\":\"clear demand\",\"buyer\":\"creators\"},"
            "\"top_ideas\":[{\"rank\":1,\"title\":\"AI Prompt Pack\",\"score\":84,\"platform\":\"gumroad\",\"format\":\"pdf\",\"price_band\":\"$9-$19\",\"why_now\":\"clear demand\",\"buyer\":\"creators\"}]}\n"
            "```"
        ))
        result = await agent.deep_research("digital products market")
        assert result.success is True
        assert result.output is not None
        assert "## Sources" in result.output
        assert "## Confidence Score" in result.output
        assert result.metadata["overall_score"] == 84
        assert result.metadata["recommended_product"]["title"] == "AI Prompt Pack"
        assert result.metadata["top_ideas"][0]["platform"] == "gumroad"

    @pytest.mark.asyncio
    async def test_competitor_analysis(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="Competitor A, Competitor B...")
        result = await agent.competitor_analysis("etsy templates")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_market_analysis(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="Market size: $1B...")
        result = await agent.market_analysis("digital planners")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_task_research(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="findings")
        result = await agent.execute_task("research", topic="AI trends")
        assert result.success is True
