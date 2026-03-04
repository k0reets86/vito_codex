#!/usr/bin/env python3
"""Combined full-cycle verifier for Etsy (browser-only) and Ko-fi.

Runs on existing targets and records actionable blockers when live auth/session is missing.
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

from config.paths import PROJECT_ROOT
from platforms.etsy import EtsyPlatform
from platforms.kofi import KofiPlatform

REPORTS = PROJECT_ROOT / "reports"


async def run_etsy(args) -> dict:
    etsy = EtsyPlatform()
    target_listing_id = str(args.etsy_listing_id or "").strip()
    payload = {
        "title": args.etsy_title,
        "description": args.etsy_description,
        "price": args.etsy_price,
        "tags": [t.strip() for t in (args.etsy_tags or "").split(",") if t.strip()],
        "allow_existing_update": bool(target_listing_id),
        "target_listing_id": target_listing_id,
    }
    result = await etsy.publish(payload)
    await etsy.close()

    shot = PROJECT_ROOT / "runtime" / "etsy_browser_publish.png"
    html = PROJECT_ROOT / "runtime" / "etsy_browser_publish.html"

    checks = {
        "has_session": result.get("status") != "needs_browser_login",
        "editor_reached": result.get("status") in {"prepared", "created"},
        "has_listing_id": bool(result.get("listing_id")),
    }
    return {
        "payload": payload,
        "result": result,
        "evidence": {
            "screenshot": str(shot) if shot.exists() else "",
            "html": str(html) if html.exists() else "",
        },
        "checks": checks,
        "pass": checks["has_session"] and checks["editor_reached"],
    }


async def run_kofi(args) -> dict:
    kofi = KofiPlatform()
    payload = {
        "title": args.kofi_title,
        "description": args.kofi_description,
        "price": args.kofi_price,
    }
    result = await kofi.publish(payload)
    await kofi.close()

    shot = PROJECT_ROOT / "runtime" / "kofi_browser_publish.png"
    html = PROJECT_ROOT / "runtime" / "kofi_browser_publish.html"
    checks = {
        "has_session": result.get("status") != "needs_browser_login",
        "action_executed": result.get("status") in {"prepared", "created"},
        "live_created": result.get("status") == "created",
    }
    return {
        "payload": payload,
        "result": result,
        "evidence": {
            "screenshot": str(shot) if shot.exists() else "",
            "html": str(html) if html.exists() else "",
        },
        "checks": checks,
        "pass": checks["has_session"] and checks["action_executed"],
    }


async def main_async(args) -> dict:
    etsy = await run_etsy(args)
    kofi = await run_kofi(args)
    all_checks = {
        "etsy": etsy.get("pass", False),
        "kofi": kofi.get("pass", False),
    }
    blockers = []
    if etsy.get("result", {}).get("status") == "needs_browser_login":
        blockers.append("etsy_session_missing")
    if kofi.get("result", {}).get("status") == "needs_browser_login":
        blockers.append("kofi_session_missing")
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": {
            "etsy": etsy,
            "kofi": kofi,
        },
        "checks": all_checks,
        "pass": all(all_checks.values()),
        "blockers": blockers,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--etsy-listing-id", default="", help="Existing Etsy listing id for safe update flow")
    ap.add_argument("--etsy-title", default="VITO Etsy Test Listing")
    ap.add_argument("--etsy-description", default="Safe test update for existing Etsy listing.")
    ap.add_argument("--etsy-price", default="9")
    ap.add_argument("--etsy-tags", default="ai,automation,digital products,productivity,templates")

    ap.add_argument("--kofi-title", default="VITO Ko-fi Test Product")
    ap.add_argument("--kofi-description", default="Safe test product update flow for Ko-fi.")
    ap.add_argument("--kofi-price", default="9")

    args = ap.parse_args()
    report = asyncio.run(main_async(args))

    REPORTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%MUTC")
    path = REPORTS / f"VITO_ETSY_KOFI_FULL_CYCLE_{ts}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "report_path": str(path),
        "pass": report.get("pass"),
        "checks": report.get("checks"),
        "blockers": report.get("blockers"),
    }, ensure_ascii=False, indent=2))
    return 0 if report.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
