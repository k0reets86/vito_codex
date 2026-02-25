import pytest

from platforms.etsy import EtsyPlatform
from platforms.kofi import KofiPlatform
from platforms.printful import PrintfulPlatform
from platforms.twitter import TwitterPlatform
from platforms.wordpress import WordPressPlatform


@pytest.mark.asyncio
async def test_platform_publish_dryrun_paths():
    etsy = EtsyPlatform()
    kofi = KofiPlatform()
    printful = PrintfulPlatform()
    twitter = TwitterPlatform()
    wordpress = WordPressPlatform()

    r1 = await etsy.publish({"dry_run": True, "title": "x"})
    r2 = await kofi.publish({"dry_run": True, "title": "x"})
    r3 = await printful.publish({"dry_run": True, "sync_product": {"name": "x"}})
    r4 = await twitter.publish({"dry_run": True, "text": "x"})
    r5 = await wordpress.publish({"dry_run": True, "title": "x"})

    assert r1.get("status") == "prepared"
    assert r2.get("status") == "prepared"
    assert r3.get("status") == "prepared"
    assert r4.get("status") == "prepared"
    assert r5.get("status") == "prepared"
