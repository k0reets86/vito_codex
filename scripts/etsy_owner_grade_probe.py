#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.platform_validation_registry import record_platform_validation_result

RUNTIME = ROOT / "runtime"
PROFILE = ROOT / "runtime" / "browser_profiles" / "etsy"
PROBE = RUNTIME / "etsy_owner_grade_probe.json"
SHOT = RUNTIME / "etsy_owner_grade_probe.png"
LISTING_ID = "4468093570"
URL = f"https://www.etsy.com/your/shops/me/tools/listings/{LISTING_ID}"


async def _probe() -> dict:
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            str(PROFILE),
            headless=True,
            viewport={"width": 1440, "height": 2200},
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(4000)
        try:
            await page.screenshot(path=str(SHOT), full_page=True)
        except Exception:
            pass
        data = await page.evaluate(
            """() => {
                const low = (document.body.innerText || '').toLowerCase();
                const imgs = Array.from(document.querySelectorAll('img'))
                  .map((img) => String(img.getAttribute('src') || ''))
                  .filter((src) => src.includes('etsy') || src.includes('etsystatic'));
                return {
                  ok: true,
                  url: location.href,
                  title: document.title,
                  body_has_instant_download: low.includes('мгновенная загрузка') || low.includes('instant download'),
                  body_has_materials: low.includes('материал') || low.includes('pdf guide') || low.includes('digital download'),
                  body_has_category: low.includes('гиды и справочники') || low.includes('books, movies & music') || low.includes('книги'),
                  body_has_draft: low.includes('черновик') || low.includes('draft'),
                  body_has_pdf: low.includes('.pdf') || low.includes('digital file') || low.includes('upload a digital file'),
                  image_count: imgs.length,
                  etsy_images: imgs.slice(0, 10)
                };
            }"""
        )
        await ctx.close()
        return data


def _as_validation(data: dict) -> dict:
    url = str(data.get("url") or "")
    redirected_to_signin = "/signin" in url or "from_page=" in url
    owner_grade_ok = bool(
        data.get("body_has_instant_download")
        and data.get("body_has_materials")
        and data.get("body_has_category")
        and data.get("body_has_pdf")
        and int(data.get("image_count") or 0) > 0
    )
    blocker = "missing_session" if redirected_to_signin else ""
    state = "owner_grade" if owner_grade_ok else ("blocked" if redirected_to_signin else "partial")
    return {
        "platform": "etsy",
        "mode": "editor_probe",
        "url": url,
        "source": str(PROBE),
        "signals": data,
        "owner_grade_ok": owner_grade_ok,
        "blocker": blocker,
        "state": state,
    }


def main() -> int:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    data = asyncio.run(_probe())
    PROBE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    result = _as_validation(data)
    record_platform_validation_result(result)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
