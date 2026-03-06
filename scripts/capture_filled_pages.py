#!/usr/bin/env python3
"""Open platform pages, fill visible listing fields, and capture screenshots."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
REPORTS = ROOT / "reports"


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%MUTC")


def _mark() -> str:
    return datetime.now(timezone.utc).strftime("VITO-FILL-%Y%m%d-%H%M")


def _state(service: str) -> Path:
    return {
        "etsy": RUNTIME / "etsy_storage_state.json",
        "kofi": RUNTIME / "kofi_storage_state.json",
        "gumroad": RUNTIME / "gumroad_storage_state.json",
    }[service]


async def _open_context(p, service: str):
    storage = _state(service)
    browser = await p.chromium.launch(
        headless=os.getenv("VITO_BROWSER_HEADLESS", "1").lower() not in {"0", "false", "no"},
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
    )
    context = await browser.new_context(
        storage_state=str(storage) if storage.exists() else None,
        viewport={"width": 1440, "height": 980},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    )
    page = await context.new_page()
    return browser, context, page


async def fill_etsy(p) -> dict[str, Any]:
    browser, context, page = await _open_context(p, "etsy")
    marker = _mark()
    try:
        await page.goto("https://www.etsy.com/your/shops/me/listing-editor/create", wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(2500)
        title_ok = desc_ok = price_ok = False
        for sel in ("input[name='title']", "input[id*='title']"):
            try:
                loc = page.locator(sel)
                if await loc.count():
                    await loc.first.fill(f"Etsy Listing {marker}", timeout=2500)
                    title_ok = True
                    break
            except Exception:
                pass
        for sel in ("textarea[name='description']", "textarea[id*='description']", "textarea"):
            try:
                loc = page.locator(sel)
                if await loc.count():
                    await loc.first.fill(f"Filled for screenshot evidence {marker}.", timeout=2500)
                    desc_ok = True
                    break
            except Exception:
                pass
        for sel in ("input[name='price']", "input[id*='price']"):
            try:
                loc = page.locator(sel)
                if await loc.count():
                    await loc.first.fill("9", timeout=2500)
                    price_ok = True
                    break
            except Exception:
                pass
        shot = RUNTIME / f"filled_etsy_{_ts()}.png"
        await page.screenshot(path=str(shot), full_page=True)
        return {
            "service": "etsy",
            "ok": True,
            "url": page.url,
            "screenshot": str(shot),
            "filled": {"title": title_ok, "description": desc_ok, "price": price_ok},
        }
    finally:
        await page.close()
        await context.close()
        await browser.close()


async def fill_gumroad(p) -> dict[str, Any]:
    browser, context, page = await _open_context(p, "gumroad")
    marker = _mark()
    try:
        await page.goto("https://gumroad.com/l/yupwt/edit", wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(2500)
        # New Gumroad editor may expose different inputs; fill first suitable fields.
        name_ok = summary_ok = desc_ok = False
        for sel in ("input[name='name']", "input[placeholder*='Name' i]", "input[type='text']"):
            try:
                loc = page.locator(sel)
                if await loc.count():
                    await loc.first.fill(f"Gumroad {marker}", timeout=2500)
                    name_ok = True
                    break
            except Exception:
                pass
        for sel in ("textarea[name='custom_summary']", "textarea[placeholder*='summary' i]", "textarea"):
            try:
                loc = page.locator(sel)
                if await loc.count():
                    await loc.first.fill(f"Summary marker {marker}", timeout=2500)
                    summary_ok = True
                    break
            except Exception:
                pass
        for sel in ("div[contenteditable='true']", "textarea[name='description']", "textarea"):
            try:
                loc = page.locator(sel)
                if await loc.count():
                    await loc.first.fill(f"Description marker {marker}", timeout=2500)
                    desc_ok = True
                    break
            except Exception:
                pass
        shot = RUNTIME / f"filled_gumroad_{_ts()}.png"
        await page.screenshot(path=str(shot), full_page=True)
        return {
            "service": "gumroad",
            "ok": True,
            "url": page.url,
            "screenshot": str(shot),
            "filled": {"name": name_ok, "summary": summary_ok, "description": desc_ok},
        }
    finally:
        await page.close()
        await context.close()
        await browser.close()


async def fill_kofi(p) -> dict[str, Any]:
    browser, context, page = await _open_context(p, "kofi")
    marker = _mark()
    try:
        urls = ["https://ko-fi.com/manage/shop", "https://ko-fi.com/manage", "https://ko-fi.com"]
        for u in urls:
            await page.goto(u, wait_until="domcontentloaded", timeout=90000)
            await page.wait_for_timeout(1800)
            if "404" not in page.url and "/404" not in page.url:
                break
        title_ok = desc_ok = price_ok = False
        for sel in ("input[name='title']", "input[type='text']"):
            try:
                loc = page.locator(sel)
                if await loc.count():
                    await loc.first.fill(f"Ko-fi {marker}", timeout=2500)
                    title_ok = True
                    break
            except Exception:
                pass
        for sel in ("textarea[name='description']", "textarea"):
            try:
                loc = page.locator(sel)
                if await loc.count():
                    await loc.first.fill(f"Filled for screenshot evidence {marker}.", timeout=2500)
                    desc_ok = True
                    break
            except Exception:
                pass
        for sel in ("input[name='price']", "input[inputmode='decimal']"):
            try:
                loc = page.locator(sel)
                if await loc.count():
                    await loc.first.fill("9", timeout=2500)
                    price_ok = True
                    break
            except Exception:
                pass
        shot = RUNTIME / f"filled_kofi_{_ts()}.png"
        await page.screenshot(path=str(shot), full_page=True)
        return {
            "service": "kofi",
            "ok": True,
            "url": page.url,
            "screenshot": str(shot),
            "filled": {"title": title_ok, "description": desc_ok, "price": price_ok},
        }
    finally:
        await page.close()
        await context.close()
        await browser.close()


async def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = {"timestamp": datetime.now(timezone.utc).isoformat(), "results": []}
    async with async_playwright() as p:
        for fn in (fill_gumroad, fill_etsy, fill_kofi):
            try:
                out["results"].append(await fn(p))
            except Exception as e:
                out["results"].append({"service": fn.__name__, "ok": False, "error": str(e)})

    path = REPORTS / f"VITO_FILLED_PAGE_EVIDENCE_{_ts()}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(path))
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

