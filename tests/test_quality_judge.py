"""Тесты QualityJudge — 5 тестов."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from agents.base_agent import TaskResult


class TestQualityJudge:
    @pytest.fixture
    def agent(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        from agents.quality_judge import QualityJudge
        return QualityJudge(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
        )

    def test_init(self, agent):
        assert agent.name == "quality_judge"
        assert "quality_review" in agent.capabilities
        assert "content_check" in agent.capabilities

    @pytest.mark.asyncio
    async def test_review_approved(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value='{"score": 8, "feedback": "Good quality", "issues": []}')
        result = await agent.review("Great article about Python", "article")
        assert result.success is True
        assert result.output["approved"] is True
        assert result.output["score"] >= 7

    @pytest.mark.asyncio
    async def test_review_rejected(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value='{"score": 4, "feedback": "Poor quality", "issues": ["too short"]}')
        result = await agent.review("bad", "article")
        assert result.success is True
        assert result.output["approved"] is False

    @pytest.mark.asyncio
    async def test_review_llm_failure(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value=None)
        result = await agent.review("content", "article")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_execute_task(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value='{"score": 9, "feedback": "Excellent", "issues": []}')
        result = await agent.execute_task("quality_review", content="test content", content_type="article")
        assert result.success is True
