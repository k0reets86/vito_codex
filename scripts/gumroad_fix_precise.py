#!/usr/bin/env python3
"""Precise fix: disable PWYW checkbox, undo Circle toggle, upload cover, find tags."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SESSION_COOKIE = Path("/tmp/gumroad_cookie.txt").read_text().strip() if Path("/tmp/gumroad_cookie.txt").exists() else ""
EDIT_URL = "https://gumroad.com/products/wblqda/edit"
COVER_PATH = str(Path(__file__).resolve().parent.parent / "output/ai_side_hustle_cover_no_price.png")
SCREENSHOTS = Path(__file__).resolve().parent.parent / "output/screenshots"
SCREENSHOTS.mkdir(parents=True, exist_ok=True)


async def run():
    from playwright.async_api import async_playwright

    if not SESSION_COOKIE:
        print("ERROR: No cookie"); return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 1400},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        await ctx.add_cookies([{
            "name": "_gumroad_app_session", "value": SESSION_COOKIE,
            "domain": ".gumroad.com", "path": "/", "httpOnly": True, "secure": True, "sameSite": "Lax",
        }])
        page = await ctx.new_page()
        page.set_default_timeout(20000)

        try:
            print("[1] Loading...")
            await page.goto(EDIT_URL, wait_until="networkidle")
            await asyncio.sleep(3)
            if "login" in page.url.lower():
                print("ERROR: Cookie expired!"); await browser.close(); return
            print(f"  OK: {page.url}")

            # ============ FIX 1: DISABLE PWYW ============
            print("\n[2] Disabling PWYW...")

            # Find ALL checkboxes and their context text
            checkboxes = await page.evaluate("""() => {
                const cbs = document.querySelectorAll('input[type="checkbox"]');
                return Array.from(cbs).map((cb, i) => {
                    const label = cb.closest('label') || cb.parentElement;
                    const text = label ? label.textContent.trim().substring(0, 80) : '';
                    return {i, checked: cb.checked, text, id: cb.id};
                });
            }""")
            print(f"  All checkboxes ({len(checkboxes)}):")
            for cb in checkboxes:
                print(f"    [{cb['i']}] checked={cb['checked']} text='{cb['text']}'")

            # Click PWYW checkbox to uncheck it
            pwyw_result = await page.evaluate("""() => {
                const cbs = document.querySelectorAll('input[type="checkbox"]');
                for (let i = 0; i < cbs.length; i++) {
                    const label = cbs[i].closest('label') || cbs[i].parentElement;
                    const text = label ? label.textContent : '';
                    if (text.includes('pay what you want') && cbs[i].checked) {
                        cbs[i].click();
                        return {toggled: true, index: i, nowChecked: cbs[i].checked};
                    }
                }
                return {toggled: false};
            }""")
            print(f"  PWYW toggle result: {pwyw_result}")
            await asyncio.sleep(2)

            # Also fix Circle community if accidentally enabled
            circle_result = await page.evaluate("""() => {
                const cbs = document.querySelectorAll('input[type="checkbox"]');
                for (let i = 0; i < cbs.length; i++) {
                    const label = cbs[i].closest('label') || cbs[i].parentElement;
                    const text = label ? label.textContent : '';
                    if (text.includes('Circle community') && cbs[i].checked) {
                        cbs[i].click();
                        return {toggled: true, index: i};
                    }
                }
                return {toggled: false};
            }""")
            print(f"  Circle fix: {circle_result}")
            await asyncio.sleep(1)

            # Verify PWYW is now off
            verify = await page.evaluate("""() => {
                const cbs = document.querySelectorAll('input[type="checkbox"]');
                for (let i = 0; i < cbs.length; i++) {
                    const label = cbs[i].closest('label') || cbs[i].parentElement;
                    const text = label ? label.textContent : '';
                    if (text.includes('pay what you want')) {
                        return {checked: cbs[i].checked};
                    }
                }
                return {found: false};
            }""")
            print(f"  PWYW verify: {verify}")

            await page.screenshot(path=str(SCREENSHOTS / "precise_02_pwyw.png"))

            # ============ SAVE AFTER PWYW FIX ============
            print("\n[2b] Saving...")
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)
            save_btn = page.locator('button:has-text("Save changes")').first
            if await save_btn.is_visible(timeout=3000):
                await save_btn.click()
                await asyncio.sleep(4)
                print("  Saved!")

            # ============ FIX 2: UPLOAD COVER ============
            print("\n[3] Uploading cover...")

            # Scroll down to find Cover section
            found_cover = await page.evaluate("""() => {
                const all = document.querySelectorAll('h2, h3, span, label, div');
                for (const el of all) {
                    if (el.textContent.trim() === 'Cover' && el.offsetParent !== null
                        && el.getBoundingClientRect().height < 50
                        && el.getBoundingClientRect().width < 200) {
                        el.scrollIntoView({behavior: 'instant', block: 'center'});
                        return {found: true, tag: el.tagName, y: el.getBoundingClientRect().y};
                    }
                }
                return {found: false};
            }""")
            print(f"  Cover section: {found_cover}")
            await asyncio.sleep(1)
            await page.screenshot(path=str(SCREENSHOTS / "precise_03a_cover_area.png"))

            # List ALL file inputs
            fi_info = await page.evaluate("""() => {
                const fis = document.querySelectorAll('input[type="file"]');
                return Array.from(fis).map((fi, i) => ({
                    i,
                    accept: fi.accept || 'none',
                    multiple: fi.multiple,
                    visible: fi.offsetParent !== null,
                    rect: fi.getBoundingClientRect(),
                }));
            }""")
            print(f"  File inputs ({len(fi_info)}):")
            for fi in fi_info:
                print(f"    [{fi['i']}] accept={fi['accept'][:60]} multiple={fi['multiple']} visible={fi['visible']}")

            # Try to find cover upload area - look for "Upload images or videos" button
            upload_btn = page.locator('button:has-text("Upload images or videos")').first
            try:
                if await upload_btn.is_visible(timeout=5000):
                    print("  Found 'Upload images or videos' button, clicking...")
                    await upload_btn.click()
                    await asyncio.sleep(2)
                    await page.screenshot(path=str(SCREENSHOTS / "precise_03b_upload_menu.png"))

                    # Now look for "Computer files" button
                    comp_btn = page.locator('button:has-text("Computer files")').first
                    try:
                        if await comp_btn.is_visible(timeout=3000):
                            async with page.expect_file_chooser(timeout=10000) as fc_info:
                                await comp_btn.click()
                            chooser = await fc_info.value
                            await chooser.set_files(COVER_PATH)
                            print("  Cover uploaded via file chooser!")
                            await asyncio.sleep(5)
                        else:
                            print("  'Computer files' not visible")
                    except Exception as e:
                        print(f"  File chooser failed: {e}")
                        # Fallback: try newly appeared file inputs
                        fi_all = await page.locator('input[type="file"]').all()
                        print(f"  File inputs after menu: {len(fi_all)}")
                        for fi in fi_all:
                            accept = await fi.evaluate("el => el.accept || ''")
                            if ".mov" in accept or ".mp4" in accept:
                                await fi.set_input_files(COVER_PATH)
                                print("  Cover uploaded via file input (video-accepting)!")
                                await asyncio.sleep(5)
                                break
                else:
                    print("  'Upload images or videos' not visible")
                    # Maybe cover already has an image - look for replace option
                    # Or try clicking directly in the cover area
            except Exception as e:
                print(f"  Upload button error: {e}")

            # Check if cover was uploaded in a different way
            fi_all = await page.locator('input[type="file"]').all()
            cover_uploaded = False
            for fi in fi_all:
                accept = await fi.evaluate("el => el.accept || ''")
                if ".mov" in accept or ".mp4" in accept:
                    await fi.set_input_files(COVER_PATH)
                    print("  Cover uploaded via fallback file input!")
                    cover_uploaded = True
                    await asyncio.sleep(5)
                    break

            if not cover_uploaded:
                # Last resort: use the first file input (images only)
                # On Gumroad, the cover might use the image-only input on some pages
                print("  Trying first image file input as cover...")
                for fi in fi_all:
                    accept = await fi.evaluate("el => el.accept || ''")
                    if ".jpg" in accept and ".png" in accept:
                        multiple = await fi.evaluate("el => el.multiple")
                        if multiple:
                            await fi.set_input_files(COVER_PATH)
                            print(f"  Cover uploaded via image input (multiple={multiple})!")
                            cover_uploaded = True
                            await asyncio.sleep(5)
                            break

            await page.screenshot(path=str(SCREENSHOTS / "precise_03c_after_cover.png"))

            # Save after cover
            print("\n[3b] Saving...")
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)
            save_btn = page.locator('button:has-text("Save changes")').first
            if await save_btn.is_visible(timeout=3000):
                await save_btn.click()
                await asyncio.sleep(4)
                print("  Saved!")

            # ============ EXPLORE TABS FOR TAGS ============
            print("\n[4] Looking for tags on Share tab...")

            # Click Share tab
            share_tab = page.locator('button:has-text("Share"), a:has-text("Share")').first
            try:
                if await share_tab.is_visible(timeout=3000):
                    await share_tab.click()
                    await asyncio.sleep(3)
                    await page.screenshot(path=str(SCREENSHOTS / "precise_04a_share_tab.png"), full_page=True)

                    # Look for tag/keyword inputs
                    inputs_on_share = await page.evaluate("""() => {
                        const inputs = document.querySelectorAll('input:not([type="hidden"]):not([type="file"]):not([type="checkbox"])');
                        return Array.from(inputs).filter(el => el.offsetParent !== null).map((el, i) => ({
                            i, ph: el.placeholder, type: el.type, value: el.value,
                            ariaLabel: el.getAttribute('aria-label') || '',
                        }));
                    }""")
                    print(f"  Inputs on Share tab:")
                    for inp in inputs_on_share:
                        print(f"    [{inp['i']}] ph={inp['ph']} type={inp['type']} val={inp['value']} aria={inp['ariaLabel']}")

                    # Look for any text containing "tag"
                    tag_sections = await page.evaluate("""() => {
                        const result = [];
                        const els = document.querySelectorAll('*');
                        for (const el of els) {
                            if (el.children.length === 0 && el.textContent.toLowerCase().includes('tag')
                                && el.offsetParent !== null) {
                                result.push({tag: el.tagName, text: el.textContent.trim().substring(0, 100)});
                            }
                        }
                        return result.slice(0, 10);
                    }""")
                    print(f"  'tag' mentions: {tag_sections}")
            except Exception as e:
                print(f"  Share tab error: {e}")

            # Go back to Product tab and check Discover section
            print("\n[5] Looking for tags on Product tab (Discover section)...")
            product_tab = page.locator('button:has-text("Product"), a:has-text("Product")').first
            try:
                if await product_tab.is_visible(timeout=3000):
                    await product_tab.click()
                    await asyncio.sleep(2)
            except Exception:
                pass

            # Scroll to bottom to find Discover/Tags/SEO section
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1)
            await page.screenshot(path=str(SCREENSHOTS / "precise_05a_bottom.png"), full_page=False)

            # Look for discover/tags section
            discover_info = await page.evaluate("""() => {
                const result = [];
                const els = document.querySelectorAll('h2, h3, h4, label, span');
                for (const el of els) {
                    const text = el.textContent.trim().toLowerCase();
                    if (['discover', 'tags', 'seo', 'search', 'category', 'discover'].some(k => text.includes(k))
                        && el.offsetParent !== null) {
                        result.push({tag: el.tagName, text: el.textContent.trim().substring(0, 80),
                                    y: el.getBoundingClientRect().y});
                    }
                }
                return result;
            }""")
            print(f"  Discover/Tags sections: {discover_info}")

            # Check the full page sections
            sections_dump = await page.evaluate("""() => {
                const headings = document.querySelectorAll('h2, h3');
                return Array.from(headings).filter(h => h.offsetParent !== null)
                    .map(h => ({tag: h.tagName, text: h.textContent.trim()}));
            }""")
            print(f"  Page headings: {sections_dump}")

            await page.screenshot(path=str(SCREENSHOTS / "precise_05_final.png"), full_page=True)

        except Exception as e:
            print(f"\nERROR: {e}")
            import traceback; traceback.print_exc()
            try:
                await page.screenshot(path=str(SCREENSHOTS / "precise_99_error.png"), full_page=True)
            except Exception:
                pass
        finally:
            await browser.close()

    # === VERIFY ===
    print("\n[VERIFY] API check...")
    import requests
    token = os.getenv("GUMROAD_API_KEY", "")
    r = requests.get("https://api.gumroad.com/v2/products", params={"access_token": token})
    if r.status_code == 200:
        for prod in r.json().get("products", []):
            print(f"  Name: {prod.get('name')}")
            print(f"  Price: {prod.get('formatted_price')} ({prod.get('price')} cents)")
            print(f"  PWYW: {prod.get('customizable_price')}")
            print(f"  Published: {prod.get('published')}")
            print(f"  Covers: {len(prod.get('covers', []))}")
            print(f"  Tags: {prod.get('tags', [])}")


if __name__ == "__main__":
    print("=" * 60)
    print("Gumroad Precise Fix: PWYW + Cover + Tags")
    print("=" * 60)
    asyncio.run(run())
