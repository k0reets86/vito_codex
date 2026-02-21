"""Тесты BrowserAgent — 6 тестов."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.base_agent import TaskResult


class TestBrowserAgent:
    @pytest.fixture
    def agent(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        from agents.browser_agent import BrowserAgent
        # Reset singleton for test isolation
        BrowserAgent._instance = None
        BrowserAgent._browser = None
        BrowserAgent._playwright_inst = None
        return BrowserAgent(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
        )

    def test_init(self, agent):
        assert agent.name == "browser_agent"
        assert "browse" in agent.capabilities
        assert "web_scrape" in agent.capabilities
        assert "form_fill" in agent.capabilities

    @pytest.mark.asyncio
    async def test_start_stop(self, agent):
        mock_context = AsyncMock()
        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_pw_factory = MagicMock()
        mock_pw_factory.return_value.start = AsyncMock(return_value=mock_pw)

        with patch("playwright.async_api.async_playwright", mock_pw_factory):
            await agent.start()
        status = agent.get_status()
        assert status["status"] == "idle"
        await agent.stop()
        assert agent.get_status()["status"] == "stopped"

    @pytest.mark.asyncio
    async def test_navigate(self, agent):
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(return_value=MagicMock(status=200))
        mock_page.title = AsyncMock(return_value="Test Page")
        mock_page.url = "https://example.com"
        mock_page.close = AsyncMock()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        agent._context = mock_context
        with patch.object(agent, '_ensure_browser', new_callable=AsyncMock):
            result = await agent.navigate("https://example.com")
            assert result.success is True

    @pytest.mark.asyncio
    async def test_extract_text(self, agent):
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.inner_text = AsyncMock(return_value="Page content here")
        mock_page.close = AsyncMock()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        agent._context = mock_context
        with patch.object(agent, '_ensure_browser', new_callable=AsyncMock):
            result = await agent.extract_text("https://example.com")
            assert result.success is True
            assert "Page content" in result.output

    @pytest.mark.asyncio
    async def test_execute_task_browse(self, agent):
        with patch.object(agent, 'navigate', new_callable=AsyncMock) as mock_nav:
            mock_nav.return_value = TaskResult(success=True, output="navigated")
            result = await agent.execute_task("browse", url="https://example.com")
            assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_task_unknown(self, agent):
        result = await agent.execute_task("unknown_task")
        assert result.success is False
