"""Тесты RiskAgent — 5 тестов."""

import pytest
from unittest.mock import AsyncMock

from agents.base_agent import TaskResult


class TestRiskAgent:
    @pytest.fixture
    def agent(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        from agents.risk_agent import RiskAgent
        return RiskAgent(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
        )

    def test_init(self, agent):
        assert agent.name == "risk_agent"
        assert "risk_assessment" in agent.capabilities
        assert "reputation" in agent.capabilities

    @pytest.mark.asyncio
    async def test_assess_risk(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value='{"risk_level": "low", "factors": [], "recommendation": "proceed"}')
        result = await agent.assess_risk("publish product on etsy")
        assert result.success is True
        assert isinstance(result.output, dict)
        assert "risk_level" in result.output
        assert "risk_runtime_profile" in result.metadata
        assert "escalation_targets" in result.output

    @pytest.mark.asyncio
    async def test_monitor_reputation(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="Reputation: positive")
        result = await agent.monitor_reputation()
        assert result.success is True
        assert result.output["status"] == "neutral"

    @pytest.mark.asyncio
    async def test_handle_complaint(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="Response: apologize and refund")
        result = await agent.handle_complaint({"type": "refund", "message": "Product not as described"})
        assert result.success is True
        assert result.output["recommended_resolution"] == "refund_or_fix_review"

    @pytest.mark.asyncio
    async def test_execute_task(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value='{"risk_level": "medium"}')
        result = await agent.execute_task("risk_assessment", action="large purchase")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_local_fallback_without_llm(self, mock_memory, mock_finance, mock_comms):
        from agents.risk_agent import RiskAgent

        agent = RiskAgent(
            llm_router=None,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
        )
        result = await agent.assess_risk("bulk automated posting")
        assert result.success is True
        assert result.output["risk_level"] in {"medium", "high"}
        assert result.metadata["risk_runtime_profile"]["block_recommended"] in {True, False}
