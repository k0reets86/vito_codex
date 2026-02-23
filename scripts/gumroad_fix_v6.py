#!/usr/bin/env python3
"""V6: Tags via React Select data-value click + Cover via button[0] menu."""

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
            # STEP 1: TAGS via React Select
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

            # Click the React Select value container (the one that intercepts clicks)
            # Then find the focused input and type tags
            tags_added = False

            # Click the data-value div
            rs_container = page.locator('[data-value]').first
            try:
                await rs_container.click()
                await asyncio.sleep(1)

                # Check active element
                active = await page.evaluate("""() => {
                    const el = document.activeElement;
                    return {tag: el.tagName, id: el.id, type: el.type || ''};
                }""")
                print(f"  Active after data-value click: {active}")

                if active['tag'] == 'INPUT':
                    for tag in TAGS:
                        await page.keyboard.type(tag, delay=30)
                        await asyncio.sleep(0.5)
                        await page.keyboard.press("Enter")
                        await asyncio.sleep(0.5)
                    tags_added = True
                    print(f"  Added {len(TAGS)} tags!")
                else:
                    # Focus the input manually
                    await page.evaluate("""() => {
                        const containers = document.querySelectorAll('[class*="b62m3t"]');
                        for (const c of containers) {
                            const inp = c.querySelector('input');
                            if (inp) { inp.focus(); return true; }
                        }
                        return false;
                    }""")
                    await asyncio.sleep(0.5)
                    for tag in TAGS:
                        await page.keyboard.type(tag, delay=30)
                        await asyncio.sleep(0.3)
                        await page.keyboard.press("Enter")
                        await asyncio.sleep(0.5)
                    tags_added = True
                    print(f"  Added {len(TAGS)} tags via JS focus!")
            except Exception as e:
                print(f"  Tags error: {e}")

            await page.screenshot(path=str(SCREENSHOTS / "v6_02_tags.png"))

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

            print("[4] Cover...")

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

            # Click the visible button in cover section (50x48, the "+" add button)
            cover_uploaded = False

            # Mark the button
            await page.evaluate("""() => {
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() !== 'Cover') continue;
                    let el = h2;
                    for (let i = 0; i < 3; i++) el = el.parentElement;
                    if (!el) return;
                    const btns = el.querySelectorAll('button');
                    for (const btn of btns) {
                        if (btn.offsetParent !== null && btn.textContent.trim() === '') {
                            btn.setAttribute('data-cover-plus-v6', 'true');
                            return;
                        }
                    }
                }
            }""")

            plus_btn = page.locator('[data-cover-plus-v6="true"]').first
            try:
                if await plus_btn.is_visible(timeout=3000):
                    # Click the + button
                    await plus_btn.click()
                    await asyncio.sleep(2)
                    await page.screenshot(path=str(SCREENSHOTS / "v6_03_plus_clicked.png"))

                    # Check what appeared — menu? file chooser?
                    # Look for "Computer files", "Upload", or file input
                    comp = page.locator('button:has-text("Computer files")').first
                    unsplash = page.locator('button:has-text("Unsplash")').first
                    url_opt = page.locator('button:has-text("URL")').first

                    # Check what menu items are visible
                    for name, loc in [("Computer files", comp), ("Unsplash", unsplash), ("URL", url_opt)]:
                        try:
                            if await loc.is_visible(timeout=2000):
                                print(f"  Menu item visible: {name}")
                        except Exception:
                            pass

                    # Click "Computer files" if visible
                    try:
                        if await comp.is_visible(timeout=3000):
                            async with page.expect_file_chooser(timeout=10000) as fc_info:
                                await comp.click()
                            chooser = await fc_info.value
                            await chooser.set_files(COVER_PATH)
                            print("  Cover uploaded via + → Computer files!")
                            cover_uploaded = True
                            await asyncio.sleep(5)
                        else:
                            print("  Computer files not visible after + click")
                            # Maybe the + button IS the file trigger and we need to check for new file inputs
                            fi_all = await page.locator('input[type="file"]').all()
                            print(f"  File inputs: {len(fi_all)}")
                            for i, fi in enumerate(fi_all):
                                accept = await fi.evaluate("el => el.accept || ''")
                                print(f"    [{i}] accept={accept}")
                    except Exception as e:
                        print(f"  Computer files error: {e}")
            except Exception as e:
                print(f"  Cover error: {e}")

            if not cover_uploaded:
                # Last resort: force-show the hidden "Upload images or videos" button and click it
                try:
                    shown = await page.evaluate("""() => {
                        const h2s = document.querySelectorAll('h2');
                        for (const h2 of h2s) {
                            if (h2.textContent.trim() !== 'Cover') continue;
                            let el = h2;
                            for (let i = 0; i < 3; i++) el = el.parentElement;
                            if (!el) return false;
                            const btns = el.querySelectorAll('button');
                            for (const btn of btns) {
                                if (btn.textContent.includes('Upload images or videos')) {
                                    // Force show it
                                    btn.style.display = 'block';
                                    btn.style.visibility = 'visible';
                                    btn.style.opacity = '1';
                                    btn.style.position = 'relative';
                                    btn.style.width = 'auto';
                                    btn.style.height = 'auto';
                                    btn.setAttribute('data-forced-upload', 'true');
                                    return true;
                                }
                            }
                            return false;
                        }
                        return false;
                    }""")
                    print(f"  Forced upload button visible: {shown}")

                    if shown:
                        await asyncio.sleep(1)
                        forced_btn = page.locator('[data-forced-upload="true"]').first
                        await forced_btn.click()
                        await asyncio.sleep(2)
                        await page.screenshot(path=str(SCREENSHOTS / "v6_04_forced_upload.png"))

                        comp = page.locator('button:has-text("Computer files")').first
                        try:
                            if await comp.is_visible(timeout=3000):
                                async with page.expect_file_chooser(timeout=10000) as fc_info:
                                    await comp.click()
                                chooser = await fc_info.value
                                await chooser.set_files(COVER_PATH)
                                print("  Cover uploaded via forced Upload button!")
                                cover_uploaded = True
                                await asyncio.sleep(5)
                        except Exception as e:
                            print(f"  Forced upload comp files error: {e}")
                except Exception as e:
                    print(f"  Force show error: {e}")

            await page.screenshot(path=str(SCREENSHOTS / "v6_05_cover_done.png"))

            # Save
            if cover_uploaded:
                await page.evaluate("window.scrollTo(0, 0)")
                await asyncio.sleep(1)
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
            print(f"  Name: {prod.get('name')}")
            print(f"  Price: {prod.get('formatted_price')}")
            print(f"  PWYW: {prod.get('customizable_price')}")
            print(f"  Covers: {len(prod.get('covers', []))}")
            print(f"  Tags: {prod.get('tags', [])}")


if __name__ == "__main__":
    asyncio.run(run())
