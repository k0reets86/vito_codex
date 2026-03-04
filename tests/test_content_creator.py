"""Тесты ContentCreator — 6 тестов."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from agents.base_agent import TaskResult


class TestContentCreator:
    @pytest.fixture
    def agent(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        from agents.content_creator import ContentCreator
        return ContentCreator(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
        )

    def test_init(self, agent):
        assert agent.name == "content_creator"
        assert "content_creation" in agent.capabilities
        assert "article" in agent.capabilities
        assert "ebook" in agent.capabilities

    @pytest.mark.asyncio
    async def test_create_article(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="# Great Article\n\nContent here...")
        result = await agent.create_article("Python tips")
        assert result.success is True
        assert result.output is not None

    @pytest.mark.asyncio
    async def test_create_ebook(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="Chapter content...")
        result = await agent.create_ebook("Python Guide", chapters=3)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_create_product_description(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="Amazing product description")
        result = await agent.create_product_description("Digital Planner", "etsy")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_task_content_creation(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="created content")
        result = await agent.execute_task("content_creation", topic="AI guide")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_llm_failure(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value=None)
        result = await agent.create_article("topic")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_create_turnkey_product_local(self, agent):
        agent.llm_router = None
        result = await agent.create_turnkey_product("AI Etsy Starter Kit", platform="gumroad", price=9)
        assert result.success is True
        assert result.output.get("files", {}).get("listing_json")
