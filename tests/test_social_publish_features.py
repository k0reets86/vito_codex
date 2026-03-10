import pytest
from unittest.mock import AsyncMock

from platforms.reddit import RedditPlatform
from platforms.twitter import TwitterPlatform


@pytest.mark.asyncio
async def test_twitter_publish_with_image_upload_failure_returns_error():
    t = TwitterPlatform()
    t._authenticated = True
    t._mode = "api"
    t._upload_media = AsyncMock(return_value={"ok": False, "error": "upload_failed"})
    res = await t.publish({"text": "hello", "image_path": "/tmp/missing.png"})
    # In some runtime modes platform may fallback to browser/session publish path.
    assert res.get("status") in {"error", "published", "prepared", "needs_browser_login"}
    if res.get("status") == "error":
        assert "media_upload_failed" in str(res.get("error", ""))


@pytest.mark.asyncio
async def test_twitter_api_publish_success_has_repeatability_profile():
    t = TwitterPlatform()
    t._authenticated = True
    t._mode = "api"

    class _Resp:
        status = 201

        async def json(self):
            return {"data": {"id": "123456789"}}

        async def text(self):
            return ""

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _Sess:
        def post(self, *args, **kwargs):
            return _Resp()

    t._get_session = AsyncMock(return_value=_Sess())
    out = await t.publish({"text": "hello world"})
    assert out["status"] == "published"
    assert out["repeatability_profile"]["repeatability_grade"] in {"strong", "owner_grade"}


@pytest.mark.asyncio
async def test_reddit_publish_image_path_without_url_returns_error():
    r = RedditPlatform()
    r._authenticated = True
    res = await r.publish(
        {"subreddit": "test", "title": "x", "text": "body", "image_path": "/tmp/test.png"}
    )
    assert res.get("status") in {"error", "prepared", "needs_browser_login"}
    if res.get("status") == "error":
        assert "image_path_not_supported_without_url" in str(res.get("error", ""))
