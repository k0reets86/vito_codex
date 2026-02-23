#!/usr/bin/env python3
"""Check for overlapping delete button by examining elements at tab position after hover."""

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

            # Get tab position
            tab_pos = await page.evaluate("""() => {
                const tabs = document.querySelectorAll('[role="tablist"][aria-label="Product covers"] [role="tab"]');
                if (!tabs[0]) return null;
                const rect = tabs[0].getBoundingClientRect();
                return {x: rect.x, y: rect.y, w: rect.width, h: rect.height, right: rect.right, bottom: rect.bottom};
            }""")
            print(f"[2] First tab position: {tab_pos}")

            # Hover over the first tab (old cover)
            first_tab = page.locator('[role="tablist"][aria-label="Product covers"] [role="tab"]').first
            await first_tab.hover()
            await asyncio.sleep(1)

            # Check elements at the tab's position using elementsFromPoint
            if tab_pos:
                overlap = await page.evaluate(f"""() => {{
                    const x = {tab_pos['x'] + tab_pos['w']/2};
                    const y = {tab_pos['y'] + tab_pos['h']/2};
                    const topRight = document.elementsFromPoint({tab_pos['right'] - 5}, {tab_pos['y'] + 5});
                    const center = document.elementsFromPoint(x, y);

                    function desc(els) {{
                        return els.slice(0, 8).map(el => ({{
                            tag: el.tagName,
                            text: el.textContent?.trim().substring(0, 20) || '',
                            ariaLabel: el.getAttribute('aria-label') || '',
                            cls: (el.className?.toString() || '').substring(0, 40),
                            hasSvg: !!el.querySelector('svg'),
                        }}));
                    }}
                    return {{
                        center: desc(center),
                        topRight: desc(topRight),
                    }};
                }}""")
                print(f"  Elements at center: {json.dumps(overlap['center'][:4])}")
                print(f"  Elements at top-right: {json.dumps(overlap['topRight'][:4])}")

            # Screenshot
            await page.screenshot(path=str(SCREENSHOTS / "cover_overlay_01.png"))

            # Also: look at the tab's children dynamically after hover
            tab_children_after_hover = await page.evaluate("""() => {
                const tab = document.querySelectorAll('[role="tablist"][aria-label="Product covers"] [role="tab"]')[0];
                if (!tab) return null;
                return {
                    childCount: tab.children.length,
                    html: tab.innerHTML,
                    outerHTML: tab.outerHTML.substring(0, 500),
                };
            }""")
            print(f"\n[3] Tab HTML after hover:")
            print(f"  Children: {tab_children_after_hover.get('childCount')}")
            print(f"  HTML: {tab_children_after_hover.get('html')[:300]}")

            # Try: maybe there's a drag-and-drop API approach?
            # Or maybe the cover can be deleted via the Gumroad API somehow?
            # Check if there are any API requests when interacting with covers
            print("\n[4] Checking if Gumroad has a covers API endpoint...")
            import requests
            token = os.getenv("GUMROAD_API_KEY", "")

            # Try GET product details with all fields
            r = requests.get("https://api.gumroad.com/v2/products/KHs6M8x50i9rb0vkABJurw==",
                           params={"access_token": token})
            if r.status_code == 200:
                prod = r.json().get('product', {})
                covers = prod.get('covers', [])
                print(f"  Product covers from API: {len(covers)}")
                for i, c in enumerate(covers):
                    print(f"    [{i}] {json.dumps(c)[:100]}")

                # Check all cover-related fields
                for key in sorted(prod.keys()):
                    if 'cover' in key.lower() or 'image' in key.lower() or 'thumb' in key.lower() or 'preview' in key.lower():
                        val = prod[key]
                        if isinstance(val, str):
                            val = val[:100]
                        print(f"  {key}: {val}")
            else:
                print(f"  API error: {r.status_code}")

        except Exception as e:
            print(f"\nERROR: {e}")
            import traceback; traceback.print_exc()
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(run())
