#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.browser_runtime_policy import get_browser_runtime_profile
from modules.human_browser import HumanBrowser

LOGIN_ROUTES = {
    "etsy": "https://www.etsy.com/signin",
    "printful": "https://www.printful.com/login",
    "twitter": "https://x.com/i/flow/login",
}
SUCCESS_MARKERS = {
    "etsy": ("/your/", "/shop-manager", "/your/account"),
    "printful": ("/dashboard", "/stores", "/billing"),
    "twitter": ("/home", "/compose/post", "/settings/profile"),
}


async def capture(service: str, timeout_sec: int, headless: bool) -> int:
    svc = str(service or "").strip().lower()
    if svc not in LOGIN_ROUTES:
        print(f"ERROR: unsupported service {svc}")
        return 2
    try:
        from playwright.async_api import async_playwright
    except Exception as e:
        print(f"ERROR: playwright unavailable: {e}")
        return 2

    profile = get_browser_runtime_profile(svc)
    storage_path = Path(str(profile.get("storage_state_path") or ""))
    if not storage_path.is_absolute():
        storage_path = PROJECT_ROOT / storage_path
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    cookies_path = storage_path.with_suffix(".cookies.json")
    screenshot_fail = storage_path.with_suffix(".failed.png")

    hb = HumanBrowser()
    print(json.dumps({
        "service": svc,
        "login_url": LOGIN_ROUTES[svc],
        "storage_state": str(storage_path),
        "profile_dir": str(profile.get("persistent_profile_dir") or ""),
    }, ensure_ascii=False))

    async with async_playwright() as p:
        browser, context, mode = await hb.launch_managed_context(
            p.chromium,
            profile=profile,
            headless=headless,
            launch_args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="America/New_York",
            viewport={"width": 1366, "height": 900},
        )
        page = await context.new_page()
        try:
            await page.goto(LOGIN_ROUTES[svc], wait_until="domcontentloaded", timeout=120000)
            end_ts = asyncio.get_event_loop().time() + max(60, int(timeout_sec))
            ok = False
            while asyncio.get_event_loop().time() < end_ts:
                await page.wait_for_timeout(1500)
                url = (page.url or "").lower()
                if any(tok in url for tok in SUCCESS_MARKERS[svc]):
                    ok = True
                    break
            if not ok:
                try:
                    await page.screenshot(path=str(screenshot_fail), full_page=True)
                except Exception:
                    pass
                print(json.dumps({"ok": False, "service": svc, "mode": mode, "error": "login_not_confirmed", "debug_screenshot": str(screenshot_fail)}, ensure_ascii=False))
                return 1
            await context.storage_state(path=str(storage_path))
            cookies = await context.cookies()
            cookies_path.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"ok": True, "service": svc, "mode": mode, "storage_state": str(storage_path), "cookies": str(cookies_path)}, ensure_ascii=False))
            return 0
        finally:
            await context.close()
            await browser.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Generic browser auth capture")
    ap.add_argument("service", choices=sorted(LOGIN_ROUTES))
    ap.add_argument("--timeout-sec", type=int, default=420)
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()
    return asyncio.run(capture(args.service, int(args.timeout_sec), bool(args.headless)))


if __name__ == "__main__":
    raise SystemExit(main())
