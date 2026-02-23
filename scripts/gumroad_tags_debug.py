#!/usr/bin/env python3
"""Debug: Why no autocomplete options when page loads with existing tags."""

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
                        l.scrollIntoView({behavior: 'instant', block: 'center'});
                        return;
                    }
                }
            }""")
            await asyncio.sleep(1)

            # Deep inspection of Tags React Select
            tags_info = await page.evaluate("""() => {
                const dvs = document.querySelectorAll('[data-value]');
                if (dvs.length < 2) return { error: 'less than 2 [data-value]' };
                const el = dvs[1]; // Tags

                // Get the full React Select container (parent hierarchy)
                let rsContainer = el;
                while (rsContainer && !rsContainer.className.toString().includes('container')) {
                    rsContainer = rsContainer.parentElement;
                }

                // Find the hidden input
                const hiddenInput = rsContainer ? rsContainer.querySelector('input[type="hidden"]') : null;
                const visibleInput = rsContainer ? rsContainer.querySelector('input:not([type="hidden"])') : null;

                // Find all multi-value items
                const multiValues = el.querySelectorAll('[class*="multiValue"]');
                const singleValue = el.querySelector('[class*="singleValue"]');

                // Check placeholder
                const placeholder = el.querySelector('[class*="placeholder"]');

                // Full HTML of the data-value container
                const html = el.innerHTML;

                return {
                    dataValue: el.getAttribute('data-value'),
                    containerClass: rsContainer ? rsContainer.className.toString().substring(0, 100) : 'not found',
                    hiddenInputName: hiddenInput ? hiddenInput.name : 'none',
                    hiddenInputValue: hiddenInput ? hiddenInput.value : 'none',
                    visibleInputValue: visibleInput ? visibleInput.value : 'none',
                    visibleInputPlaceholder: visibleInput ? visibleInput.placeholder : 'none',
                    multiValueCount: multiValues.length,
                    multiValues: Array.from(multiValues).map(mv => mv.textContent.trim()),
                    singleValue: singleValue ? singleValue.textContent.trim() : 'none',
                    placeholder: placeholder ? placeholder.textContent.trim() : 'none',
                    htmlLength: html.length,
                    htmlSnippet: html.substring(0, 500),
                };
            }""")
            print(f"[2] Tags React Select state:")
            print(json.dumps(tags_info, indent=2))

            # Take screenshot
            await page.screenshot(path=str(SCREENSHOTS / "debug_tags_01_initial.png"))

            # Now try clicking and typing
            print("\n[3] Clicking Tags container...")
            dvs = page.locator('[data-value]')
            tags_dv = dvs.nth(1)
            await tags_dv.click()
            await asyncio.sleep(1)

            # Check what element has focus
            focus_info = await page.evaluate("""() => {
                const el = document.activeElement;
                return {
                    tag: el.tagName,
                    type: el.type || '',
                    value: el.value || '',
                    placeholder: el.placeholder || '',
                    className: el.className.toString().substring(0, 80),
                    id: el.id || '',
                    ariaAutocomplete: el.getAttribute('aria-autocomplete') || '',
                };
            }""")
            print(f"  Focused element: {json.dumps(focus_info)}")

            # Type "money"
            print("\n[4] Typing 'money'...")
            await page.keyboard.type("money", delay=100)
            await asyncio.sleep(3)

            # Check what appeared
            after_type = await page.evaluate("""() => {
                // Check all role=option
                const options = document.querySelectorAll('[role="option"]');
                const visibleOpts = [];
                for (const opt of options) {
                    if (opt.offsetParent !== null) {
                        visibleOpts.push(opt.textContent.trim().substring(0, 60));
                    }
                }

                // Check all menus
                const menus = document.querySelectorAll('[class*="menu"], [role="listbox"]');
                const visibleMenus = [];
                for (const menu of menus) {
                    if (menu.offsetParent !== null) {
                        visibleMenus.push({
                            classes: menu.className.toString().substring(0, 80),
                            text: menu.textContent.trim().substring(0, 200),
                            childCount: menu.children.length,
                        });
                    }
                }

                // Check focused input value
                const input = document.activeElement;

                return {
                    optionCount: visibleOpts.length,
                    options: visibleOpts,
                    menuCount: visibleMenus.length,
                    menus: visibleMenus,
                    inputValue: input.value || '',
                    inputTag: input.tagName,
                };
            }""")
            print(f"  After typing: {json.dumps(after_type, indent=2)}")

            await page.screenshot(path=str(SCREENSHOTS / "debug_tags_02_typed.png"))

            # Check for "No options" message
            no_options = await page.evaluate("""() => {
                const els = document.querySelectorAll('[class*="noOptions"], [class*="NoOptions"]');
                const result = [];
                for (const el of els) {
                    if (el.offsetParent !== null) {
                        result.push(el.textContent.trim());
                    }
                }
                // Also check for any "No" text in menu area
                const menus = document.querySelectorAll('[class*="menu"]');
                for (const menu of menus) {
                    if (menu.offsetParent !== null) {
                        result.push('MENU: ' + menu.textContent.trim().substring(0, 100));
                    }
                }
                return result;
            }""")
            print(f"  No options messages: {no_options}")

            # Try: clear all and type "ai" (which we KNOW works)
            print("\n[5] Testing with known working tag 'ai'...")
            await page.keyboard.press("Control+a")
            await page.keyboard.press("Backspace")
            await asyncio.sleep(0.5)
            await page.keyboard.type("ai", delay=100)
            await asyncio.sleep(3)

            ai_opts = await page.evaluate("""() => {
                const opts = document.querySelectorAll('[role="option"]');
                const result = [];
                for (const opt of opts) {
                    if (opt.offsetParent !== null) {
                        result.push(opt.textContent.trim().substring(0, 60));
                    }
                }
                return result;
            }""")
            print(f"  'ai' options: {ai_opts[:5]}")

            await page.screenshot(path=str(SCREENSHOTS / "debug_tags_03_ai.png"))

        except Exception as e:
            print(f"\nERROR: {e}")
            import traceback; traceback.print_exc()
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(run())
