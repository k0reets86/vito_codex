#!/usr/bin/env python3
"""Run Social SDK Pack dry-run via unified PublisherQueue."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.publisher_queue import PublisherQueue
from platforms.reddit import RedditPlatform
from platforms.threads import ThreadsPlatform
from platforms.tiktok import TikTokPlatform
from platforms.youtube import YouTubePlatform
from platforms.twitter import TwitterPlatform


async def main_async() -> dict:
    platforms = {
        "twitter": TwitterPlatform(),
        "threads": ThreadsPlatform(),
        "reddit": RedditPlatform(),
        "tiktok": TikTokPlatform(),
        "youtube": YouTubePlatform(),
    }
    pq = PublisherQueue(platforms=platforms)
    pq.enqueue("twitter", {"dry_run": True, "text": "VITO social sdk pack dryrun"})
    pq.enqueue("threads", {"dry_run": True, "text": "VITO social sdk pack dryrun"})
    pq.enqueue("reddit", {"dry_run": True, "subreddit": "test", "title": "VITO dryrun", "text": "dryrun"})
    pq.enqueue("tiktok", {"dry_run": True, "caption": "VITO social sdk pack dryrun"})
    pq.enqueue("youtube", {"dry_run": True, "title": "VITO social sdk pack dryrun"})
    rows = await pq.process_all(limit=20)
    return {"timestamp": datetime.now(timezone.utc).isoformat(), "processed": rows, "stats": pq.stats()}


def main() -> int:
    data = asyncio.run(main_async())
    reports = ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%MUTC")
    p = reports / f"VITO_SOCIAL_SDK_DRYRUN_{ts}.json"
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(p))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
