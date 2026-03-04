#!/usr/bin/env python3
"""Live publish probe matrix for configured platforms.

By default runs in dry-run. Use --live to attempt real publish calls.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from platforms.etsy import EtsyPlatform
from platforms.kofi import KofiPlatform
from platforms.printful import PrintfulPlatform
from platforms.reddit import RedditPlatform
from platforms.twitter import TwitterPlatform
from platforms.wordpress import WordPressPlatform


def _payloads(live: bool) -> dict[str, dict]:
    tag = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    common_img_url = "https://via.placeholder.com/1200x630.png?text=VITO+Probe"
    return {
        "twitter": {
            "dry_run": not live,
            "text": f"VITO publish probe {tag}",
        },
        "reddit": {
            "dry_run": not live,
            "subreddit": "test",
            "title": f"VITO probe {tag}",
            "text": "Live probe post from VITO",
            "image_url": common_img_url,
        },
        "etsy": {
            "dry_run": not live,
            "title": f"VITO Probe Listing {tag}",
            "description": "Automated probe listing",
            "price": 5,
            "quantity": 1,
            "taxonomy_id": 1,
            "tags": ["vito", "probe"],
        },
        "printful": {
            "dry_run": not live,
            "sync_product": {"name": f"VITO Probe {tag}"},
            "sync_variants": [],
        },
        "kofi": {
            "dry_run": not live,
            "title": f"VITO Probe {tag}",
            "description": "Automated probe product",
            "price": 1,
        },
        "wordpress": {
            "dry_run": not live,
            "title": f"VITO Probe Post {tag}",
            "content": "<p>Live probe post.</p>",
            "status": "draft",
        },
    }


async def run(live: bool) -> dict:
    platforms = {
        "twitter": TwitterPlatform(),
        "reddit": RedditPlatform(),
        "etsy": EtsyPlatform(),
        "printful": PrintfulPlatform(),
        "kofi": KofiPlatform(),
        "wordpress": WordPressPlatform(),
    }
    payloads = _payloads(live)
    out: dict = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "live" if live else "dry_run",
        "results": [],
    }

    for name, p in platforms.items():
        row: dict = {"platform": name}
        try:
            auth_ok = await p.authenticate()
            row["auth_ok"] = bool(auth_ok)
        except Exception as e:
            row["auth_ok"] = False
            row["auth_error"] = str(e)
        try:
            res = await p.publish(payloads[name])
            row["publish"] = res
            if name == "twitter" and live and isinstance(res, dict) and res.get("status") == "published":
                tid = str(res.get("tweet_id") or "")
                if tid:
                    row["cleanup"] = await p.delete_tweet(tid)
        except Exception as e:
            row["publish"] = {"platform": name, "status": "error", "error": str(e)}
        out["results"].append(row)
        try:
            await p.close()
        except Exception:
            pass

    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Attempt real publish operations.")
    args = parser.parse_args()

    data = asyncio.run(run(live=bool(args.live)))
    reports = ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%MUTC")
    mode = "LIVE" if args.live else "DRY"
    path = reports / f"VITO_PUBLISH_MATRIX_{mode}_{ts}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

