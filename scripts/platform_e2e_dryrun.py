#!/usr/bin/env python3
"""Run safe end-to-end dry-run publish pipeline across key platforms.

This does NOT perform live posting. It validates end-to-end orchestration
and stores evidence via ExecutionFacts with status=prepared.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from platforms.etsy import EtsyPlatform
from platforms.gumroad import GumroadPlatform
from platforms.kofi import KofiPlatform
from platforms.printful import PrintfulPlatform
from platforms.twitter import TwitterPlatform
from platforms.wordpress import WordPressPlatform


async def run() -> dict:
    platforms = {
        "gumroad": GumroadPlatform(),
        "etsy": EtsyPlatform(),
        "kofi": KofiPlatform(),
        "printful": PrintfulPlatform(),
        "twitter": TwitterPlatform(),
        "wordpress": WordPressPlatform(),
    }
    payloads = {
        "etsy": {
            "dry_run": True,
            "title": "VITO DryRun Etsy Product",
            "description": "Dry-run listing validation only.",
            "price": 5,
            "tags": ["ai", "checklist"],
        },
        "gumroad": {
            "dry_run": True,
            "name": "VITO DryRun Gumroad Product",
            "description": "Dry-run Gumroad product pipeline validation only.",
            "price": 5,
        },
        "kofi": {
            "dry_run": True,
            "title": "VITO DryRun Ko-fi Product",
            "description": "Dry-run shop product validation only.",
            "price": 5,
        },
        "printful": {
            "dry_run": True,
            "sync_product": {"name": "VITO DryRun Printful Product"},
        },
        "twitter": {
            "dry_run": True,
            "text": "VITO dry-run tweet pipeline validated.",
        },
        "wordpress": {
            "dry_run": True,
            "title": "VITO DryRun WordPress Post",
            "content": "<p>Dry-run post pipeline validated.</p>",
            "status": "draft",
        },
    }
    out = {"timestamp": datetime.now(timezone.utc).isoformat(), "results": []}
    for name, p in platforms.items():
        try:
            res = await p.publish(payloads[name])
        except Exception as e:
            res = {"platform": name, "status": "error", "error": str(e)}
        out["results"].append({"platform": name, "result": res})
    return out


def main() -> int:
    data = asyncio.run(run())
    reports = ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%MUTC")
    p = reports / f"VITO_PLATFORM_E2E_DRYRUN_{ts}.json"
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(p))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
