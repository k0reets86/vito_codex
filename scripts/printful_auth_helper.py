#!/usr/bin/env python3
"""Printful browser auth helper (storage_state capture)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from playwright.async_api import async_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings


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


async def browser_capture(timeout_sec: int, storage_path: str, headless: bool, auto_submit: bool) -> int:
    email = str(os.getenv("PRINTFUL_EMAIL", "") or os.getenv("EMAIL", ""))
    password = str(os.getenv("PRINTFUL_PASSWORD", "") or os.getenv("PASSWORD", ""))
    out = Path(storage_path)
    if not out.is_absolute():
        out = PROJECT_ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)

    print("\n=== Printful Browser Session Capture ===")
    print("1) Откроется printful.com/login")
    print("2) Заверши вход вручную (captcha/2FA если нужно)")
    print("3) Скрипт дождется /dashboard и сохранит storage_state")
    print(f"Output storage: {out}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, args=_chromium_launch_args())
        context = await browser.new_context(viewport={"width": 1366, "height": 900})
        page = await context.new_page()
        await page.goto("https://www.printful.com/login", wait_until="domcontentloaded", timeout=120000)
        await page.wait_for_timeout(2000)

        if email:
            for sel in ("input[type='email']", "input[name='email']"):
                try:
                    await page.fill(sel, email)
                    break
                except Exception:
                    continue
        if password:
            for sel in ("input[type='password']", "input[name='password']"):
                try:
                    await page.fill(sel, password)
                    break
                except Exception:
                    continue
        if auto_submit:
            for sel in ("button[type='submit']", "button:has-text('Log in')", "button:has-text('Sign in')"):
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=1500):
                        await btn.click()
                        await page.wait_for_timeout(1200)
                        break
                except Exception:
                    continue

        ok = False
        end_ts = asyncio.get_event_loop().time() + max(60, int(timeout_sec))
        while asyncio.get_event_loop().time() < end_ts:
            await page.wait_for_timeout(1500)
            u = page.url.lower()
            if "/dashboard" in u or "/stores" in u or "/billing" in u:
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
    ap = argparse.ArgumentParser(description="Printful auth helper")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_capture = sub.add_parser("browser-capture", help="Capture logged-in Printful browser session")
    p_capture.add_argument("--timeout-sec", type=int, default=420)
    p_capture.add_argument("--storage-path", default="runtime/printful_storage_state.json")
    p_capture.add_argument("--headless", action="store_true")
    p_capture.add_argument("--auto-submit", action="store_true")

    args = ap.parse_args()
    if args.cmd == "browser-capture":
        return asyncio.run(browser_capture(int(args.timeout_sec), str(args.storage_path), bool(args.headless), bool(args.auto_submit)))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
