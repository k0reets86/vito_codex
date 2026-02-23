#!/usr/bin/env python3
"""V7: Tags with Tab key + Cover via + → 'Upload images or videos' panel."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SESSION_COOKIE = Path("/tmp/gumroad_cookie.txt").read_text().strip() if Path("/tmp/gumroad_cookie.txt").exists() else ""
COVER_PATH = str(Path(__file__).resolve().parent.parent / "output/ai_side_hustle_cover_no_price.png")
SCREENSHOTS = Path(__file__).resolve().parent.parent / "output/screenshots"
SCREENSHOTS.mkdir(parents=True, exist_ok=True)

TAGS = ["ai", "side hustle", "passive income", "chatgpt", "make money online", "ebook", "artificial intelligence"]


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
            # ==========================================
            # STEP 1: TAGS
            # ==========================================
            print("[1] Loading Share tab...")
            await page.goto("https://gumroad.com/products/wblqda/edit/share", wait_until="networkidle")
            await asyncio.sleep(3)
            if "login" in page.url.lower():
                print("COOKIE EXPIRED"); return

            print("[2] Adding tags...")

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

            # Click the React Select value container to focus the input
            rs_container = page.locator('[data-value]').first
            await rs_container.click()
            await asyncio.sleep(1)

            # Verify input is focused
            active = await page.evaluate("() => document.activeElement.tagName")
            print(f"  Focused: {active}")

            if active == 'INPUT':
                for i, tag in enumerate(TAGS):
                    await page.keyboard.type(tag, delay=30)
                    await asyncio.sleep(0.5)

                    # Try Tab to create a custom tag (React Select creates on Tab)
                    await page.keyboard.press("Tab")
                    await asyncio.sleep(0.5)

                    # Check if tag was added (chips should appear)
                    chips = await page.evaluate("""() => {
                        const container = document.querySelector('[data-value]');
                        if (!container) return [];
                        const chips = container.querySelectorAll('[class*="multiValue"], [class*="multi-value"]');
                        return Array.from(chips).map(c => c.textContent.trim());
                    }""")

                    if i == 0:
                        print(f"  After first tag (Tab): chips = {chips}")
                        if not chips:
                            # Tab didn't work, try Enter
                            # Re-focus input
                            await rs_container.click()
                            await asyncio.sleep(0.5)
                            await page.keyboard.type(tag, delay=30)
                            await asyncio.sleep(0.3)
                            await page.keyboard.press("Enter")
                            await asyncio.sleep(0.5)

                            chips2 = await page.evaluate("""() => {
                                const container = document.querySelector('[data-value]');
                                if (!container) return [];
                                const chips = container.querySelectorAll('[class*="multiValue"], [class*="multi-value"]');
                                return Array.from(chips).map(c => c.textContent.trim());
                            }""")
                            print(f"  After retry (Enter): chips = {chips2}")

                            if not chips2:
                                # Try comma separator
                                await rs_container.click()
                                await asyncio.sleep(0.5)
                                await page.keyboard.type(tag, delay=30)
                                await page.keyboard.press(",")
                                await asyncio.sleep(0.5)

                                chips3 = await page.evaluate("""() => {
                                    const container = document.querySelector('[data-value]');
                                    if (!container) return [];
                                    const chips = container.querySelectorAll('[class*="multiValue"], [class*="multi-value"]');
                                    return Array.from(chips).map(c => c.textContent.trim());
                                }""")
                                print(f"  After retry (comma): chips = {chips3}")

                    # Re-click to ensure focus for next tag
                    if i < len(TAGS) - 1:
                        await rs_container.click()
                        await asyncio.sleep(0.3)

                # Check final state
                final_chips = await page.evaluate("""() => {
                    const container = document.querySelector('[data-value]');
                    if (!container) return {chips: [], html: 'no container'};
                    const chips = container.querySelectorAll('[class*="multiValue"], [class*="multi-value"]');
                    return {
                        chips: Array.from(chips).map(c => c.textContent.trim()),
                        html: container.innerHTML.substring(0, 500),
                    };
                }""")
                print(f"\n  Final chips: {final_chips['chips']}")
                if not final_chips['chips']:
                    print(f"  Container HTML: {final_chips['html'][:300]}")

            await page.screenshot(path=str(SCREENSHOTS / "v7_02_tags.png"))

            # Save
            save = page.locator('button:has-text("Save changes")').first
            if await save.is_visible(timeout=3000):
                await save.click()
                await asyncio.sleep(4)
                print("  Saved!")

            # ==========================================
            # STEP 2: COVER
            # ==========================================
            print("\n[3] Loading Product tab...")
            await page.goto("https://gumroad.com/products/wblqda/edit", wait_until="networkidle")
            await asyncio.sleep(3)

            print("[4] Cover: click + then Upload images or videos...")

            # Scroll to Cover
            await page.evaluate("""() => {
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() === 'Cover') {
                        h2.scrollIntoView({behavior: 'instant', block: 'center'});
                        return;
                    }
                }
            }""")
            await asyncio.sleep(1)

            # Click the + button (visible, empty text, 50x48)
            plus_clicked = await page.evaluate("""() => {
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() !== 'Cover') continue;
                    let el = h2;
                    for (let i = 0; i < 3; i++) el = el.parentElement;
                    if (!el) return false;
                    const btns = el.querySelectorAll('button');
                    for (const btn of btns) {
                        if (btn.offsetParent !== null) {
                            // Click the small visible button (the + button)
                            const rect = btn.getBoundingClientRect();
                            if (rect.width < 60 && rect.height < 60) {
                                btn.click();
                                return true;
                            }
                        }
                    }
                    return false;
                }
                return false;
            }""")
            print(f"  + clicked via JS: {plus_clicked}")
            await asyncio.sleep(2)

            # Now the "Upload images or videos" panel should appear at the bottom
            # Click it to trigger file chooser
            cover_uploaded = False
            upload_panel = page.locator('button:has-text("Upload images or videos")').first
            try:
                if await upload_panel.is_visible(timeout=5000):
                    print("  'Upload images or videos' visible!")
                    async with page.expect_file_chooser(timeout=15000) as fc_info:
                        await upload_panel.click()
                    chooser = await fc_info.value
                    await chooser.set_files(COVER_PATH)
                    print("  Cover uploaded via Upload images or videos!")
                    cover_uploaded = True
                    await asyncio.sleep(6)
                else:
                    print("  Upload panel not visible")
            except Exception as e:
                print(f"  Upload panel error: {e}")
                # Maybe clicking opened a file dialog directly
                await asyncio.sleep(2)
                await page.screenshot(path=str(SCREENSHOTS / "v7_04_after_upload_click.png"))

                # Check for "Computer files" in a dropdown
                comp = page.locator('button:has-text("Computer files")').first
                try:
                    if await comp.is_visible(timeout=3000):
                        async with page.expect_file_chooser(timeout=10000) as fc_info:
                            await comp.click()
                        chooser = await fc_info.value
                        await chooser.set_files(COVER_PATH)
                        print("  Cover via Computer files!")
                        cover_uploaded = True
                        await asyncio.sleep(6)
                except Exception:
                    pass

            await page.screenshot(path=str(SCREENSHOTS / "v7_05_cover.png"))

            # Now delete the old cover if new one was uploaded
            if cover_uploaded:
                await asyncio.sleep(2)
                # The old cover thumbnail should still be there
                # Find and delete it (it's the first/smaller thumbnail)
                deleted = await page.evaluate("""() => {
                    const h2s = document.querySelectorAll('h2');
                    for (const h2 of h2s) {
                        if (h2.textContent.trim() !== 'Cover') continue;
                        let el = h2;
                        for (let i = 0; i < 3; i++) el = el.parentElement;
                        if (!el) return false;
                        // Find thumbnail buttons (have img inside)
                        const btns = el.querySelectorAll('button');
                        for (const btn of btns) {
                            if (btn.querySelector('img') && btn.offsetParent !== null) {
                                // Check if this is the old cover (first one)
                                const rect = btn.getBoundingClientRect();
                                if (rect.width < 100) {
                                    // This is a thumbnail - hover and look for X
                                    btn.dispatchEvent(new MouseEvent('mouseenter', {bubbles: true}));
                                    btn.dispatchEvent(new MouseEvent('mouseover', {bubbles: true}));
                                    return {found: true, w: rect.width, h: rect.height};
                                }
                            }
                        }
                        return {found: false};
                    }
                    return {found: false};
                }""")
                print(f"  Old cover thumb: {deleted}")

            # Save
            if cover_uploaded:
                await page.evaluate("window.scrollTo(0, 0)")
                await asyncio.sleep(1)
                save = page.locator('button:has-text("Save changes")').first
                if await save.is_visible(timeout=3000):
                    await save.click()
                    await asyncio.sleep(4)
                    print("  Saved!")

            await page.screenshot(path=str(SCREENSHOTS / "v7_06_final.png"), full_page=True)

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
            print(f"  Name: {prod.get('name')}")
            print(f"  Price: {prod.get('formatted_price')}")
            print(f"  PWYW: {prod.get('customizable_price')}")
            print(f"  Covers: {len(prod.get('covers', []))}")
            print(f"  Tags: {prod.get('tags', [])}")


if __name__ == "__main__":
    asyncio.run(run())
