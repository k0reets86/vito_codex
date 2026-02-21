"""Тесты LegalAgent — 5 тестов."""

import pytest
from unittest.mock import AsyncMock

from agents.base_agent import TaskResult


class TestLegalAgent:
    @pytest.fixture
    def agent(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        from agents.legal_agent import LegalAgent
        return LegalAgent(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
        )

    def test_init(self, agent):
        assert agent.name == "legal_agent"
        assert "legal" in agent.capabilities
        assert "copyright" in agent.capabilities
        assert "gdpr" in agent.capabilities

    @pytest.mark.asyncio
    async def test_check_tos(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="TOS compliant: yes")
        result = await agent.check_tos("etsy")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_check_copyright(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="No copyright issues detected")
        result = await agent.check_copyright("Original content about Python")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_gdpr_audit(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="GDPR audit: compliant")
        result = await agent.gdpr_audit()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_task(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="legal check done")
        result = await agent.execute_task("legal", action="check_tos", platform="gumroad")
        assert result.success is True
