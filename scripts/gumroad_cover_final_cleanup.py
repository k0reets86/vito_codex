#!/usr/bin/env python3
"""Delete covers: hover tab → click 'Remove cover' overlay (div, top-right, aria-label).
Target: Remove OLD $17 cover + 2 duplicate clean covers. Keep only 1 clean cover."""

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

OLD_COVER_FRAGMENT = "qhwxpetkogb8m13d"  # The $17 cover


async def get_cover_tabs(page):
    """Return cover tab info."""
    return await page.evaluate("""() => {
        const tabs = document.querySelectorAll('[role="tablist"][aria-label="Product covers"] [role="tab"]');
        return Array.from(tabs).map((tab, i) => {
            const img = tab.querySelector('img');
            return {
                idx: i,
                src: img ? img.src.split('/').pop().substring(0, 25) : '',
                fullSrc: img ? img.src : '',
            };
        });
    }""")


async def remove_cover_at_index(page, idx):
    """Hover tab at index to reveal 'Remove cover' button, then click it."""
    # Get the tab
    tabs = page.locator('[role="tablist"][aria-label="Product covers"] [role="tab"]')
    tab = tabs.nth(idx)

    if not await tab.is_visible(timeout=3000):
        print(f"    Tab {idx} not visible")
        return False

    # Hover to reveal the Remove cover overlay
    await tab.hover()
    await asyncio.sleep(1)

    # Click the "Remove cover" overlay
    remove_btn = page.locator('[aria-label="Remove cover"]').first
    if await remove_btn.is_visible(timeout=3000):
        await remove_btn.click()
        await asyncio.sleep(2)
        print(f"    Removed cover at index {idx}")
        return True
    else:
        # Try force click
        try:
            await remove_btn.click(force=True)
            await asyncio.sleep(2)
            print(f"    Force-removed cover at index {idx}")
            return True
        except Exception as e:
            print(f"    Failed to remove: {e}")
            return False


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

            # Get current covers
            tabs = await get_cover_tabs(page)
            print(f"[2] Current covers ({len(tabs)}):")
            for t in tabs:
                marker = " ← OLD $17 DELETE" if OLD_COVER_FRAGMENT in t['src'] else ""
                print(f"    [{t['idx']}] {t['src']}{marker}")

            # Plan: delete the $17 cover + keep only 1 of the clean ones
            # Clean covers all have same content (3ih4, zm3i, op6h)
            # So delete: [0] = old $17, [2] = duplicate, [3] = duplicate
            # Keep: [1] = clean cover

            # Delete from highest index to lowest to avoid index shifting issues
            to_delete = []
            for t in tabs:
                if OLD_COVER_FRAGMENT in t['src']:
                    to_delete.append(t['idx'])  # $17 cover
            # Also mark duplicates for deletion (keep only the first clean one)
            clean_covers = [t for t in tabs if OLD_COVER_FRAGMENT not in t['src']]
            if len(clean_covers) > 1:
                # Keep the first clean, delete the rest
                for c in clean_covers[1:]:
                    to_delete.append(c['idx'])

            # Sort descending to delete from end first
            to_delete.sort(reverse=True)
            print(f"\n[3] Will delete indices: {to_delete} (keep 1 clean cover)")

            for idx in to_delete:
                # Need to re-get tabs because indices shift after deletion
                current_tabs = await get_cover_tabs(page)
                print(f"\n  Current tabs: {len(current_tabs)}")

                # Find the target in current tabs
                # After deletion, indices shift. Use src fragment to find the right one
                target_src = tabs[idx]['src']
                current_idx = None
                for ct in current_tabs:
                    if target_src in ct['src']:
                        current_idx = ct['idx']
                        break

                if current_idx is not None:
                    print(f"  Deleting tab at current index {current_idx} (src={target_src})...")
                    result = await remove_cover_at_index(page, current_idx)
                    if result:
                        await asyncio.sleep(1)
                else:
                    print(f"  Tab with src={target_src} not found in current tabs")

            # Final state
            final_tabs = await get_cover_tabs(page)
            print(f"\n[4] Remaining covers ({len(final_tabs)}):")
            for t in final_tabs:
                print(f"    [{t['idx']}] {t['src']}")

            await page.screenshot(path=str(SCREENSHOTS / "cover_final_01.png"))

            # Save
            print("\n[5] Saving...")
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)
            save = page.locator('button:has-text("Save changes")').first
            if await save.is_visible(timeout=3000):
                await save.click()
                await asyncio.sleep(5)
                print("  Saved!")

            await page.screenshot(path=str(SCREENSHOTS / "cover_final_02.png"))

        except Exception as e:
            print(f"\nERROR: {e}")
            import traceback; traceback.print_exc()
        finally:
            await browser.close()

    # Verify
    print("\n[VERIFY]")
    import requests
    token = os.getenv("GUMROAD_API_KEY", "")
    r = requests.get("https://api.gumroad.com/v2/products/KHs6M8x50i9rb0vkABJurw==",
                     params={"access_token": token})
    if r.status_code == 200:
        prod = r.json().get('product', {})
        print(f"  Preview URL: {prod.get('preview_url', 'NONE')}")
        print(f"  Thumbnail URL: {prod.get('thumbnail_url', 'NONE')}")
        print(f"  Tags: {prod.get('tags', [])}")
        print(f"  Price: {prod.get('formatted_price')}")


if __name__ == "__main__":
    asyncio.run(run())
