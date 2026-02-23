#!/usr/bin/env python3
"""Fix: Use Playwright click (not JS) to remove tag pill. JS .click() fails on React."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SESSION_COOKIE = Path("/tmp/gumroad_cookie.txt").read_text().strip() if Path("/tmp/gumroad_cookie.txt").exists() else ""


async def get_tag_pills(page):
    """Get current tag pills as list of strings."""
    return await page.evaluate("""() => {
        const labels = document.querySelectorAll('label');
        for (const l of labels) {
            if (l.textContent.trim() !== 'Tags') continue;
            let parent = l;
            for (let i = 0; i < 5; i++) {
                parent = parent.parentElement;
                if (!parent) break;
                const buttons = parent.querySelectorAll('button.inline-flex');
                if (buttons.length > 0) {
                    return Array.from(buttons)
                        .filter(b => b.offsetParent !== null && b.textContent.trim().length < 30)
                        .map(b => b.textContent.trim());
                }
            }
        }
        return [];
    }""")


async def scroll_to_tags(page):
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
            # ========== STEP 1: Remove 'self improvement' via Playwright click ==========
            print("[STEP 1] Remove 'self improvement' tag via Playwright click...")
            await page.goto("https://gumroad.com/products/wblqda/edit/share", wait_until="networkidle")
            await asyncio.sleep(3)
            if "login" in page.url.lower():
                print("COOKIE EXPIRED"); return

            await scroll_to_tags(page)
            pills = await get_tag_pills(page)
            print(f"  Before: {pills}")

            # Use Playwright locator click (NOT JS click)
            pill_btn = page.locator('button.inline-flex:has-text("self improvement")').first
            if await pill_btn.is_visible(timeout=3000):
                await pill_btn.click()
                await asyncio.sleep(2)
                pills_after = await get_tag_pills(page)
                print(f"  After Playwright click: {pills_after}")

                if len(pills_after) < len(pills):
                    print("  TAG REMOVED! Saving...")
                    save = page.locator('button:has-text("Save changes")').first
                    if await save.is_visible(timeout=3000):
                        await save.click()
                        await asyncio.sleep(5)
                        print("  Saved!")
                else:
                    print("  Tag NOT removed. Trying force click...")
                    await pill_btn.click(force=True)
                    await asyncio.sleep(2)
                    pills_force = await get_tag_pills(page)
                    print(f"  After force click: {pills_force}")
                    if len(pills_force) < len(pills):
                        print("  TAG REMOVED with force! Saving...")
                        save = page.locator('button:has-text("Save changes")').first
                        if await save.is_visible(timeout=3000):
                            await save.click()
                            await asyncio.sleep(5)
                            print("  Saved!")
            else:
                print("  'self improvement' pill not found!")

            # ========== STEP 2: Reload and add 'money' ==========
            print("\n[STEP 2] Reload and add 'money'...")
            await page.goto("https://gumroad.com/products/wblqda/edit/share", wait_until="networkidle")
            await asyncio.sleep(3)
            await scroll_to_tags(page)

            pills_now = await get_tag_pills(page)
            print(f"  After reload: {pills_now} ({len(pills_now)} tags)")

            if len(pills_now) < 5:
                dvs = page.locator('[data-value]')
                tags_dv = dvs.nth(1)
                await tags_dv.click()
                await asyncio.sleep(0.5)
                await page.keyboard.type("money", delay=80)
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
                print(f"  Options: {options[:3]}")

                if options:
                    await page.evaluate("""() => {
                        const opts = document.querySelectorAll('[role="option"]');
                        for (const opt of opts) {
                            if (opt.offsetParent !== null) { opt.click(); return; }
                        }
                    }""")
                    await asyncio.sleep(1)

                    save = page.locator('button:has-text("Save changes")').first
                    if await save.is_visible(timeout=3000):
                        await save.click()
                        await asyncio.sleep(5)
                        print("  Saved!")
            else:
                print("  Still 5 tags — can't add more")

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
            print(f"  Tags ({len(prod.get('tags', []))}): {prod.get('tags', [])}")


if __name__ == "__main__":
    asyncio.run(run())
