import pytest

from platforms.reddit import RedditPlatform
from platforms.threads import ThreadsPlatform
from platforms.tiktok import TikTokPlatform
from platforms.youtube import YouTubePlatform


@pytest.mark.asyncio
async def test_social_adapters_dryrun_paths():
    reddit = RedditPlatform()
    threads = ThreadsPlatform()
    tiktok = TikTokPlatform()
    youtube = YouTubePlatform()

    r1 = await reddit.publish({"dry_run": True, "title": "x", "subreddit": "test"})
    r2 = await threads.publish({"dry_run": True, "text": "x"})
    r3 = await tiktok.publish({"dry_run": True, "caption": "x"})
    r4 = await youtube.publish({"dry_run": True, "title": "x"})

    assert r1.get("status") == "prepared"
    assert r2.get("status") == "prepared"
    assert r3.get("status") == "prepared"
    assert r4.get("status") == "prepared"
