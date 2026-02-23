#!/usr/bin/env python3
"""V2: Find tag pills at correct DOM level, test removal, test autocomplete."""

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

            # Find tag pills — search multiple DOM levels from Tags label
            pills = await page.evaluate("""() => {
                const labels = document.querySelectorAll('label');
                for (const l of labels) {
                    if (l.textContent.trim() !== 'Tags') continue;

                    // Search up to 5 levels up from label
                    let parent = l;
                    for (let lvl = 0; lvl < 6; lvl++) {
                        parent = parent.parentElement;
                        if (!parent) break;

                        // Find buttons with tag-like styling
                        const buttons = parent.querySelectorAll('button.inline-flex, button[class*="pill"], button[class*="badge"], button[class*="tag"]');
                        if (buttons.length > 0) {
                            const result = [];
                            for (const btn of buttons) {
                                if (btn.offsetParent !== null) {
                                    const text = btn.textContent.trim();
                                    if (text.length > 0 && text.length < 30) {
                                        result.push({text, level: lvl, classes: btn.className?.toString().substring(0, 80) || ''});
                                    }
                                }
                            }
                            if (result.length > 0) return result;
                        }

                        // Also try: any button with inline-flex class
                        const allBtns = parent.querySelectorAll('button');
                        const flexBtns = [];
                        for (const btn of allBtns) {
                            if (btn.offsetParent !== null && btn.className?.toString().includes('inline-flex')) {
                                const text = btn.textContent.trim();
                                if (text.length > 0 && text.length < 30) {
                                    flexBtns.push({text, level: lvl, classes: btn.className?.toString().substring(0, 80) || ''});
                                }
                            }
                        }
                        if (flexBtns.length > 0) return flexBtns;
                    }
                }

                // Fallback: search entire page for buttons matching known tags
                const knownTags = ['self improvement', 'ai', 'passive income', 'chatgpt', 'ebook'];
                const found = [];
                const allBtns = document.querySelectorAll('button');
                for (const btn of allBtns) {
                    const text = btn.textContent.trim().toLowerCase();
                    if (btn.offsetParent !== null && knownTags.includes(text)) {
                        found.push({
                            text: btn.textContent.trim(),
                            level: -1,
                            classes: btn.className?.toString().substring(0, 80) || '',
                            parentTag: btn.parentElement?.tagName || '',
                        });
                    }
                }
                return found.length > 0 ? found : [];
            }""")
            print(f"[2] Tag pills ({len(pills)}):")
            for p_info in pills:
                print(f"    '{p_info['text']}' lvl={p_info.get('level')} cls={p_info.get('classes', '')[:60]}")

            await page.screenshot(path=str(SCREENSHOTS / "swap2_01_initial.png"))

            if not pills:
                # Broader search: dump ALL visible buttons on page
                all_btns = await page.evaluate("""() => {
                    const btns = document.querySelectorAll('button');
                    const result = [];
                    for (const btn of btns) {
                        if (btn.offsetParent !== null) {
                            const text = btn.textContent.trim();
                            if (text.length > 0 && text.length < 40) {
                                result.push({text, classes: btn.className?.toString().substring(0, 60) || ''});
                            }
                        }
                    }
                    return result;
                }""")
                print(f"\n  ALL visible buttons ({len(all_btns)}):")
                for b in all_btns:
                    print(f"    '{b['text']}' cls={b['classes'][:50]}")
                return

            # Click the first tag pill to test removal
            tag_text = pills[0]['text']
            print(f"\n[3] Clicking tag pill '{tag_text}'...")
            pill_btn = page.locator(f'button:has-text("{tag_text}")').first
            await pill_btn.click()
            await asyncio.sleep(1)

            # Check if tag was removed
            pills_after = await page.evaluate("""() => {
                const knownTags = ['self improvement', 'ai', 'passive income', 'chatgpt', 'ebook'];
                const found = [];
                const allBtns = document.querySelectorAll('button');
                for (const btn of allBtns) {
                    const text = btn.textContent.trim().toLowerCase();
                    if (btn.offsetParent !== null && knownTags.includes(text)) {
                        found.push(btn.textContent.trim());
                    }
                }
                return found;
            }""")
            print(f"  Tags after click: {pills_after} (was {len(pills)}, now {len(pills_after)})")

            if len(pills_after) < len(pills):
                print("  TAG REMOVED by clicking!")
            else:
                print("  Not removed — tag pills are NOT remove-on-click")

            await page.screenshot(path=str(SCREENSHOTS / "swap2_02_after_click.png"))

            # Now test autocomplete
            print(f"\n[4] Testing autocomplete (current tag count: {len(pills_after)})...")
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
            expanded = await page.evaluate("""() => {
                const dvs = document.querySelectorAll('[data-value]');
                const input = dvs[1]?.querySelector('input');
                return input?.getAttribute('aria-expanded');
            }""")
            print(f"  Autocomplete options: {options[:5]}")
            print(f"  aria-expanded: {expanded}")

            await page.screenshot(path=str(SCREENSHOTS / "swap2_03_autocomplete.png"))

        except Exception as e:
            print(f"\nERROR: {e}")
            import traceback; traceback.print_exc()
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(run())
