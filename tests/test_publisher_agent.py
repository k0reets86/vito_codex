"""Тесты PublisherAgent — 5 тестов."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from agents.base_agent import TaskResult


class TestPublisherAgent:
    @pytest.fixture
    def mock_quality_judge(self):
        judge = MagicMock()
        judge.review = AsyncMock(return_value=TaskResult(
            success=True,
            output={"score": 8, "feedback": "Good", "approved": True},
        ))
        return judge

    @pytest.fixture
    def mock_wp_platform(self):
        wp = MagicMock()
        wp.publish = AsyncMock(return_value={"post_id": "456", "url": "https://blog.example.com/post"})
        wp.health_check = AsyncMock(return_value=True)
        return wp

    @pytest.fixture
    def agent(self, mock_llm_router, mock_memory, mock_finance, mock_comms, mock_quality_judge, mock_wp_platform):
        from agents.publisher_agent import PublisherAgent
        return PublisherAgent(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
            quality_judge=mock_quality_judge,
            platforms={"wordpress": mock_wp_platform},
        )

    def test_init(self, agent):
        assert agent.name == "publisher_agent"
        assert "publish" in agent.capabilities
        assert "wordpress" in agent.capabilities

    @pytest.mark.asyncio
    async def test_publish_wordpress(self, agent):
        result = await agent.publish_wordpress("Test Post", "Content here", tags=["test"])
        assert result.success is True

    @pytest.mark.asyncio
    async def test_publish_rejected_by_quality(self, agent):
        agent.quality_judge.review = AsyncMock(return_value=TaskResult(
            success=True,
            output={"score": 3, "feedback": "Poor quality", "approved": False},
        ))
        result = await agent.publish_wordpress("Bad Post", "Bad content")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_publish_no_platform(self, agent):
        result = await agent.publish_medium("Title", "Content")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_execute_task(self, agent):
        result = await agent.execute_task("publish", platform="wordpress", title="Test", content="Content")
        assert result.success is True
