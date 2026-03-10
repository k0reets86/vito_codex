import pytest
from unittest.mock import AsyncMock


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

    @pytest.mark.asyncio
    async def test_create_newsletter(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="newsletter")
        result = await agent.create_newsletter("AI launch", "creators")
        assert result.success is True
        assert "subject" in result.output
        assert result.metadata["email_runtime_profile"]["mode"] == "single_send"

    @pytest.mark.asyncio
    async def test_create_sequence(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="sequence")
        result = await agent.create_sequence("conversion", 3)
        assert result.success is True
        assert len(result.output["emails"]) == 3
        assert result.metadata["email_runtime_profile"]["mode"] == "sequence"

    @pytest.mark.asyncio
    async def test_manage_subscribers(self, agent):
        added = await agent.manage_subscribers("add", {"email": "a@b.com"})
        assert added.success is True
        listed = await agent.manage_subscribers("list", {})
        assert listed.output["total"] == 1
        assert "email_runtime_profile" in listed.metadata
