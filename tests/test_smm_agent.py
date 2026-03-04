"""Тесты SMMAgent — 5 тестов."""

import pytest
from unittest.mock import AsyncMock

from agents.base_agent import TaskResult


class TestSMMAgent:
    @pytest.fixture
    def agent(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        from agents.smm_agent import SMMAgent
        return SMMAgent(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
        )

    def test_init(self, agent):
        assert agent.name == "smm_agent"
        assert "social_media" in agent.capabilities
        assert "scheduling" in agent.capabilities

    @pytest.mark.asyncio
    async def test_create_post(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="Amazing post about AI!")
        result = await agent.create_post("instagram", "AI tools review")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_suggest_hashtags(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="#AI #MachineLearning #Tech")
        result = await agent.suggest_hashtags("Article about AI tools", "instagram")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_schedule_post(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="Post content")
        result = await agent.schedule_post("twitter", "AI news", "2026-03-01 10:00")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_task(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="post created")
        result = await agent.execute_task("social_media", platform="instagram", content="test")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_create_post_local_fallback_without_llm(self, agent):
        agent.llm_router = None
        result = await agent.create_post("twitter", "Проверка автономного режима")
        assert result.success is True
