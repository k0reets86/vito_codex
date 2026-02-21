"""Тесты для AmazonKDPPlatform."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from platforms.amazon_kdp import AmazonKDPPlatform
from agents.base_agent import TaskResult


@pytest.fixture
def mock_browser():
    browser = MagicMock()
    browser.execute_task = AsyncMock(return_value=TaskResult(success=True, output="logged in"))
    return browser


@pytest.fixture
def kdp(mock_browser):
    return AmazonKDPPlatform(browser_agent=mock_browser)


@pytest.fixture
def kdp_no_browser():
    return AmazonKDPPlatform()


class TestKDPInit:
    def test_name(self, kdp):
        assert kdp.name == "amazon_kdp"

    def test_has_browser(self, kdp, mock_browser):
        assert kdp.browser_agent is mock_browser


class TestKDPAuth:
    @pytest.mark.asyncio
    async def test_auth_no_browser(self, kdp_no_browser):
        result = await kdp_no_browser.authenticate()
        assert result is False

    @pytest.mark.asyncio
    async def test_auth_with_browser(self, kdp):
        result = await kdp.authenticate()
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_with_browser(self, kdp):
        assert await kdp.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_no_browser(self, kdp_no_browser):
        assert await kdp_no_browser.health_check() is False


class TestKDPPublish:
    @pytest.mark.asyncio
    async def test_publish_no_browser(self, kdp_no_browser):
        result = await kdp_no_browser.publish({"title": "Book"})
        assert result["status"] == "no_browser"

    @pytest.mark.asyncio
    async def test_publish_with_browser(self, kdp):
        result = await kdp.publish({"title": "Book"})
        assert result["status"] == "published"


class TestKDPAnalytics:
    @pytest.mark.asyncio
    async def test_analytics_no_browser(self, kdp_no_browser):
        result = await kdp_no_browser.get_analytics()
        assert result["sales"] == 0
