"""Тесты EconomicsAgent — 5 тестов."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from agents.base_agent import TaskResult


class TestEconomicsAgent:
    @pytest.fixture
    def agent(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        from agents.economics_agent import EconomicsAgent
        return EconomicsAgent(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
        )

    def test_init(self, agent):
        assert agent.name == "economics_agent"
        assert "pricing" in agent.capabilities
        assert "unit_economics" in agent.capabilities

    @pytest.mark.asyncio
    async def test_suggest_price(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="Suggested price: $19.99")
        result = await agent.suggest_price("Digital Planner")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_unit_economics(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="CAC: $5, LTV: $50, margin: 80%")
        result = await agent.unit_economics("AI Prompt Pack")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_model_pnl(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="Scenario: revenue $1000, costs $200")
        result = await agent.model_pnl({"product": "ebook", "price": 15, "units": 100})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_task(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="pricing analysis")
        result = await agent.execute_task("pricing", product="test product")
        assert result.success is True
