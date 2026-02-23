#!/usr/bin/env python3
"""Two-step tag swap: remove + save + reload + add + save."""

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
            # ========== STEP 1: Remove 'self improvement' and save ==========
            print("[STEP 1] Remove 'self improvement' tag...")
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

            # Count pills before
            pills_before = await page.evaluate("""() => {
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
            print(f"  Before: {pills_before}")

            # Remove 'self improvement'
            removed = await page.evaluate("""() => {
                const labels = document.querySelectorAll('label');
                for (const l of labels) {
                    if (l.textContent.trim() !== 'Tags') continue;
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
            await asyncio.sleep(2)

            # Count pills after removal
            pills_after = await page.evaluate("""() => {
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
            print(f"  After removal: {pills_after}")

            # Save
            print("  Saving...")
            save = page.locator('button:has-text("Save changes")').first
            if await save.is_visible(timeout=3000):
                await save.click()
                await asyncio.sleep(5)
                print("  Saved!")

            # ========== STEP 2: Reload and add 'money' ==========
            print("\n[STEP 2] Reload and add 'money' tag...")
            await page.goto("https://gumroad.com/products/wblqda/edit/share", wait_until="networkidle")
            await asyncio.sleep(3)

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

            # Check current pills
            pills_now = await page.evaluate("""() => {
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
            print(f"  After reload: {pills_now} ({len(pills_now)} tags)")

            if len(pills_now) < 5:
                # Good! We can add a new tag
                print("  Adding 'money' tag via autocomplete...")
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
                print(f"  Options: {options[:5]}")

                if options:
                    await page.evaluate("""() => {
                        const opts = document.querySelectorAll('[role="option"]');
                        for (const opt of opts) {
                            if (opt.offsetParent !== null) { opt.click(); return; }
                        }
                    }""")
                    await asyncio.sleep(1)
                    print("  Selected!")

                    # Save
                    save = page.locator('button:has-text("Save changes")').first
                    if await save.is_visible(timeout=3000):
                        await save.click()
                        await asyncio.sleep(5)
                        print("  Saved!")
                else:
                    print("  No autocomplete options! Skipping.")
            else:
                print(f"  Still {len(pills_now)} tags — removal didn't persist?")

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
