#!/usr/bin/env python3
"""Test: Remove one tag pill, see if autocomplete unlocks. Then add better tag back."""

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SESSION_COOKIE = Path("/tmp/gumroad_cookie.txt").read_text().strip() if Path("/tmp/gumroad_cookie.txt").exists() else ""
SCREENSHOTS = Path(__file__).resolve().parent.parent / "output/screenshots"
SCREENSHOTS.mkdir(parents=True, exist_ok=True)


async def run():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 1400},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        )
        await ctx.add_cookies([{
            "name": "_gumroad_app_session", "value": SESSION_COOKIE,
            "domain": ".gumroad.com", "path": "/", "httpOnly": True, "secure": True, "sameSite": "Lax",
        }])
        page = await ctx.new_page()
        page.set_default_timeout(20000)

        try:
            print("[1] Loading Share tab...")
            await page.goto("https://gumroad.com/products/wblqda/edit/share", wait_until="networkidle")
            await asyncio.sleep(3)
            if "login" in page.url.lower():
                print("COOKIE EXPIRED"); return

            # Scroll to Tags
            await page.evaluate("""() => {
                const labels = document.querySelectorAll('label');
                for (const l of labels) {
                    if (l.textContent.trim() === 'Tags') {
                        l.scrollIntoView({behavior: 'instant', block: 'start'});
                        return;
                    }
                }
            }""")
            await asyncio.sleep(1)

            # List current tag pills
            pills = await page.evaluate("""() => {
                const labels = document.querySelectorAll('label');
                for (const l of labels) {
                    if (l.textContent.trim() !== 'Tags') continue;
                    let parent = l.parentElement;
                    const buttons = parent.querySelectorAll('button');
                    const result = [];
                    for (const btn of buttons) {
                        if (btn.offsetParent !== null) {
                            const text = btn.textContent.trim();
                            if (text.length > 0 && text.length < 30) {
                                // Check if there's an X/close icon (SVG or ×)
                                const hasSvg = !!btn.querySelector('svg');
                                const hasX = text.includes('×') || text.includes('✕') || text.includes('x');
                                btn.setAttribute('data-tag-pill', text);
                                result.push({text, hasSvg, hasX, idx: result.length});
                            }
                        }
                    }
                    return result;
                }
                return [];
            }""")
            print(f"[2] Current tag pills ({len(pills)}):")
            for p_info in pills:
                print(f"    '{p_info['text']}' svg={p_info['hasSvg']} x={p_info['hasX']}")

            if not pills:
                print("  No tag pills found!")
                return

            # Click on the first tag pill to see if it has delete functionality
            # Try clicking the tag - it might be a toggle or have an X button
            print(f"\n[3] Clicking tag pill '{pills[0]['text']}' to test removal...")
            first_pill = page.locator(f'button[data-tag-pill="{pills[0]["text"]}"]').first
            await first_pill.click()
            await asyncio.sleep(1)

            # Check if anything changed (maybe the pill was removed)
            pills_after = await page.evaluate("""() => {
                const labels = document.querySelectorAll('label');
                for (const l of labels) {
                    if (l.textContent.trim() !== 'Tags') continue;
                    let parent = l.parentElement;
                    const buttons = parent.querySelectorAll('button');
                    const result = [];
                    for (const btn of buttons) {
                        if (btn.offsetParent !== null) {
                            const text = btn.textContent.trim();
                            if (text.length > 0 && text.length < 30) {
                                result.push(text);
                            }
                        }
                    }
                    return result;
                }
                return [];
            }""")
            print(f"  After click: {pills_after}")

            removed = len(pills_after) < len(pills)
            if removed:
                print(f"  TAG REMOVED! (click to remove works)")
            else:
                print(f"  Tag NOT removed. Count same ({len(pills_after)})")

            await page.screenshot(path=str(SCREENSHOTS / "swap_01_after_click.png"))

            # Now try the autocomplete
            print(f"\n[4] Testing autocomplete after removal...")
            dvs = page.locator('[data-value]')
            tags_dv = dvs.nth(1)
            await tags_dv.click()
            await asyncio.sleep(0.5)
            await page.keyboard.type("money", delay=100)
            await asyncio.sleep(3)

            options = await page.evaluate("""() => {
                const opts = document.querySelectorAll('[role="option"]');
                const result = [];
                for (const opt of opts) {
                    if (opt.offsetParent !== null) {
                        result.push(opt.textContent.trim().substring(0, 60));
                    }
                }
                return result;
            }""")
            print(f"  Autocomplete options for 'money': {options[:5]}")

            expanded = await page.evaluate("""() => {
                const dvs = document.querySelectorAll('[data-value]');
                const input = dvs[1]?.querySelector('input');
                return input?.getAttribute('aria-expanded');
            }""")
            print(f"  aria-expanded: {expanded}")

            if options:
                print(f"\n  CONFIRMED: Tag limit was the issue! Autocomplete works after removal.")
                # Click first option to add new tag
                await page.evaluate("""() => {
                    const opts = document.querySelectorAll('[role="option"]');
                    for (const opt of opts) {
                        if (opt.offsetParent !== null) { opt.click(); return; }
                    }
                }""")
                await asyncio.sleep(1)
                print("  Added 'money' tag")
            else:
                print(f"\n  Autocomplete still dead. Not a tag limit issue.")

            await page.screenshot(path=str(SCREENSHOTS / "swap_02_after_autocomplete.png"))

            # Final state
            pills_final = await page.evaluate("""() => {
                const labels = document.querySelectorAll('label');
                for (const l of labels) {
                    if (l.textContent.trim() !== 'Tags') continue;
                    let parent = l.parentElement;
                    const buttons = parent.querySelectorAll('button');
                    const result = [];
                    for (const btn of buttons) {
                        if (btn.offsetParent !== null) {
                            const text = btn.textContent.trim();
                            if (text.length > 0 && text.length < 30) result.push(text);
                        }
                    }
                    return result;
                }
                return [];
            }""")
            print(f"\n[5] Final tags: {pills_final}")

            # Don't save yet — just testing
            print("\n  NOT saving — this was a test run.")

        except Exception as e:
            print(f"\nERROR: {e}")
            import traceback; traceback.print_exc()
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(run())
