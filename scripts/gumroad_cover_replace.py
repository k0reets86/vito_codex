#!/usr/bin/env python3
"""Replace old cover ($17) with new cover (no price). Delete old → upload new → save."""

import asyncio
import json
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

            # Step 1: Find all cover thumbnails in Cover section
            thumbs = await page.evaluate("""() => {
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() !== 'Cover') continue;
                    let el = h2;
                    for (let i = 0; i < 3; i++) el = el.parentElement;
                    if (!el) return [];

                    const btns = el.querySelectorAll('button');
                    const result = [];
                    let idx = 0;
                    for (const btn of btns) {
                        if (btn.offsetParent !== null) {
                            const img = btn.querySelector('img');
                            const rect = btn.getBoundingClientRect();
                            result.push({
                                idx,
                                hasImg: !!img,
                                src: img ? img.src.substring(0, 100) : '',
                                w: Math.round(rect.width),
                                h: Math.round(rect.height),
                                text: btn.textContent.trim().substring(0, 20),
                            });
                            idx++;
                        }
                    }
                    return result;
                }
                return [];
            }""")

            print(f"[2] Cover buttons ({len(thumbs)}):")
            for t in thumbs:
                print(f"    [{t['idx']}] img={t['hasImg']} {t['w']}x{t['h']} text='{t['text']}' src={t['src'][:60]}")

            await page.screenshot(path=str(SCREENSHOTS / "cover_replace_01.png"))

            # Step 2: Delete ALL existing covers (click each thumbnail with img)
            # In Gumroad, clicking a thumbnail selects it, then we need to find a delete option
            # From v9 experience: hover shows delete SVG button
            img_thumbs = [t for t in thumbs if t['hasImg']]
            print(f"\n[3] Deleting {len(img_thumbs)} existing covers...")

            for thumb in img_thumbs:
                # Mark the button
                await page.evaluate(f"""() => {{
                    const h2s = document.querySelectorAll('h2');
                    for (const h2 of h2s) {{
                        if (h2.textContent.trim() !== 'Cover') continue;
                        let el = h2;
                        for (let i = 0; i < 3; i++) el = el.parentElement;
                        if (!el) return;
                        const btns = el.querySelectorAll('button');
                        let idx = 0;
                        for (const btn of btns) {{
                            if (btn.offsetParent !== null) {{
                                if (idx === {thumb['idx']}) {{
                                    btn.setAttribute('data-cover-target', 'true');
                                    return;
                                }}
                                idx++;
                            }}
                        }}
                    }}
                }}""")

                target = page.locator('[data-cover-target="true"]').first
                if await target.is_visible(timeout=3000):
                    # Click to select this thumbnail
                    await target.click()
                    await asyncio.sleep(1)

                    # Hover to reveal delete button
                    await target.hover()
                    await asyncio.sleep(1)

                    # Look for delete button (small button with SVG, no img, no text)
                    delete_btns = await page.evaluate("""() => {
                        const h2s = document.querySelectorAll('h2');
                        for (const h2 of h2s) {
                            if (h2.textContent.trim() !== 'Cover') continue;
                            let el = h2;
                            for (let i = 0; i < 3; i++) el = el.parentElement;
                            if (!el) return [];
                            const btns = el.querySelectorAll('button');
                            const result = [];
                            for (const btn of btns) {
                                if (btn.offsetParent !== null && btn.querySelector('svg') && !btn.querySelector('img')) {
                                    const rect = btn.getBoundingClientRect();
                                    result.push({
                                        text: btn.textContent.trim(),
                                        w: Math.round(rect.width),
                                        h: Math.round(rect.height),
                                        x: Math.round(rect.x),
                                        y: Math.round(rect.y),
                                    });
                                    btn.setAttribute('data-del-btn', 'true');
                                }
                            }
                            return result;
                        }
                        return [];
                    }""")
                    print(f"    Thumb [{thumb['idx']}] — delete candidates: {delete_btns}")

                    # Find the small SVG button (likely a trash/X icon)
                    for db in delete_btns:
                        if db['w'] < 50 and db['text'] == '':
                            # Click it via Playwright
                            del_btn = page.locator('[data-del-btn="true"]').first
                            await del_btn.click(force=True)
                            await asyncio.sleep(2)
                            print(f"    Deleted!")
                            break
                    else:
                        # Try clicking any SVG button
                        if delete_btns:
                            del_btn = page.locator('[data-del-btn="true"]').first
                            await del_btn.click(force=True)
                            await asyncio.sleep(2)
                            print(f"    Clicked first SVG button")

                # Clean up marker
                await page.evaluate("() => { const el = document.querySelector('[data-cover-target]'); if (el) el.removeAttribute('data-cover-target'); }")
                await page.evaluate("() => { document.querySelectorAll('[data-del-btn]').forEach(el => el.removeAttribute('data-del-btn')); }")

            await page.screenshot(path=str(SCREENSHOTS / "cover_replace_02_after_delete.png"))

            # Save after deletion
            print("\n[4] Saving after cover deletion...")
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)
            save = page.locator('button:has-text("Save changes")').first
            if await save.is_visible(timeout=3000):
                await save.click()
                await asyncio.sleep(5)
                print("  Saved!")

            # Reload to clean state
            await page.goto("https://gumroad.com/products/wblqda/edit", wait_until="networkidle")
            await asyncio.sleep(3)

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

            # Check how many thumbnails remain
            thumbs_remaining = await page.evaluate("""() => {
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() !== 'Cover') continue;
                    let el = h2;
                    for (let i = 0; i < 3; i++) el = el.parentElement;
                    if (!el) return -1;
                    return el.querySelectorAll('button img').length;
                }
                return -1;
            }""")
            print(f"\n[5] Thumbnails remaining after reload: {thumbs_remaining}")

            await page.screenshot(path=str(SCREENSHOTS / "cover_replace_03_after_reload.png"))

            # Step 3: Upload new cover
            print("\n[6] Uploading new cover (no price)...")

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
                        if (btn.offsetParent !== null && btn.getBoundingClientRect().width < 60) {
                            btn.click();
                            return;
                        }
                    }
                }
            }""")
            await asyncio.sleep(2)

            # Click "Upload images or videos"
            upload_btn = page.locator('button:has-text("Upload images or videos")').first
            if await upload_btn.is_visible(timeout=5000):
                await upload_btn.click()
                await asyncio.sleep(2)

                # Find cover file input (accepts .mov/.mp4)
                fi_all = await page.locator('input[type="file"]').all()
                uploaded = False
                for fi in fi_all:
                    accept = await fi.evaluate("el => el.accept || ''")
                    if ".mov" in accept or ".mp4" in accept:
                        await fi.set_input_files(COVER_PATH)
                        print("  Cover uploaded via video-accepting file input!")
                        uploaded = True
                        await asyncio.sleep(6)
                        break

                if not uploaded:
                    print(f"  No video-accepting file input found! Inputs: {len(fi_all)}")
                    for i, fi in enumerate(fi_all):
                        accept = await fi.evaluate("el => el.accept || ''")
                        print(f"    [{i}] accept={accept}")
            else:
                print("  'Upload images or videos' not visible")

            await page.screenshot(path=str(SCREENSHOTS / "cover_replace_04_uploaded.png"))

            # Save
            print("\n[7] Saving...")
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)
            save = page.locator('button:has-text("Save changes")').first
            if await save.is_visible(timeout=3000):
                await save.click()
                await asyncio.sleep(5)
                print("  Saved!")

            await page.screenshot(path=str(SCREENSHOTS / "cover_replace_05_final.png"), full_page=True)

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
            print(f"  Preview URL: {prod.get('preview_url', 'NONE')}")
            print(f"  Thumbnail URL: {prod.get('thumbnail_url', 'NONE')}")
            print(f"  Tags: {prod.get('tags', [])}")


if __name__ == "__main__":
    asyncio.run(run())
