"""Тесты для YouTubePlatform."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from platforms.youtube import YouTubePlatform


@pytest.fixture
def youtube():
    with patch("platforms.youtube.settings") as mock_settings:
        mock_settings.GOOGLE_API_KEY = "test-key"
        return YouTubePlatform()


@pytest.fixture
def youtube_no_key():
    with patch("platforms.youtube.settings") as mock_settings:
        mock_settings.GOOGLE_API_KEY = ""
        return YouTubePlatform()


class TestYouTubeInit:
    def test_name(self, youtube):
        assert youtube.name == "youtube"


class TestYouTubeAuth:
    @pytest.mark.asyncio
    async def test_auth_no_key(self, youtube_no_key):
        result = await youtube_no_key.authenticate()
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_with_key(self, youtube):
        assert await youtube.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_no_key(self, youtube_no_key):
        assert await youtube_no_key.health_check() is False


class TestYouTubePublish:
    @pytest.mark.asyncio
    async def test_publish_not_supported(self, youtube):
        result = await youtube.publish({"title": "video"})
        assert result["status"] == "not_supported"


class TestYouTubeTrending:
    @pytest.mark.asyncio
    async def test_trending_no_key(self, youtube_no_key):
        result = await youtube_no_key.search_trending()
        assert result["videos"] == []

    @pytest.mark.asyncio
    async def test_search_videos_no_key(self, youtube_no_key):
        result = await youtube_no_key.search_videos("test")
        assert result == []
