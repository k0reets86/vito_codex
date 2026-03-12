"""Тесты QualityJudge — 5 тестов."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from agents.base_agent import TaskResult
from config.settings import settings


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

    @pytest.mark.asyncio
    async def test_review_respects_runtime_threshold(self, agent, monkeypatch):
        monkeypatch.setattr(settings, "QUALITY_JUDGE_APPROVAL_THRESHOLD", 8, raising=False)
        agent.llm_router.call_llm = AsyncMock(return_value='{"score": 7, "feedback": "Good", "issues": []}')
        result = await agent.review("decent content", "article")
        assert result.success is True
        assert result.output["approved"] is False
        assert result.output["threshold"] == 8

    @pytest.mark.asyncio
    async def test_review_returns_domain_scorecard(self, agent):
        agent.llm_router.call_llm = AsyncMock(
            return_value='{"score": 8, "feedback": "Good", "issues": [], "domain_scorecard": {"completeness": 8, "evidence": 7, "compliance": 9, "readiness": 8}}'
        )
        result = await agent.review("https://example.com proof report with enough detail for listing", "product_pipeline_result")
        assert result.success is True
        assert "domain_scorecard" in result.output
        assert result.output["domain_scorecard"]["completeness"] == 8
        assert "quality_runtime_profile" in result.metadata
        assert "handoff_plan" in result.output

    @pytest.mark.asyncio
    async def test_review_blocks_low_domain_dimension(self, agent, monkeypatch):
        monkeypatch.setattr(settings, "QUALITY_JUDGE_APPROVAL_THRESHOLD", 7, raising=False)
        monkeypatch.setattr(settings, "QUALITY_JUDGE_MIN_DOMAIN_THRESHOLD", 7, raising=False)
        agent.llm_router.call_llm = AsyncMock(
            return_value='{"score": 9, "feedback": "Looks good", "issues": [], "domain_scorecard": {"completeness": 9, "evidence": 6, "compliance": 9, "readiness": 9}}'
        )
        result = await agent.review("Detailed content with proof", "article")
        assert result.success is True
        assert result.output["approved"] is False
        assert "evidence" in result.output["blocked_dimensions"]
