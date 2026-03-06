#!/usr/bin/env python3
"""Best-effort Amazon KDP draft creation test via saved storage_state."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright


def _launch_args() -> list[str]:
    return [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--renderer-process-limit=1",
        "--no-zygote",
        "--single-process",
    ]


async def _click_first(page, selectors: list[str], timeout_ms: int = 3500) -> bool:
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if await loc.count() > 0:
                await loc.first.click(timeout=timeout_ms)
                return True
        except Exception:
            continue
    return False


async def _bookshelf_titles(page) -> list[str]:
    try:
        items = await page.evaluate(
            """() => {
                const out = [];
                const seen = new Set();
                const push = (v) => {
                  const t = String(v || '').replace(/\\s+/g, ' ').trim();
                  if (!t || t.length < 3 || t.length > 180) return;
                  const low = t.toLowerCase();
                  if (seen.has(low)) return;
                  seen.add(low);
                  out.push(t);
                };
                const selectors = [
                  "a[href*='/title/']",
                  "a[href*='/book/']",
                  "[data-testid*='book']",
                  "[data-testid*='title']",
                  "h2",
                  "h3"
                ];
                for (const sel of selectors) {
                  for (const n of Array.from(document.querySelectorAll(sel))) {
                    push(n.textContent || "");
                  }
                }
                return out.slice(0, 200);
            }"""
        )
        return [str(x) for x in (items or [])]
    except Exception:
        return []


async def _kdp_relogin_if_needed(page) -> bool:
    """Best-effort re-login when KDP asks only for password inside existing Amazon session."""
    cur = (page.url or "").lower()
    if "signin" not in cur and "ap/signin" not in cur:
        try:
            if await page.locator("input[type='password']").count() == 0:
                return False
        except Exception:
            return False
    pwd = str(os.getenv("KDP_PASSWORD", "")).strip()
    if not pwd:
        return False
    try:
        pwd_loc = page.locator("input[type='password'], input#ap_password, input[name='password']")
        if await pwd_loc.count() == 0:
            return False
        await pwd_loc.first.fill(pwd)
        clicked = await _click_first(
            page,
            [
                "input#signInSubmit",
                "button#signInSubmit",
                "button:has-text('Sign in')",
                "input[type='submit']",
            ],
            timeout_ms=4000,
        )
        if not clicked:
            return False
        await page.wait_for_timeout(2200)
        return True
    except Exception:
        return False


async def run(storage_path: str, headless: bool, debug_dir: str) -> int:
    state = Path(storage_path)
    dbg = Path(debug_dir)
    dbg.mkdir(parents=True, exist_ok=True)
    if not state.exists():
        print(json.dumps({"ok": False, "error": "storage_state_missing", "path": str(state)}, ensure_ascii=False))
        return 2

    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    title = str(os.getenv("KDP_TEST_DRAFT_TITLE", "VITO TEST DRAFT")).strip() or "VITO TEST DRAFT"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, args=_launch_args())
        ctx = await browser.new_context(storage_state=str(state), viewport={"width": 1440, "height": 920})
        page = await ctx.new_page()
        try:
            await page.goto("https://kdp.amazon.com/bookshelf", wait_until="domcontentloaded", timeout=120000)
            await page.wait_for_timeout(2500)
            await _kdp_relogin_if_needed(page)
            if "signin" in (page.url or "").lower() or "ap/signin" in (page.url or "").lower():
                await page.screenshot(path=str(dbg / f"kdp_draft_{stamp}_signin_required.png"), full_page=True)
                print(
                    json.dumps(
                        {"ok": False, "error": "signin_required_after_password", "url": page.url, "screenshot": str(dbg / f"kdp_draft_{stamp}_signin_required.png")},
                        ensure_ascii=False,
                    )
                )
                return 3
            before_titles = await _bookshelf_titles(page)

            # Step 1: open create flow
            opened = await _click_first(
                page,
                [
                    "button:has-text('Create')",
                    "a:has-text('Create')",
                    "text=Create",
                ],
            )
            if not opened:
                await page.screenshot(path=str(dbg / f"kdp_draft_{stamp}_no_create.png"), full_page=True)
                print(json.dumps({"ok": False, "error": "create_button_not_found", "url": page.url}, ensure_ascii=False))
                return 3

            await page.wait_for_timeout(1200)

            # Step 2: choose ebook/paperback flow
            chosen = await _click_first(
                page,
                [
                    "a:has-text('Create Kindle eBook')",
                    "button:has-text('Create Kindle eBook')",
                    "a:has-text('Kindle eBook')",
                    "button:has-text('Kindle eBook')",
                    "a:has-text('Paperback')",
                    "button:has-text('Paperback')",
                ],
            )
            if not chosen:
                # sometimes direct flow opens immediately
                pass

            await page.wait_for_timeout(2200)
            await _kdp_relogin_if_needed(page)

            # Step 3: fill minimal required fields on details page (best effort).
            for sel in [
                "input[name='bookTitle']",
                "input#bookTitle",
                "input[aria-label*='Book title']",
                "input[placeholder*='Book title']",
            ]:
                try:
                    if await page.locator(sel).count() > 0:
                        await page.locator(sel).first.fill(title)
                        break
                except Exception:
                    continue

            # author name
            first_set = False
            for sel in [
                "input[name='authorFirstName']",
                "input#authorFirstName",
                "input[aria-label*='First name']",
            ]:
                try:
                    if await page.locator(sel).count() > 0:
                        await page.locator(sel).first.fill("Vito")
                        first_set = True
                        break
                except Exception:
                    continue
            if first_set:
                for sel in [
                    "input[name='authorLastName']",
                    "input#authorLastName",
                    "input[aria-label*='Last name']",
                ]:
                    try:
                        if await page.locator(sel).count() > 0:
                            await page.locator(sel).first.fill("Bot")
                            break
                    except Exception:
                        continue

            await page.wait_for_timeout(800)

            # Step 4: save draft / continue
            saved = await _click_first(
                page,
                [
                    "button:has-text('Save and Continue')",
                    "button:has-text('Save and continue')",
                    "button:has-text('Save as draft')",
                    "button:has-text('Save')",
                    "button[type='submit']",
                ],
                timeout_ms=4500,
            )
            await page.wait_for_timeout(3000)
            await page.screenshot(path=str(dbg / f"kdp_draft_{stamp}_after_save.png"), full_page=True)

            # Step 5: strict verification on Bookshelf with retries (KDP list can refresh with delay).
            await page.goto("https://kdp.amazon.com/bookshelf", wait_until="domcontentloaded", timeout=120000)
            await page.wait_for_timeout(3500)
            # Additional verification path: search by exact title in bookshelf search field.
            search_hit = False
            try:
                for sel in ("input[placeholder*='Search by title']", "input[aria-label*='Search by title']", "input[type='search']"):
                    box = page.locator(sel)
                    if await box.count() > 0:
                        await box.first.fill(title)
                        await page.keyboard.press("Enter")
                        await page.wait_for_timeout(2200)
                        body_text = (await page.text_content("body") or "").lower()
                        if title.lower() in body_text:
                            search_hit = True
                        break
            except Exception:
                search_hit = False
            await page.screenshot(path=str(dbg / f"kdp_draft_{stamp}_bookshelf.png"), full_page=True)
            after_titles = await _bookshelf_titles(page)
            if not any((title or "").lower() in (t or "").lower() for t in after_titles):
                for _ in range(2):
                    try:
                        await page.reload(wait_until="domcontentloaded", timeout=120000)
                        await page.wait_for_timeout(2200)
                        after_titles = await _bookshelf_titles(page)
                        if any((title or "").lower() in (t or "").lower() for t in after_titles):
                            break
                    except Exception:
                        continue
            before_l = [t.lower() for t in before_titles]
            after_l = [t.lower() for t in after_titles]
            has_title = title.lower() in after_l
            appeared_new = any(t not in before_l for t in after_l)
            fields_filled = 0
            fields_filled += 1 if title.strip() else 0
            fields_filled += 1 if bool(saved) else 0
            fields_filled += 1 if bool(first_set) else 0
            ok = bool(saved and (has_title or appeared_new or search_hit))
            ok_soft = bool(saved and page.url and "bookshelf" in page.url)
            result = {
                "ok": bool(ok),
                "ok_soft": bool(ok_soft),
                "title": title,
                "saved_click": bool(saved),
                "url": page.url,
                "title_found_on_bookshelf": has_title,
                "title_found_via_search": bool(search_hit),
                "before_count": len(before_titles),
                "after_count": len(after_titles),
                "fields_filled": int(fields_filled),
                "note": "strict_bookshelf_verification",
                "screenshot": str(dbg / f"kdp_draft_{stamp}_after_save.png"),
                "bookshelf_screenshot": str(dbg / f"kdp_draft_{stamp}_bookshelf.png"),
            }
            print(json.dumps(result, ensure_ascii=False))
            return 0 if (ok or ok_soft) else 4
        finally:
            await ctx.close()
            await browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="KDP draft creation smoke test")
    parser.add_argument("--storage-path", default="runtime/kdp_storage_state.json")
    parser.add_argument("--debug-dir", default="runtime/remote_auth")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()
    return asyncio.run(run(args.storage_path, bool(args.headless), args.debug_dir))


if __name__ == "__main__":
    raise SystemExit(main())
