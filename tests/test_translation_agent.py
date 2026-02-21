"""Тесты TranslationAgent — 5 тестов."""

import pytest
from unittest.mock import AsyncMock

from agents.base_agent import TaskResult


class TestTranslationAgent:
    @pytest.fixture
    def agent(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        from agents.translation_agent import TranslationAgent
        return TranslationAgent(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
        )

    def test_init(self, agent):
        assert agent.name == "translation_agent"
        assert "translate" in agent.capabilities
        assert "localize" in agent.capabilities

    @pytest.mark.asyncio
    async def test_translate(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="Translated text in German")
        result = await agent.translate("Hello world", "en", "de")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_detect_language(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="en")
        result = await agent.detect_language("Hello world")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_localize_listing(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="Localized listing data")
        result = await agent.localize_listing({"title": "Digital Planner", "description": "Great planner"}, "de")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_task(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="translated text")
        result = await agent.execute_task("translate", text="Hello", source_lang="en", target_lang="de")
        assert result.success is True
