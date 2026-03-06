#!/usr/bin/env python3
"""Capture listing page evidence screenshots + extracted field snapshot.

Services:
- gumroad (target listing edit page)
- etsy (listing editor page)
- kofi (manage shop page)
"""

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


def _storage_path(name: str) -> Path:
    mapping = {
        "etsy": RUNTIME / "etsy_storage_state.json",
        "kofi": RUNTIME / "kofi_storage_state.json",
        "gumroad": RUNTIME / "gumroad_storage_state.json",
    }
    return mapping[name]


async def _capture_with_storage(playwright, service: str, url: str) -> dict[str, Any]:
    storage = _storage_path(service)
    if not storage.exists():
        return {"service": service, "ok": False, "error": "storage_state_missing", "storage_state": str(storage)}

    browser = await playwright.chromium.launch(
        headless=os.getenv("VITO_BROWSER_HEADLESS", "1").lower() not in {"0", "false", "no"},
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
    )
    context = await browser.new_context(
        storage_state=str(storage),
        viewport={"width": 1400, "height": 950},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    )
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(2200)
        shot = RUNTIME / f"evidence_{service}_{_ts()}.png"
        html = RUNTIME / f"evidence_{service}_{_ts()}.html"
        await page.screenshot(path=str(shot), full_page=True)
        html.write_text(await page.content(), encoding="utf-8")

        data: dict[str, Any] = {
            "service": service,
            "ok": True,
            "url": page.url,
            "screenshot": str(shot),
            "html": str(html),
            "signals": {},
        }
        if service == "etsy":
            data["signals"] = await page.evaluate(
                """() => {
                    const title = document.querySelector("input[name='title']")?.value || "";
                    const descr = document.querySelector("textarea[name='description']")?.value || "";
                    const price = document.querySelector("input[name='price']")?.value || "";
                    const pubBtn = !!document.querySelector("#shop-manager--listing-publish");
                    const listingId = (location.href.match(/\\/listing\\/(\\d+)/)?.[1]) || "";
                    return {
                        title_len: title.length,
                        description_len: descr.length,
                        price,
                        publish_button_present: pubBtn,
                        listing_id: listingId,
                    };
                }"""
            )
        elif service == "kofi":
            data["signals"] = await page.evaluate(
                """() => {
                    const title = document.querySelector("input[name='title'],input[type='text']")?.value || "";
                    const descr = document.querySelector("textarea")?.value || "";
                    const price = document.querySelector("input[name='price'],input[inputmode='decimal']")?.value || "";
                    const hasPublish = [...document.querySelectorAll("button")].some(b => /publish|save|create/i.test((b.textContent||"").trim()));
                    return {
                        title_len: title.length,
                        description_len: descr.length,
                        price,
                        action_button_present: hasPublish,
                    };
                }"""
            )
        elif service == "gumroad":
            data["signals"] = await page.evaluate(
                """() => {
                    const script = document.querySelector('script[data-component-name=\"ProductEditPage\"]');
                    let parsed = null;
                    try { parsed = script ? JSON.parse(script.textContent || "{}") : null; } catch(_) {}
                    const product = parsed?.product || {};
                    return {
                        product_name: product.name || "",
                        summary_len: (product.custom_summary || "").length,
                        description_len: (product.description || "").length,
                        taxonomy_id: String(product.taxonomy_id || ""),
                        tags_count: (product.tags || []).length,
                        is_published: !!product.is_published,
                    };
                }"""
            )
        return data
    finally:
        await page.close()
        await context.close()
        await browser.close()


async def main() -> int:
    gumroad_slug = os.getenv("GUMROAD_TEST_SLUG", "yupwt").strip()
    plan = [
        ("gumroad", f"https://gumroad.com/l/{gumroad_slug}/edit"),
        ("etsy", "https://www.etsy.com/your/shops/me/listing-editor/create"),
        ("kofi", "https://ko-fi.com/manage/shop"),
    ]
    out: dict[str, Any] = {"timestamp": datetime.now(timezone.utc).isoformat(), "captures": []}
    async with async_playwright() as p:
        for service, url in plan:
            try:
                res = await _capture_with_storage(p, service, url)
            except Exception as e:
                res = {"service": service, "ok": False, "error": str(e), "url": url}
            out["captures"].append(res)

    REPORTS.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS / f"VITO_LISTING_EVIDENCE_{_ts()}.json"
    report_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(report_path))
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

