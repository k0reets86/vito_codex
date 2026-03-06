"""Тесты ECommerceAgent — 5 тестов."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from agents.base_agent import TaskResult


class TestECommerceAgent:
    @pytest.fixture
    def mock_platform(self):
        platform = MagicMock()
        platform.publish = AsyncMock(return_value={"listing_id": "123", "url": "https://example.com/123"})
        platform.get_analytics = AsyncMock(return_value={"sales": 5, "revenue": 50.0})
        platform.health_check = AsyncMock(return_value=True)
        return platform

    @pytest.fixture
    def agent(self, mock_llm_router, mock_memory, mock_finance, mock_comms, mock_platform):
        from agents.ecommerce_agent import ECommerceAgent
        return ECommerceAgent(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
            platforms={"gumroad": mock_platform},
        )

    def test_init(self, agent):
        assert agent.name == "ecommerce_agent"
        assert "listing_create" in agent.capabilities
        assert "sales_check" in agent.capabilities

    @pytest.mark.asyncio
    async def test_create_listing(self, agent, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_text("dummy", encoding="utf-8")
        result = await agent.create_listing("gumroad", {"title": "Test Product", "price": 9.99, "pdf_path": str(pdf)})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_create_listing_unknown_platform(self, agent):
        result = await agent.create_listing("unknown_platform", {"title": "Test"})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_check_sales(self, agent):
        result = await agent.check_sales("gumroad")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_create_listing_existing_update_requires_target(self, agent, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_text("dummy", encoding="utf-8")
        result = await agent.create_listing(
            "gumroad",
            {
                "title": "Test Product",
                "price": 9.99,
                "pdf_path": str(pdf),
                "allow_existing_update": True,
            },
        )
        assert result.success is False
        assert result.error == "existing_update_requires_target_id"

    @pytest.mark.asyncio
    async def test_execute_task(self, agent):
        result = await agent.execute_task("sales_check", platform="gumroad")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_create_listing_printful_allows_no_preview_files(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        from agents.ecommerce_agent import ECommerceAgent
        printful = MagicMock()
        printful.publish = AsyncMock(return_value={"platform": "printful", "status": "created", "id": "pf_1"})
        agent = ECommerceAgent(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
            platforms={"printful": printful},
        )
        result = await agent.create_listing("printful", {"sync_product": {"name": "VITO POD"}})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_create_listing_printful_needs_browser_flow_is_failure(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        from agents.ecommerce_agent import ECommerceAgent
        printful = MagicMock()
        printful.publish = AsyncMock(return_value={"platform": "printful", "status": "needs_browser_flow", "error": "restricted"})
        agent = ECommerceAgent(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
            platforms={"printful": printful},
        )
        result = await agent.create_listing("printful", {"sync_product": {"name": "VITO POD"}})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_platform_rules_sync_success(self, agent, monkeypatch):
        from agents import ecommerce_agent as module_under_test

        monkeypatch.setattr(
            module_under_test,
            "sync_platform_rules",
            lambda services=None: {"checked_count": 2, "changed_count": 1, "changes": [{"service": "etsy", "url": "https://www.etsy.com/seller-handbook"}]},
        )
        result = await agent.execute_task("platform_rules_sync", services=["etsy"])
        assert result.success is True
        assert result.output["changed_count"] == 1

    @pytest.mark.asyncio
    async def test_platform_rules_sync_failure(self, agent, monkeypatch):
        from agents import ecommerce_agent as module_under_test

        def _raise(_services=None):
            raise RuntimeError("boom")

        monkeypatch.setattr(module_under_test, "sync_platform_rules", _raise)
        result = await agent.execute_task("platform_rules_sync", services=["etsy"])
        assert result.success is False
        assert "platform_rules_sync_failed" in str(result.error)
