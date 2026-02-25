import pytest

from platforms.twitter import TwitterPlatform


@pytest.mark.asyncio
async def test_twitter_delete_requires_id():
    t = TwitterPlatform()
    res = await t.delete_tweet("")
    assert res.get("status") == "error"
