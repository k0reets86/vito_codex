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
def kdp_no_browser(tmp_path):
    k = AmazonKDPPlatform()
    # Isolate from any real session state that may exist on runner.
    k._state_file = tmp_path / "kdp_missing_state.json"
    return k


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
        assert result["status"] in {"published", "prepared"}

    @pytest.mark.asyncio
    async def test_publish_no_browser_records_platform_lesson(self, kdp_no_browser, monkeypatch):
        calls = []
        monkeypatch.setattr("platforms.amazon_kdp.record_platform_lesson", lambda service, **kwargs: calls.append((service, kwargs)))
        result = await kdp_no_browser.publish({"title": "Book"})
        assert result["status"] == "no_browser"
        assert calls
        assert calls[-1][0] == "amazon_kdp"
        assert calls[-1][1]["status"] == "no_browser"

    @pytest.mark.asyncio
    async def test_kdp_helper_requires_visible_draft_for_draft_status(self, kdp, monkeypatch):
        async def _fake_exec(*args, **kwargs):
            class _Proc:
                returncode = 4

                async def communicate(self):
                    payload = {
                        "ok": False,
                        "ok_soft": False,
                        "saved_click": True,
                        "title_found_on_bookshelf": False,
                        "title_found_via_search": False,
                        "fields_filled": 4,
                        "screenshot": "runtime/kdp_after.png",
                    }
                    return (json.dumps(payload).encode("utf-8"), b"")

            return _Proc()

        import json
        monkeypatch.setattr("platforms.amazon_kdp.asyncio.create_subprocess_exec", _fake_exec)
        result = await kdp._publish_via_kdp_helper({"title": "Book"})
        assert result["status"] == "prepared"
        assert result["output"]["draft_visible"] is False

    @pytest.mark.asyncio
    async def test_kdp_helper_visible_bookshelf_result_maps_to_draft(self, kdp, monkeypatch):
        async def _fake_exec(*args, **kwargs):
            class _Proc:
                returncode = 0

                async def communicate(self):
                    payload = {
                        "ok": True,
                        "ok_soft": True,
                        "saved_click": False,
                        "title_found_on_bookshelf": False,
                        "title_found_via_search": True,
                        "draft_visible": True,
                        "fields_filled": 4,
                        "bookshelf_screenshot": "runtime/kdp_bookshelf.png",
                    }
                    return (json.dumps(payload).encode("utf-8"), b"")

            return _Proc()

        import json
        monkeypatch.setattr("platforms.amazon_kdp.asyncio.create_subprocess_exec", _fake_exec)
        result = await kdp._publish_via_kdp_helper({"title": "Book"})
        assert result["status"] == "draft"
        assert result["screenshot_path"] == "runtime/kdp_bookshelf.png"


class TestKDPAnalytics:
    @pytest.mark.asyncio
    async def test_analytics_no_browser(self, kdp_no_browser):
        result = await kdp_no_browser.get_analytics()
        assert result["sales"] == 0
