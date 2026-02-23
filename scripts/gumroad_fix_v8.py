#!/usr/bin/env python3
"""V8: Debug tags dropdown + cover click without file_chooser expectation."""

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

TAGS = ["ai", "passive income", "chatgpt", "ebook", "side hustle"]


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
            # STEP 1: TAGS — debug dropdown
            # ==========================================
            print("[1] Loading Share tab...")
            await page.goto("https://gumroad.com/products/wblqda/edit/share", wait_until="networkidle")
            await asyncio.sleep(3)
            if "login" in page.url.lower():
                print("COOKIE EXPIRED"); return

            print("[2] Tags debug...")

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

            # Click value container to focus
            rs_container = page.locator('[data-value]').first
            await rs_container.click()
            await asyncio.sleep(1)

            # Type first tag and wait to see dropdown
            await page.keyboard.type("ai", delay=50)
            await asyncio.sleep(2)  # Wait for dropdown

            # Take screenshot to see what dropdown appeared
            await page.screenshot(path=str(SCREENSHOTS / "v8_01_tag_dropdown.png"))

            # Check for dropdown menu
            dropdown = await page.evaluate("""() => {
                // React Select dropdown is usually a div with role="listbox" or class containing "menu"
                const menus = document.querySelectorAll('[class*="menu"], [role="listbox"]');
                const result = [];
                for (const menu of menus) {
                    if (menu.offsetParent !== null) {
                        const options = menu.querySelectorAll('[role="option"], [class*="option"]');
                        result.push({
                            tag: menu.tagName,
                            classes: menu.className.toString().substring(0, 80),
                            visible: true,
                            options: Array.from(options).map(o => ({
                                text: o.textContent.trim().substring(0, 60),
                                ariaSelected: o.getAttribute('aria-selected'),
                            })),
                        });
                    }
                }
                return result;
            }""")
            print(f"  Dropdowns: {dropdown}")

            # If there are options, click the first one
            if dropdown and dropdown[0].get('options'):
                print(f"  First option: {dropdown[0]['options'][0]['text']}")
                # Click it via JS
                clicked_opt = await page.evaluate("""() => {
                    const options = document.querySelectorAll('[role="option"], [class*="option"]');
                    for (const opt of options) {
                        if (opt.offsetParent !== null) {
                            opt.click();
                            return opt.textContent.trim().substring(0, 60);
                        }
                    }
                    return null;
                }""")
                print(f"  Clicked option: {clicked_opt}")
                await asyncio.sleep(1)

                # Check if tag appeared
                chips = await page.evaluate("""() => {
                    const container = document.querySelector('[data-value]');
                    if (!container) return [];
                    // React Select multi-value items
                    const all = container.querySelectorAll('div');
                    const chips = [];
                    for (const d of all) {
                        // Multi-value items usually have class containing "multiValue"
                        if (d.className && d.className.toString().includes('multiValue')) {
                            chips.push(d.textContent.trim());
                        }
                    }
                    // Also check data-value attribute
                    const dv = container.getAttribute('data-value');
                    return {chips, dataValue: dv};
                }""")
                print(f"  After click: {chips}")

            # Add remaining tags by typing and selecting from dropdown
            for tag in TAGS[1:]:
                await rs_container.click()
                await asyncio.sleep(0.5)
                await page.keyboard.type(tag, delay=30)
                await asyncio.sleep(1)

                # Click first dropdown option
                await page.evaluate("""() => {
                    const options = document.querySelectorAll('[role="option"], [class*="option"]');
                    for (const opt of options) {
                        if (opt.offsetParent !== null) {
                            opt.click();
                            return;
                        }
                    }
                }""")
                await asyncio.sleep(0.5)

            await page.screenshot(path=str(SCREENSHOTS / "v8_02_tags_done.png"))

            # Check final tags state
            final_state = await page.evaluate("""() => {
                const container = document.querySelector('[data-value]');
                return container ? container.getAttribute('data-value') : 'no container';
            }""")
            print(f"  Final data-value: '{final_state}'")

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

            # Click + button
            await page.evaluate("""() => {
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() !== 'Cover') continue;
                    let el = h2;
                    for (let i = 0; i < 3; i++) el = el.parentElement;
                    if (!el) return;
                    const btns = el.querySelectorAll('button');
                    for (const btn of btns) {
                        const rect = btn.getBoundingClientRect();
                        if (btn.offsetParent !== null && rect.width < 60 && rect.height < 60) {
                            btn.click();
                            return;
                        }
                    }
                }
            }""")
            await asyncio.sleep(2)

            # Now click "Upload images or videos" WITHOUT expecting file chooser
            upload_btn = page.locator('button:has-text("Upload images or videos")').first
            if await upload_btn.is_visible(timeout=5000):
                await upload_btn.click()
                await asyncio.sleep(3)
                await page.screenshot(path=str(SCREENSHOTS / "v8_03_after_upload_click.png"))

                # Check what happened — modal? new inputs? file dialog?
                # Look for any new elements
                new_elements = await page.evaluate("""() => {
                    const result = [];
                    // Check for modals
                    const modals = document.querySelectorAll('[role="dialog"], .modal, [class*="modal"], [class*="overlay"]');
                    for (const m of modals) {
                        if (m.offsetParent !== null) {
                            result.push({type: 'modal', text: m.textContent.trim().substring(0, 100)});
                        }
                    }
                    // Check file inputs
                    const fis = document.querySelectorAll('input[type="file"]');
                    for (const fi of fis) {
                        result.push({type: 'file-input', accept: fi.accept, visible: fi.offsetParent !== null});
                    }
                    // Check for drag-drop zone
                    const dropzones = document.querySelectorAll('[class*="dropzone"], [class*="drag"]');
                    for (const dz of dropzones) {
                        if (dz.offsetParent !== null) {
                            result.push({type: 'dropzone', text: dz.textContent.trim().substring(0, 100)});
                        }
                    }
                    // Check for "Computer files" button
                    const btns = document.querySelectorAll('button');
                    for (const btn of btns) {
                        if (btn.offsetParent !== null && btn.textContent.includes('Computer')) {
                            result.push({type: 'button', text: btn.textContent.trim()});
                        }
                    }
                    return result;
                }""")
                print(f"  After upload click elements: {new_elements}")

                # Check if file inputs appeared
                fi_all = await page.locator('input[type="file"]').all()
                print(f"  File inputs: {len(fi_all)}")
                for i, fi in enumerate(fi_all):
                    accept = await fi.evaluate("el => el.accept || ''")
                    print(f"    [{i}] accept={accept}")
                    if ".mov" in accept or ".mp4" in accept or ".wmv" in accept or ".mpeg" in accept:
                        await fi.set_input_files(COVER_PATH)
                        print(f"  Cover uploaded via file input [{i}]!")
                        await asyncio.sleep(5)
                        break
                else:
                    # Try the first image-accepting input
                    for i, fi in enumerate(fi_all):
                        accept = await fi.evaluate("el => el.accept || ''")
                        if ".jpg" in accept or ".png" in accept:
                            multiple = await fi.evaluate("el => el.multiple")
                            print(f"  Trying image input [{i}] multiple={multiple}")
                            await fi.set_input_files(COVER_PATH)
                            await asyncio.sleep(5)
                            break

            else:
                print("  Upload button not visible")

            await page.screenshot(path=str(SCREENSHOTS / "v8_04_cover_done.png"))

            # Save
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)
            save = page.locator('button:has-text("Save changes")').first
            if await save.is_visible(timeout=3000):
                await save.click()
                await asyncio.sleep(4)
                print("  Saved!")

            await page.screenshot(path=str(SCREENSHOTS / "v8_05_final.png"), full_page=True)

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
