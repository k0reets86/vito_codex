#!/usr/bin/env python3
"""Etsy auth helper.

Provides two safe flows:
1) OAuth2 PKCE (recommended) using Etsy official API flow.
2) Manual browser session capture (fallback for browser automation).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings
from platforms.etsy import EtsyPlatform


def _chromium_launch_args() -> list[str]:
    args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--renderer-process-limit=1",
    ]
    if bool(getattr(settings, "BROWSER_CONSTRAINED_MODE", True)):
        args.extend(["--no-zygote", "--single-process"])
    return args


def _extract_code(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    if "code=" not in text:
        return text
    try:
        qs = parse_qs(urlparse(text).query)
        code = (qs.get("code") or [""])[0]
        return str(code or "").strip()
    except Exception:
        m = re.search(r"[?&]code=([^&]+)", text)
        return m.group(1).strip() if m else ""


async def oauth_start() -> int:
    etsy = EtsyPlatform()
    data = await etsy.start_oauth2_pkce()
    if data.get("error"):
        print(f"ERROR: {data['error']}")
        return 1
    print("\n=== Etsy OAuth Start ===")
    print("1) Open URL in your regular browser")
    print("2) Login to Etsy and approve access")
    print("3) Copy full callback URL and run oauth-complete\n")
    print(data.get("auth_url", ""))
    print("\nRedirect URI:")
    print(data.get("redirect_uri", ""))
    return 0


async def oauth_complete(raw_code_or_url: str) -> int:
    code = _extract_code(raw_code_or_url)
    if not code:
        print("ERROR: missing code (pass callback URL or code)")
        return 1
    etsy = EtsyPlatform()
    ok = await etsy.complete_oauth2(code)
    if not ok:
        print("ERROR: token exchange failed")
        return 1
    print("OK: Etsy OAuth token saved.")
    print(f"- ETSY_OAUTH_ACCESS_TOKEN: {'set' if bool(settings.ETSY_OAUTH_ACCESS_TOKEN) else 'state-file only'}")
    print(f"- ETSY_OAUTH_REFRESH_TOKEN: {'set' if bool(settings.ETSY_OAUTH_REFRESH_TOKEN) else 'state-file only'}")
    print("Note: runtime state saved to runtime/etsy_oauth_state.json")
    return 0


async def browser_capture(timeout_sec: int, storage_path: str, headless: bool) -> int:
    # Lazy import so OAuth-only mode does not require playwright runtime
    from playwright.async_api import async_playwright

    email = str(getattr(settings, "ETSY_EMAIL", "") or "")
    password = str(getattr(settings, "ETSY_PASSWORD", "") or "")
    out = Path(storage_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    print("\n=== Etsy Browser Session Capture ===")
    print("Flow:")
    print("1) Browser opens Etsy login page")
    print("2) Complete login manually (captcha/2FA if asked)")
    print("3) Script waits for account URL and saves storage state")
    print(f"Output storage: {out}")
    if headless:
        print("WARNING: headless=True may fail on Etsy anti-bot checks.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, args=_chromium_launch_args())
        context = await browser.new_context(viewport={"width": 1366, "height": 900})
        page = await context.new_page()
        await page.goto("https://www.etsy.com/signin", wait_until="domcontentloaded", timeout=120000)
        await page.wait_for_timeout(2000)

        # Best effort prefill only; submit remains manual.
        if email:
            for sel in ("input[type='email']", "input[name='email']", "#join_neu_email_field"):
                try:
                    await page.fill(sel, email)
                    break
                except Exception:
                    continue
        if password:
            for sel in ("input[type='password']", "input[name='password']", "#join_neu_password_field"):
                try:
                    await page.fill(sel, password)
                    break
                except Exception:
                    continue

        print("Waiting for successful login...")
        print("Success markers: /your/, /shop-manager, /your/account")
        ok = False
        end_ts = asyncio.get_event_loop().time() + max(60, int(timeout_sec))
        while asyncio.get_event_loop().time() < end_ts:
            await page.wait_for_timeout(1500)
            u = page.url.lower()
            if any(x in u for x in ("/your/", "/shop-manager", "/your/account")):
                ok = True
                break

        if not ok:
            shot = out.with_suffix(".failed.png")
            try:
                await page.screenshot(path=str(shot), full_page=True)
            except Exception:
                pass
            await context.close()
            await browser.close()
            print("ERROR: login not confirmed before timeout")
            print(f"Debug screenshot: {shot}")
            return 1

        await context.storage_state(path=str(out))
        cookies = await context.cookies()
        cookie_path = out.with_suffix(".cookies.json")
        cookie_path.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
        await context.close()
        await browser.close()
        print("OK: session captured")
        print(f"- storage_state: {out}")
        print(f"- cookies: {cookie_path}")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Etsy auth helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("oauth-start", help="Start Etsy OAuth2 PKCE flow (recommended)")
    p_complete = sub.add_parser("oauth-complete", help="Complete OAuth2 with callback URL or code")
    p_complete.add_argument("--code", required=True, help="OAuth code or full callback URL")

    p_browser = sub.add_parser("browser-capture", help="Capture logged-in Etsy browser session")
    p_browser.add_argument("--timeout-sec", type=int, default=420)
    p_browser.add_argument("--storage-path", default="runtime/etsy_storage_state.json")
    p_browser.add_argument("--headless", action="store_true", help="Run headless (not recommended for Etsy login)")

    args = parser.parse_args()
    if args.cmd == "oauth-start":
        return asyncio.run(oauth_start())
    if args.cmd == "oauth-complete":
        return asyncio.run(oauth_complete(args.code))
    if args.cmd == "browser-capture":
        return asyncio.run(
            browser_capture(
                timeout_sec=int(args.timeout_sec),
                storage_path=str(args.storage_path),
                headless=bool(args.headless),
            )
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
