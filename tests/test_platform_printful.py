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

    @pytest.mark.asyncio
    async def test_publish_store_restriction_returns_needs_browser_flow(self, printful):
        printful._authenticated = True
        printful._store_id = "1"
        printful._store_type = "api"

        class _Resp:
            status = 400

            async def json(self):
                return {
                    "code": 400,
                    "result": "This API endpoint applies only to Printful stores based on the Manual Order / API platform.",
                    "error": {"message": "This API endpoint applies only to Printful stores based on the Manual Order / API platform."},
                }

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        class _Sess:
            def post(self, *args, **kwargs):
                return _Resp()

        printful._get_session = AsyncMock(return_value=_Sess())
        result = await printful.publish({"sync_product": {"name": "VITO Probe"}})
        assert result["status"] == "needs_browser_flow"

    @pytest.mark.asyncio
    async def test_publish_non_api_store_type_requires_browser_flow(self, printful):
        printful._authenticated = True
        printful._store_id = "17803130"
        printful._store_type = "etsy"
        printful._sync_products_probe = AsyncMock(return_value={"ok": True, "count": 0})
        result = await printful.publish({"sync_product": {"name": "VITO Probe"}})
        assert result["status"] == "needs_browser_flow"
        assert result["store_type"] == "etsy"


class TestPrintfulAnalytics:
    @pytest.mark.asyncio
    async def test_analytics_not_authenticated(self, printful):
        result = await printful.get_analytics()
        assert result["orders"] == 0
