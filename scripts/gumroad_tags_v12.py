#!/usr/bin/env python3
"""V12: Add more tags (building on existing 5). Try: money, make money, artificial intelligence, digital products."""

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

# Additional tags to add (existing: self improvement, ai, passive income, chatgpt, ebook)
TAG_SEARCHES = ["make money online", "artificial intelligence", "digital products", "self help", "money"]


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

            # Mark Tags container (2nd [data-value])
            await page.evaluate("""() => {
                const dvs = document.querySelectorAll('[data-value]');
                if (dvs[1]) dvs[1].setAttribute('data-vito-tags', 'true');
            }""")
            tags_container = page.locator('[data-vito-tags="true"]').first

            print("[2] Adding more tags...")
            tags_added = 0

            for search_term in TAG_SEARCHES:
                await tags_container.click()
                await asyncio.sleep(0.5)
                await page.keyboard.type(search_term, delay=80)
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

                if options:
                    print(f"  '{search_term}' → {options[:3]}")
                    await page.evaluate("""() => {
                        const opts = document.querySelectorAll('[role="option"]');
                        for (const opt of opts) {
                            if (opt.offsetParent !== null) { opt.click(); return; }
                        }
                    }""")
                    tags_added += 1
                    await asyncio.sleep(1)
                else:
                    print(f"  '{search_term}' → no options")
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(0.3)

            print(f"\n  Added {tags_added} more tags. Saving...")
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
    print("\n[VERIFY via API]")
    import requests
    token = os.getenv("GUMROAD_API_KEY", "")
    r = requests.get("https://api.gumroad.com/v2/products", params={"access_token": token})
    if r.status_code == 200:
        for prod in r.json().get("products", []):
            tags = prod.get('tags', [])
            print(f"  Tags ({len(tags)}): {tags}")


if __name__ == "__main__":
    asyncio.run(run())
