"""Тесты DocumentAgent — 5 тестов."""

import pytest
from unittest.mock import AsyncMock

from agents.base_agent import TaskResult


class TestDocumentAgent:
    @pytest.fixture
    def agent(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        from agents.document_agent import DocumentAgent
        return DocumentAgent(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
        )

    def test_init(self, agent):
        assert agent.name == "document_agent"
        assert "documentation" in agent.capabilities
        assert "knowledge_base" in agent.capabilities

    @pytest.mark.asyncio
    async def test_create_doc(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="# API Documentation\n\nEndpoints...")
        result = await agent.create_doc("API Docs", "technical", {"endpoints": ["/api/v1/products"]})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_generate_report(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="Monthly Report: revenue up 20%")
        result = await agent.generate_report("monthly", {"month": "January", "revenue": 500})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_update_knowledge_base(self, agent):
        result = await agent.update_knowledge_base("market_trends", "AI products are growing 30% YoY")
        assert result.success is True
        agent.memory.store_knowledge.assert_called()

    @pytest.mark.asyncio
    async def test_execute_task(self, agent):
        agent.llm_router.call_llm = AsyncMock(return_value="document content")
        result = await agent.execute_task("documentation", title="Test", content_type="report")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_parse_document_missing_file_returns_recovery(self, agent):
        result = await agent.parse_document("/tmp/definitely_missing_vito_doc.txt")
        assert result.success is True
        assert result.output["status"] == "source_missing"
        assert result.metadata["document_runtime_profile"]["recovery_mode"] == "needs_source_file"
