import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.base_agent import TaskResult
from platforms.instagram import InstagramPlatform
from platforms.linkedin import LinkedInPlatform
from platforms.shopify import ShopifyPlatform
from platforms.threads import ThreadsPlatform
from platforms.tiktok import TikTokPlatform


@pytest.fixture
def mock_browser():
    browser = MagicMock()
    browser.execute_task = AsyncMock(return_value=TaskResult(success=True, output={"url": "https://example.com/editor"}))
    return browser


@pytest.mark.asyncio
async def test_instagram_browser_fallback_publish(mock_browser):
    with patch("platforms.instagram.settings") as s:
        s.INSTAGRAM_ACCESS_TOKEN = ""
        s.INSTAGRAM_BUSINESS_ACCOUNT_ID = ""
        s.INSTAGRAM_STORAGE_STATE_FILE = "runtime/instagram_storage_state.json"
        platform = InstagramPlatform(browser_agent=mock_browser)
        result = await platform.publish({"caption": "hello"})
        assert result["status"] == "prepared"


@pytest.mark.asyncio
async def test_linkedin_browser_fallback_publish(mock_browser):
    with patch("platforms.linkedin.settings") as s:
        s.LINKEDIN_ACCESS_TOKEN = ""
        s.LINKEDIN_AUTHOR_URN = ""
        s.LINKEDIN_STORAGE_STATE_FILE = "runtime/linkedin_storage_state.json"
        platform = LinkedInPlatform(browser_agent=mock_browser)
        result = await platform.publish({"text": "hello"})
        assert result["status"] == "prepared"


@pytest.mark.asyncio
async def test_shopify_browser_fallback_publish(mock_browser):
    with patch("platforms.shopify.settings") as s:
        s.SHOPIFY_ACCESS_TOKEN = ""
        s.SHOPIFY_STORE_URL = ""
        s.SHOPIFY_STORAGE_STATE_FILE = "runtime/shopify_storage_state.json"
        platform = ShopifyPlatform(browser_agent=mock_browser)
        result = await platform.publish({"title": "Product"})
        assert result["status"] == "prepared"


@pytest.mark.asyncio
async def test_threads_browser_fallback_publish(mock_browser):
    with patch("platforms.threads.settings") as s:
        s.THREADS_ACCESS_TOKEN = ""
        s.THREADS_USER_ID = ""
        s.THREADS_STORAGE_STATE_FILE = "runtime/threads_storage_state.json"
        platform = ThreadsPlatform(browser_agent=mock_browser)
        result = await platform.publish({"text": "hello"})
        assert result["status"] == "prepared"


@pytest.mark.asyncio
async def test_tiktok_browser_fallback_publish(mock_browser):
    with patch("platforms.tiktok.settings") as s:
        s.TIKTOK_ACCESS_TOKEN = ""
        s.TIKTOK_STORAGE_STATE_FILE = "runtime/tiktok_storage_state.json"
        platform = TikTokPlatform(browser_agent=mock_browser)
        result = await platform.publish({"caption": "hello"})
        assert result["status"] == "prepared"
