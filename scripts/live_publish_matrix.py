#!/usr/bin/env python3
"""Live publish probe matrix for configured platforms.

By default runs in dry-run. Use --live to attempt real publish calls.
Per-platform timeouts are enforced to avoid suite hangs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import base64
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.browser_agent import BrowserAgent
from platforms.amazon_kdp import AmazonKDPPlatform
from platforms.etsy import EtsyPlatform
from platforms.gumroad import GumroadPlatform
from platforms.kofi import KofiPlatform
from platforms.pinterest import PinterestPlatform
from platforms.printful import PrintfulPlatform
from platforms.reddit import RedditPlatform
from platforms.twitter import TwitterPlatform
from platforms.wordpress import WordPressPlatform
from modules.platform_artifact_pack import build_platform_bundle


def _payloads(live: bool) -> dict[str, dict]:
    tag = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    gumroad_slug = (os.getenv("GUMROAD_TEST_SLUG", "yupwt") or "yupwt").strip()
    img_path = ROOT / "output" / "ai_side_hustle_cover_1280x720.png"
    if not img_path.exists():
        img_path = ROOT / "output" / "ai_side_hustle_thumb_600x600.png"
    if not img_path.exists():
        img_path = ROOT / "runtime" / "probe_image.png"
        if not img_path.exists():
            img_path.parent.mkdir(parents=True, exist_ok=True)
            # 1200x630 PNG (valid for social/pinterest minimum sizes)
            raw = (
                b"iVBORw0KGgoAAAANSUhEUgAABLAAAAJ2CAIAAAC6V6tzAAAACXBIWXMAAAsSAAALEgHS3X78AAAK"
                b"IUlEQVR4nO3WQQ0AAAgDIN8/9K3hA2M0q1gQkM3N7wAAAPg2gQAAABgQAAABgQAAABgQAAABgQAAABgQ"
                b"AAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAA"
                b"ABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAAB"
                b"gQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQ"
                b"AAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAA"
                b"ABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAAB"
                b"gQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQ"
                b"AAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAA"
                b"ABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAAB"
                b"gQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQ"
                b"AAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAA"
                b"ABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAAB"
                b"gQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQ"
                b"AAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAA"
                b"ABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAAB"
                b"gQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQ"
                b"AAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAA"
                b"ABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAAB"
                b"gQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQ"
                b"AAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAA"
                b"ABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAAB"
                b"gQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQAAABgQ"
                b"AAB4XwAAR3v9A9Q0zWwAAAAASUVORK5CYII="
            )
            img_path.write_bytes(base64.b64decode(raw))
    pdf_path = ROOT / "runtime" / "probe_asset.pdf"
    if not pdf_path.exists():
        raw_pdf = (
            b"JVBERi0xLjEKMSAwIG9iago8PCAvVHlwZSAvQ2F0YWxvZyAvUGFnZXMgMiAwIFIgPj4KZW5kb2JqCjIgMCBvYmoK"
            b"PDwgL1R5cGUgL1BhZ2VzIC9Db3VudCAxIC9LaWRzIFsgMyAwIFIgXSA+PgplbmRvYmoKMyAwIG9iago8PCAvVHlw"
            b"ZSAvUGFnZSAvUGFyZW50IDIgMCBSIC9NZWRpYUJveCBbMCAwIDMwMCAxNDRdIC9Db250ZW50cyA0IDAgUiAvUmVz"
            b"b3VyY2VzIDw8IC9Gb250IDw8IC9GMSA1IDAgUiA+PiA+PiA+PgplbmRvYmoKNCAwIG9iago8PCAvTGVuZ3RoIDQ0"
            b"ID4+CnN0cmVhbQpCVCAvRjEgMjQgVGYgNzIgNzIgVGQgKFZJVE8gUFJPQkUpIFRqIEVUCmVuZHN0cmVhbQplbmRv"
            b"YmoKNSAwIG9iago8PCAvVHlwZSAvRm9udCAvU3VidHlwZSAvVHlwZTEgL0Jhc2VGb250IC9IZWx2ZXRpY2EgPj4K"
            b"ZW5kb2JqCnhyZWYKMCA2CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDAxMCAwMDAwMCBuIAowMDAwMDAwMDYw"
            b"IDAwMDAwIG4gCjAwMDAwMDAxMTcgMDAwMDAgbiAKMDAwMDAwMDI0MSAwMDAwMCBuIAowMDAwMDAwMzM1IDAwMDAw"
            b"IG4gCnRyYWlsZXIKPDwgL1NpemUgNiAvUm9vdCAxIDAgUiA+PgpzdGFydHhyZWYKNDI1CiUlRU9GCg=="
        )
        pdf_path.write_bytes(base64.b64decode(raw_pdf))
    return {
        "twitter": build_platform_bundle("twitter", {
            "dry_run": not live,
            "text": f"VITO publish probe {tag}",
        }),
        "reddit": build_platform_bundle("reddit", {
            "dry_run": not live,
            "subreddit": "u_Few_Garage_3659",
            "title": f"VITO probe {tag}",
            "text": "Live probe post from VITO",
        }),
        "etsy": build_platform_bundle("etsy", {
            "dry_run": not live,
            "title": f"VITO Probe Listing {tag}",
            "description": "Automated probe listing",
            "price": 5,
            "quantity": 1,
            "taxonomy_id": 1,
            "tags": ["vito", "probe", "digital", "ai", "productivity"],
        }),
        "gumroad": build_platform_bundle("gumroad", {
            "dry_run": not live,
            "title": f"VITO Probe Gumroad {tag}",
            "description": "Automated probe listing for controlled Gumroad flow",
            "price": 5,
            "tags": ["vito", "probe", "digital", "ai", "automation"],
            # Avoid draft-spam and daily limits: edit one controlled test listing.
            "allow_existing_update": True,
            "owner_edit_confirmed": True,
            "target_slug": gumroad_slug,
            "keep_unpublished": True,
            "operation": "update",
            "pdf_path": str(pdf_path),
            "cover_path": str(img_path),
            "thumb_path": str(img_path),
        }),
        "amazon_kdp": build_platform_bundle("amazon_kdp", {
            "dry_run": not live,
            "title": f"VITO Probe Book {tag}",
            "description": "Automated KDP probe draft",
            "keywords": ["vito", "probe", "automation"],
        }),
        "printful": build_platform_bundle("printful", {
            "dry_run": not live,
            "sync_product": {"name": f"VITO Probe {tag}"},
            "sync_variants": [],
        }),
        "kofi": build_platform_bundle("kofi", {
            "dry_run": not live,
            "title": f"VITO Probe {tag}",
            "description": "Automated probe product",
            "price": 1,
        }),
        "pinterest": build_platform_bundle("pinterest", {
            "dry_run": not live,
            "title": f"VITO pin probe {tag}",
            "description": "Probe pin for browser automation flow check.",
            "url": "https://example.com/vito-probe",
            "image_path": str(img_path),
        }),
        "wordpress": {
            "dry_run": not live,
            "title": f"VITO Probe Post {tag}",
            "content": "<p>Live probe post.</p>",
            "status": "draft",
        },
    }


async def run(live: bool) -> dict:
    browser = BrowserAgent()
    platforms = {
        "twitter": TwitterPlatform(),
        "reddit": RedditPlatform(),
        "etsy": EtsyPlatform(),
        "gumroad": GumroadPlatform(),
        "amazon_kdp": AmazonKDPPlatform(browser_agent=browser),
        "printful": PrintfulPlatform(),
        "kofi": KofiPlatform(),
        "pinterest": PinterestPlatform(),
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
            auth_ok = await asyncio.wait_for(p.authenticate(), timeout=45)
            row["auth_ok"] = bool(auth_ok)
        except Exception as e:
            row["auth_ok"] = False
            row["auth_error"] = str(e)
        try:
            publish_timeout = 300 if name in {"etsy", "kofi", "gumroad", "amazon_kdp", "pinterest"} else 120
            res = await asyncio.wait_for(p.publish(payloads[name]), timeout=publish_timeout)
            row["publish"] = res
            if name == "twitter" and live and isinstance(res, dict) and res.get("status") == "published":
                tid = str(res.get("tweet_id") or "")
                if tid:
                    row["cleanup"] = await asyncio.wait_for(p.delete_tweet(tid), timeout=45)
        except TimeoutError:
            row["publish"] = {"platform": name, "status": "error", "error": "timeout"}
        except Exception as e:
            row["publish"] = {"platform": name, "status": "error", "error": str(e)}
        out["results"].append(row)
        try:
            await asyncio.wait_for(p.close(), timeout=15)
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
