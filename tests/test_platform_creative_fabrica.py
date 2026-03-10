"""Тесты для CreativeFabricaPlatform."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from platforms.creative_fabrica import CreativeFabricaPlatform
from agents.base_agent import TaskResult


@pytest.fixture
def mock_browser():
    browser = MagicMock()
    browser.execute_task = AsyncMock(return_value=TaskResult(success=True, output="ok"))
    return browser


@pytest.fixture
def cf(mock_browser):
    return CreativeFabricaPlatform(browser_agent=mock_browser)


@pytest.fixture
def cf_no_browser():
    return CreativeFabricaPlatform()


class TestCFInit:
    def test_name(self, cf):
        assert cf.name == "creative_fabrica"


class TestCFAuth:
    @pytest.mark.asyncio
    async def test_auth_no_browser(self, cf_no_browser):
        result = await cf_no_browser.authenticate()
        assert result is False

    @pytest.mark.asyncio
    async def test_auth_with_browser(self, cf):
        result = await cf.authenticate()
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check(self, cf):
        assert await cf.health_check() is True


class TestCFPublish:
    @pytest.mark.asyncio
    async def test_publish_no_browser(self, cf_no_browser):
        result = await cf_no_browser.publish({"title": "Design"})
        assert result["status"] == "no_browser"

    @pytest.mark.asyncio
    async def test_publish_with_browser(self, cf):
        result = await cf.publish({"title": "Design"})
        assert result["status"] == "draft"


class TestCFAnalytics:
    @pytest.mark.asyncio
    async def test_analytics_no_browser(self, cf_no_browser):
        result = await cf_no_browser.get_analytics()
        assert result["sales"] == 0
