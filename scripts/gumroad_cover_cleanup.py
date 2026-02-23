#!/usr/bin/env python3
"""Delete old $17 cover + 2 duplicate clean covers. Keep only 1 clean cover.
Cover tabs are <a role="tab"> elements, not buttons."""

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

# The old cover starts with this URL fragment
OLD_COVER_SRC_FRAGMENT = "qhwxpetkogb8m13dgizsgjl5cvuq"


async def get_cover_tabs(page):
    """Return list of cover tab info."""
    return await page.evaluate("""() => {
        const tablist = document.querySelector('[role="tablist"][aria-label="Product covers"]');
        if (!tablist) return [];
        const tabs = tablist.querySelectorAll('[role="tab"]');
        return Array.from(tabs).map((tab, i) => {
            const img = tab.querySelector('img');
            return {
                idx: i,
                src: img ? img.src.split('/').pop().substring(0, 20) : '',
                fullSrc: img ? img.src : '',
                selected: tab.getAttribute('aria-selected') === 'true',
            };
        });
    }""")


async def delete_selected_cover(page):
    """After selecting a cover tab, find and click its delete button."""
    # Check for delete button in the main cover preview area
    # When a cover is selected, there should be a delete/remove button somewhere

    # First check what appears after selection
    btns = await page.evaluate("""() => {
        const h2s = document.querySelectorAll('h2');
        for (const h2 of h2s) {
            if (h2.textContent.trim() !== 'Cover') continue;
            let section = h2;
            for (let i = 0; i < 3; i++) section = section.parentElement;
            if (!section) return [];

            const btns = section.querySelectorAll('button');
            const result = [];
            for (const btn of btns) {
                if (btn.offsetParent !== null) {
                    const rect = btn.getBoundingClientRect();
                    result.push({
                        text: btn.textContent.trim().substring(0, 30),
                        ariaLabel: btn.getAttribute('aria-label') || '',
                        hasSvg: !!btn.querySelector('svg'),
                        w: Math.round(rect.width),
                        h: Math.round(rect.height),
                        x: Math.round(rect.x),
                        y: Math.round(rect.y),
                    });
                }
            }
            return result;
        }
        return [];
    }""")
    return btns


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
            print("[1] Loading Product tab...")
            await page.goto("https://gumroad.com/products/wblqda/edit", wait_until="networkidle")
            await asyncio.sleep(3)
            if "login" in page.url.lower():
                print("COOKIE EXPIRED"); return

            # Scroll to Cover
            await page.evaluate("""() => {
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() === 'Cover') {
                        h2.scrollIntoView({behavior: 'instant', block: 'start'});
                        return;
                    }
                }
            }""")
            await asyncio.sleep(1)

            tabs = await get_cover_tabs(page)
            print(f"[2] Cover tabs ({len(tabs)}):")
            for t in tabs:
                marker = " ← OLD $17" if OLD_COVER_SRC_FRAGMENT[:15] in t['src'] else ""
                print(f"    [{t['idx']}] src={t['src']} selected={t['selected']}{marker}")

            # Click the OLD cover tab (first one, with $17)
            print("\n[3] Clicking old $17 cover tab...")
            old_tab = page.locator(f'[role="tab"] img[src*="{OLD_COVER_SRC_FRAGMENT[:15]}"]').first
            if await old_tab.is_visible(timeout=3000):
                await old_tab.click()
                await asyncio.sleep(1)
            else:
                # Try clicking the first tab
                first_tab = page.locator('[role="tablist"][aria-label="Product covers"] [role="tab"]').first
                await first_tab.click()
                await asyncio.sleep(1)

            # Check what buttons are visible now
            btns = await delete_selected_cover(page)
            print(f"  Buttons in cover section:")
            for b in btns:
                print(f"    '{b['text']}' aria='{b['ariaLabel']}' svg={b['hasSvg']} {b['w']}x{b['h']} pos=({b['x']},{b['y']})")

            await page.screenshot(path=str(SCREENSHOTS / "cover_cleanup_01_selected.png"))

            # Look for a delete button — it might appear on hover over the selected tab
            # Or it might be in the preview area as a trash icon
            # Try hovering over the tab itself
            print("\n[4] Hovering over old cover tab...")
            tab_loc = page.locator('[role="tablist"][aria-label="Product covers"] [role="tab"]').first
            await tab_loc.hover()
            await asyncio.sleep(1)

            btns_hover = await delete_selected_cover(page)
            new_btns = [b for b in btns_hover if b not in btns]
            if new_btns:
                print(f"  NEW buttons after hover: {json.dumps(new_btns)}")
            else:
                print(f"  Same buttons after hover (no delete appeared)")
                # Check all buttons again
                for b in btns_hover:
                    print(f"    '{b['text']}' aria='{b['ariaLabel']}' svg={b['hasSvg']} {b['w']}x{b['h']}")

            await page.screenshot(path=str(SCREENSHOTS / "cover_cleanup_02_hover.png"))

            # Try right-click context menu
            print("\n[5] Trying right-click on cover tab...")
            await tab_loc.click(button="right")
            await asyncio.sleep(1)

            # Check for context menu
            ctx_menu = await page.evaluate("""() => {
                const menus = document.querySelectorAll('[role="menu"], [class*="context"], [class*="popup"], [class*="dropdown"]');
                const result = [];
                for (const menu of menus) {
                    if (menu.offsetParent !== null) {
                        result.push({
                            tag: menu.tagName,
                            text: menu.textContent.trim().substring(0, 200),
                        });
                    }
                }
                return result;
            }""")
            print(f"  Context menus: {ctx_menu}")

            await page.screenshot(path=str(SCREENSHOTS / "cover_cleanup_03_rightclick.png"))

            # Close any menu
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)

            # Maybe the delete is via keyboard? Try selecting tab + Delete key
            print("\n[6] Trying Delete/Backspace key on selected tab...")
            await tab_loc.click()
            await asyncio.sleep(0.5)
            await page.keyboard.press("Delete")
            await asyncio.sleep(1)

            tabs_after = await get_cover_tabs(page)
            print(f"  Tabs after Delete: {len(tabs_after)} (was {len(tabs)})")

            if len(tabs_after) == len(tabs):
                await page.keyboard.press("Backspace")
                await asyncio.sleep(1)
                tabs_after2 = await get_cover_tabs(page)
                print(f"  Tabs after Backspace: {len(tabs_after2)}")

            # Check the big preview area for a delete overlay/button
            print("\n[7] Checking big preview area for delete button...")
            preview_btns = await page.evaluate("""() => {
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() !== 'Cover') continue;
                    let section = h2;
                    for (let i = 0; i < 3; i++) section = section.parentElement;
                    if (!section) return [];

                    // The big preview should be a div with role="tabpanel"
                    const panels = section.querySelectorAll('[role="tabpanel"]');
                    const result = [];
                    for (const panel of panels) {
                        if (panel.offsetParent !== null) {
                            // Find all interactive elements in panel
                            const els = panel.querySelectorAll('button, a, [role="button"]');
                            for (const el of els) {
                                if (el.offsetParent !== null) {
                                    result.push({
                                        tag: el.tagName,
                                        text: el.textContent.trim().substring(0, 30),
                                        ariaLabel: el.getAttribute('aria-label') || '',
                                        hasSvg: !!el.querySelector('svg'),
                                    });
                                }
                            }
                        }
                    }

                    // Also check for buttons ANYWHERE in section that look like delete
                    const allBtns = section.querySelectorAll('button');
                    for (const btn of allBtns) {
                        const label = btn.getAttribute('aria-label') || '';
                        const text = btn.textContent.trim();
                        if (label.toLowerCase().includes('delete') ||
                            label.toLowerCase().includes('remove') ||
                            text.toLowerCase().includes('delete') ||
                            text.toLowerCase().includes('remove')) {
                            result.push({
                                tag: 'BUTTON',
                                text,
                                ariaLabel: label,
                                hasSvg: !!btn.querySelector('svg'),
                                visible: btn.offsetParent !== null,
                            });
                        }
                    }
                    return result;
                }
                return [];
            }""")
            print(f"  Preview/delete buttons: {json.dumps(preview_btns, indent=2)}")

            await page.screenshot(path=str(SCREENSHOTS / "cover_cleanup_04_final.png"))

        except Exception as e:
            print(f"\nERROR: {e}")
            import traceback; traceback.print_exc()
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(run())
