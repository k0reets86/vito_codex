"""Тесты для PrintfulPlatform."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from platforms.printful import PrintfulPlatform


@pytest.fixture
def printful():
    with patch("platforms.printful.settings") as mock_settings:
        mock_settings.PRINTFUL_API_KEY = "test-key"
        platform = PrintfulPlatform()
        return platform


class TestPrintfulInit:
    def test_name(self, printful):
        assert printful.name == "printful"

    def test_not_authenticated(self, printful):
        assert printful._authenticated is False


class TestPrintfulAuth:
    @pytest.mark.asyncio
    async def test_auth_no_key(self):
        with patch("platforms.printful.settings") as mock_settings:
            mock_settings.PRINTFUL_API_KEY = ""
            platform = PrintfulPlatform()
            result = await platform.authenticate()
            assert result is False

    @pytest.mark.asyncio
    async def test_health_check_with_key(self, printful):
        result = await printful.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_no_key(self):
        with patch("platforms.printful.settings") as mock_settings:
            mock_settings.PRINTFUL_API_KEY = ""
            platform = PrintfulPlatform()
            result = await platform.health_check()
            assert result is False


class TestPrintfulPublish:
    @pytest.mark.asyncio
    async def test_publish_not_authenticated(self, printful):
        result = await printful.publish({"name": "test"})
        assert result["status"] == "not_authenticated"


class TestPrintfulAnalytics:
    @pytest.mark.asyncio
    async def test_analytics_not_authenticated(self, printful):
        result = await printful.get_analytics()
        assert result["orders"] == 0
