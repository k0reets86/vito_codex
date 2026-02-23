#!/usr/bin/env python3
"""V10 FINAL: Upload cover + add tags (second [data-value] = Tags, not Category)."""

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

TAG_SEARCHES = ["ai", "passive income", "chatgpt", "ebook", "side hustle", "money", "self improvement"]


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
            # STEP 1: COVER — re-upload
            # ==========================================
            print("[1] Loading Product tab...")
            await page.goto("https://gumroad.com/products/wblqda/edit", wait_until="networkidle")
            await asyncio.sleep(3)
            if "login" in page.url.lower():
                print("COOKIE EXPIRED"); return

            print("[2] Uploading cover...")

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

            # Click + button in cover section
            await page.evaluate("""() => {
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() !== 'Cover') continue;
                    let el = h2;
                    for (let i = 0; i < 3; i++) el = el.parentElement;
                    if (!el) return;
                    const btns = el.querySelectorAll('button');
                    for (const btn of btns) {
                        if (btn.offsetParent !== null && btn.getBoundingClientRect().width < 60) {
                            btn.click();
                            return;
                        }
                    }
                }
            }""")
            await asyncio.sleep(2)

            # Click "Upload images or videos" panel
            upload_btn = page.locator('button:has-text("Upload images or videos")').first
            if await upload_btn.is_visible(timeout=5000):
                await upload_btn.click()
                await asyncio.sleep(2)

                # Modal with "Computer files" and "External link" should appear
                # Find file input [2] (accepts .mov/.mp4) and upload
                fi_all = await page.locator('input[type="file"]').all()
                cover_uploaded = False
                for fi in fi_all:
                    accept = await fi.evaluate("el => el.accept || ''")
                    if ".mov" in accept or ".mp4" in accept:
                        await fi.set_input_files(COVER_PATH)
                        print("  Cover uploaded via file input (video-accepting)!")
                        cover_uploaded = True
                        await asyncio.sleep(6)
                        break

                if not cover_uploaded:
                    # Try Computer files button
                    comp = page.locator('button:has-text("Computer files")').first
                    try:
                        if await comp.is_visible(timeout=3000):
                            async with page.expect_file_chooser(timeout=10000) as fc_info:
                                await comp.click()
                            chooser = await fc_info.value
                            await chooser.set_files(COVER_PATH)
                            print("  Cover uploaded via Computer files!")
                            cover_uploaded = True
                            await asyncio.sleep(6)
                    except Exception as e:
                        print(f"  Computer files error: {e}")

                if cover_uploaded:
                    await page.screenshot(path=str(SCREENSHOTS / "v10_01_cover.png"))
                    # Save
                    await page.evaluate("window.scrollTo(0, 0)")
                    await asyncio.sleep(1)
                    save = page.locator('button:has-text("Save changes")').first
                    if await save.is_visible(timeout=3000):
                        await save.click()
                        await asyncio.sleep(4)
                        print("  Saved!")
            else:
                print("  Upload panel not visible after + click")

            # ==========================================
            # STEP 2: TAGS — use SECOND [data-value] (Tags, not Category)
            # ==========================================
            print("\n[3] Loading Share tab...")
            await page.goto("https://gumroad.com/products/wblqda/edit/share", wait_until="networkidle")
            await asyncio.sleep(3)

            print("[4] Adding tags...")

            # Scroll to Tags label
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

            # Find ALL [data-value] elements and identify which is Tags vs Category
            all_dv = await page.evaluate("""() => {
                const dvs = document.querySelectorAll('[data-value]');
                return Array.from(dvs).map((d, i) => ({
                    i,
                    dataValue: d.getAttribute('data-value'),
                    classes: d.className.toString().substring(0, 80),
                    parentText: d.parentElement?.textContent.trim().substring(0, 50) || '',
                    visible: d.offsetParent !== null,
                }));
            }""")
            print(f"  All [data-value] elements ({len(all_dv)}):")
            for dv in all_dv:
                print(f"    [{dv['i']}] val='{dv['dataValue']}' vis={dv['visible']} parent='{dv['parentText'][:40]}'")

            # The Tags one should be the one with empty data-value and parent containing "Tags"
            # or the second visible one (first is Category with "Self Improvement")
            tags_idx = None
            for dv in all_dv:
                if 'Tags' in dv.get('parentText', '') or 'tag' in dv.get('parentText', '').lower():
                    tags_idx = dv['i']
                    break
            if tags_idx is None and len(all_dv) >= 2:
                tags_idx = 1  # Second one is Tags

            if tags_idx is not None:
                print(f"\n  Using [data-value] index {tags_idx} for Tags")

                # Mark it
                await page.evaluate(f"""() => {{
                    const dvs = document.querySelectorAll('[data-value]');
                    if (dvs[{tags_idx}]) dvs[{tags_idx}].setAttribute('data-tags-input', 'true');
                }}""")

                tags_container = page.locator('[data-tags-input="true"]').first
                tags_added = 0

                for search_term in TAG_SEARCHES:
                    await tags_container.click()
                    await asyncio.sleep(0.5)

                    # Clear
                    await page.keyboard.press("Control+a")
                    await page.keyboard.press("Backspace")
                    await asyncio.sleep(0.3)

                    # Type slowly
                    await page.keyboard.type(search_term, delay=80)
                    await asyncio.sleep(3)  # Wait for autocomplete

                    # Take screenshot for first tag
                    if tags_added == 0:
                        await page.screenshot(path=str(SCREENSHOTS / "v10_02_tag_dropdown.png"))

                    # Check dropdown options
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
                        print(f"  '{search_term}' → {len(options)} options: {options[:3]}")
                        # Click first option
                        await page.evaluate("""() => {
                            const opts = document.querySelectorAll('[role="option"]');
                            for (const opt of opts) {
                                if (opt.offsetParent !== null) {
                                    opt.click();
                                    return;
                                }
                            }
                        }""")
                        tags_added += 1
                        await asyncio.sleep(1)
                    else:
                        print(f"  '{search_term}' → no options")
                        await page.keyboard.press("Escape")
                        await asyncio.sleep(0.3)

                print(f"\n  Tags added: {tags_added}")

            await page.screenshot(path=str(SCREENSHOTS / "v10_03_tags.png"))

            # Save
            save = page.locator('button:has-text("Save changes")').first
            if await save.is_visible(timeout=3000):
                await save.click()
                await asyncio.sleep(4)
                print("  Saved!")

            await page.screenshot(path=str(SCREENSHOTS / "v10_04_final.png"), full_page=True)

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
            print(f"  Thumbnail: {bool(prod.get('thumbnail_url'))}")
            print(f"  URL: {prod.get('short_url')}")


if __name__ == "__main__":
    asyncio.run(run())
