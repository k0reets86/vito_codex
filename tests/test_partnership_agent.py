"""Тесты PartnershipAgent — 5 тестов."""

import pytest
from unittest.mock import AsyncMock

from agents.base_agent import TaskResult


class TestPartnershipAgent:
    @pytest.fixture
    def agent(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        from agents.partnership_agent import PartnershipAgent
        return PartnershipAgent(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
        )

    def test_init(self, agent):
        assert agent.name == "partnership_agent"
        assert "partnership" in agent.capabilities
        assert "affiliate" in agent.capabilities

    @pytest.mark.asyncio
    async def test_find_affiliates(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="Affiliate programs: 1. Amazon, 2. ShareASale")
        result = await agent.find_affiliates("digital products")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_track_referrals(self, agent):
        result = await agent.track_referrals()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_propose_collaboration(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="Collaboration proposal draft")
        result = await agent.propose_collaboration("influencer_xyz")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_task(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="partnership results")
        result = await agent.execute_task("partnership", niche="AI tools")
        assert result.success is True
