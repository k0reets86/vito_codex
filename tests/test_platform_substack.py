"""Тесты для SubstackPlatform."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from platforms.substack import SubstackPlatform
from agents.base_agent import TaskResult


@pytest.fixture
def mock_browser():
    browser = MagicMock()
    browser.execute_task = AsyncMock(return_value=TaskResult(success=True, output="ok"))
    return browser


@pytest.fixture
def substack(mock_browser):
    return SubstackPlatform(browser_agent=mock_browser)


@pytest.fixture
def substack_no_browser():
    return SubstackPlatform()


class TestSubstackInit:
    def test_name(self, substack):
        assert substack.name == "substack"


class TestSubstackAuth:
    @pytest.mark.asyncio
    async def test_auth_no_browser(self, substack_no_browser):
        result = await substack_no_browser.authenticate()
        assert result is False

    @pytest.mark.asyncio
    async def test_auth_with_browser(self, substack):
        result = await substack.authenticate()
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check(self, substack):
        assert await substack.health_check() is True


class TestSubstackPublish:
    @pytest.mark.asyncio
    async def test_publish_no_browser(self, substack_no_browser):
        result = await substack_no_browser.publish({"title": "Post"})
        assert result["status"] == "no_browser"

    @pytest.mark.asyncio
    async def test_publish_with_browser(self, substack):
        result = await substack.publish({"title": "Post"})
        assert result["status"] == "published"


class TestSubstackAnalytics:
    @pytest.mark.asyncio
    async def test_analytics_no_browser(self, substack_no_browser):
        result = await substack_no_browser.get_analytics()
        assert result["subscribers"] == 0
