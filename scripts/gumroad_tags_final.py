#!/usr/bin/env python3
"""Final: Swap 'self improvement' tag for 'money' (category already covers self improvement)."""

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SESSION_COOKIE = Path("/tmp/gumroad_cookie.txt").read_text().strip() if Path("/tmp/gumroad_cookie.txt").exists() else ""


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

            # Remove 'self improvement' tag (click pill to remove)
            # Pills are at level 2 from label (l → parentElement → parentElement)
            print("[2] Removing 'self improvement' tag...")
            removed = await page.evaluate("""() => {
                const labels = document.querySelectorAll('label');
                for (const l of labels) {
                    if (l.textContent.trim() !== 'Tags') continue;
                    // Search up multiple levels
                    let parent = l;
                    for (let i = 0; i < 5; i++) {
                        parent = parent.parentElement;
                        if (!parent) break;
                        const buttons = parent.querySelectorAll('button');
                        for (const btn of buttons) {
                            if (btn.offsetParent !== null && btn.textContent.trim() === 'self improvement') {
                                btn.click();
                                return true;
                            }
                        }
                    }
                }
                return false;
            }""")
            print(f"  Removed: {removed}")
            await asyncio.sleep(1)

            # Add 'money' tag via autocomplete
            print("[3] Adding 'money' tag...")
            dvs = page.locator('[data-value]')
            tags_dv = dvs.nth(1)
            await tags_dv.click()
            await asyncio.sleep(0.5)
            await page.keyboard.type("money", delay=80)
            await asyncio.sleep(3)

            # Click first option
            clicked = await page.evaluate("""() => {
                const opts = document.querySelectorAll('[role="option"]');
                for (const opt of opts) {
                    if (opt.offsetParent !== null) {
                        const text = opt.textContent.trim();
                        opt.click();
                        return text;
                    }
                }
                return null;
            }""")
            print(f"  Selected: {clicked}")
            await asyncio.sleep(1)

            # Save
            print("[4] Saving...")
            save = page.locator('button:has-text("Save changes")').first
            if await save.is_visible(timeout=3000):
                await save.click()
                await asyncio.sleep(4)
                print("  Saved!")

        except Exception as e:
            print(f"\nERROR: {e}")
            import traceback; traceback.print_exc()
        finally:
            await browser.close()

    # Verify
    print("\n[VERIFY]")
    import requests
    token = os.getenv("GUMROAD_API_KEY", "")
    r = requests.get("https://api.gumroad.com/v2/products", params={"access_token": token})
    if r.status_code == 200:
        for prod in r.json().get("products", []):
            tags = prod.get('tags', [])
            print(f"  Tags ({len(tags)}): {tags}")
            print(f"  Price: {prod.get('formatted_price')}")
            print(f"  Published: {prod.get('published')}")
            print(f"  URL: {prod.get('short_url')}")


if __name__ == "__main__":
    asyncio.run(run())
