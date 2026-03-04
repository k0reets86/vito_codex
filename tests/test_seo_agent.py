"""Тесты SEOAgent — 5 тестов."""

import pytest
from unittest.mock import AsyncMock

from agents.base_agent import TaskResult


class TestSEOAgent:
    @pytest.fixture
    def agent(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        from agents.seo_agent import SEOAgent
        return SEOAgent(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
        )

    def test_init(self, agent):
        assert agent.name == "seo_agent"
        assert "seo" in agent.capabilities
        assert "keyword_research" in agent.capabilities

    @pytest.mark.asyncio
    async def test_keyword_research(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="Keywords: python tutorial, learn python, python basics")
        result = await agent.keyword_research("python programming")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_optimize_content(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="Optimized content with keywords")
        result = await agent.optimize_content("Original article", ["python", "tutorial"])
        assert result.success is True

    @pytest.mark.asyncio
    async def test_generate_meta(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value='{"title": "Best Python Guide", "description": "Learn Python"}')
        result = await agent.generate_meta("Article about Python", ["python"])
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_task(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="seo results")
        result = await agent.execute_task("keyword_research", topic="AI tools")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_listing_seo_pack(self, agent):
        result = await agent.listing_seo_pack(
            platform="gumroad",
            title="AI Prompt Bundle for Creators",
            description="Ready-to-use prompts and templates for content and product launches.",
            tags=["ai", "prompts"],
        )
        assert result.success is True
