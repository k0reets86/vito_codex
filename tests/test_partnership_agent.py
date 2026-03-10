import pytest
from unittest.mock import AsyncMock


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

    @pytest.mark.asyncio
    async def test_find_affiliates(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="affiliates")
        result = await agent.find_affiliates("digital templates")
        assert result.success is True
        assert len(result.output["candidates"]) >= 3
        assert result.metadata["partnership_runtime_profile"]["candidate_count"] >= 3
        assert "partnership_execution_profile" in result.metadata

    @pytest.mark.asyncio
    async def test_track_referrals(self, agent):
        result = await agent.track_referrals()
        assert result.success is True
        assert result.output["total"] == 0

    @pytest.mark.asyncio
    async def test_propose_collaboration(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="proposal")
        result = await agent.propose_collaboration("Creator Hub")
        assert result.success is True
        assert result.output["partner"] == "Creator Hub"
        assert "partnership_runtime_profile" in result.metadata
