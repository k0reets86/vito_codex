#!/usr/bin/env python3
"""Add tags + replace cover. Fixed Share tab selector + cover DOM."""

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

TAGS = ["ai", "side hustle", "passive income", "chatgpt", "make money online", "ebook", "artificial intelligence"]


async def run():
    from playwright.async_api import async_playwright

    if not SESSION_COOKIE:
        print("ERROR: No cookie"); return

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
            print("[1] Loading...")
            await page.goto(EDIT_URL, wait_until="networkidle")
            await asyncio.sleep(3)
            if "login" in page.url.lower():
                print("ERROR: Cookie expired!"); await browser.close(); return
            print(f"  OK: {page.url}")

            # First, dump the tab navigation to find correct selectors
            tabs = await page.evaluate("""() => {
                const result = [];
                // Look for tab-like elements near the top
                const candidates = document.querySelectorAll('a, button, [role="tab"]');
                for (const el of candidates) {
                    const text = el.textContent.trim();
                    if (['Product', 'Content', 'Receipt', 'Share'].includes(text)) {
                        result.push({
                            tag: el.tagName,
                            text,
                            href: el.href || '',
                            role: el.getAttribute('role') || '',
                            classes: el.className.toString().substring(0, 60),
                            visible: el.offsetParent !== null,
                        });
                    }
                }
                return result;
            }""")
            print(f"  Tab elements: {tabs}")

            # ==========================================
            # STEP 1: TAGS
            # ==========================================
            print("\n[2] Navigating to Share tab...")

            # Click Share tab — try multiple approaches
            share_clicked = False
            for sel in [
                'a:has-text("Share")',
                '[role="tab"]:has-text("Share")',
                'text=Share',
                'nav a:has-text("Share")',
            ]:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=3000):
                        await el.click()
                        share_clicked = True
                        print(f"  Clicked Share via: {sel}")
                        await asyncio.sleep(3)
                        break
                except Exception:
                    continue

            if not share_clicked:
                # Click via JS
                share_clicked = await page.evaluate("""() => {
                    const els = document.querySelectorAll('a, button, [role="tab"]');
                    for (const el of els) {
                        if (el.textContent.trim() === 'Share' && el.offsetParent !== null) {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                print(f"  Share via JS: {share_clicked}")
                await asyncio.sleep(3)

            await page.screenshot(path=str(SCREENSHOTS / "tc3_02_share.png"))

            # Add tags
            print("  Adding tags...")

            # Scroll to Tags
            await page.evaluate("""() => {
                const els = document.querySelectorAll('*');
                for (const el of els) {
                    if (el.children.length === 0 && el.textContent.trim() === 'Tags'
                        && el.offsetParent !== null && el.getBoundingClientRect().height < 40) {
                        el.scrollIntoView({behavior: 'instant', block: 'center'});
                        return true;
                    }
                }
                return false;
            }""")
            await asyncio.sleep(1)

            # Find tag input
            tag_found = await page.evaluate("""() => {
                const inputs = document.querySelectorAll('input');
                for (const inp of inputs) {
                    const ph = (inp.placeholder || '').toLowerCase();
                    if ((ph.includes('tag') || ph.includes('begin typing')) && inp.offsetParent !== null) {
                        inp.setAttribute('data-tag-input-v3', 'true');
                        return {found: true, ph: inp.placeholder};
                    }
                }
                return {found: false};
            }""")
            print(f"  Tag input: {tag_found}")

            tags_added = False
            if tag_found.get('found'):
                tag_inp = page.locator('[data-tag-input-v3="true"]').first
                for tag in TAGS:
                    await tag_inp.click()
                    await tag_inp.fill(tag)
                    await asyncio.sleep(0.5)
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(0.5)
                print(f"  Added {len(TAGS)} tags!")
                tags_added = True

            await page.screenshot(path=str(SCREENSHOTS / "tc3_03_tags.png"))

            # Save
            save = page.locator('button:has-text("Save changes")').first
            if await save.is_visible(timeout=3000):
                await save.click()
                await asyncio.sleep(4)
                print("  Saved!")

            # ==========================================
            # STEP 2: COVER
            # ==========================================
            print("\n[3] Replacing cover...")

            # Navigate to Product tab
            for sel in ['a:has-text("Product")', '[role="tab"]:has-text("Product")', 'text=Product']:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=3000):
                        await el.click()
                        await asyncio.sleep(3)
                        print(f"  Product tab via: {sel}")
                        break
                except Exception:
                    continue

            # Scroll to Cover
            await page.evaluate("""() => {
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() === 'Cover') {
                        h2.scrollIntoView({behavior: 'instant', block: 'start'});
                        return true;
                    }
                }
                return false;
            }""")
            await asyncio.sleep(1)

            # Get cover section using deeper DOM traversal
            # Go up 3 levels from Cover h2 to find container with buttons/images
            cover_info = await page.evaluate("""() => {
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() !== 'Cover') continue;

                    // Traverse up multiple levels to find the real container
                    let container = h2;
                    for (let level = 0; level < 5; level++) {
                        container = container.parentElement;
                        if (!container) break;

                        const btns = container.querySelectorAll('button');
                        const imgs = container.querySelectorAll('img');
                        const fis = container.querySelectorAll('input[type="file"]');

                        // We found the right level when we have buttons AND images
                        if (btns.length >= 2 || imgs.length > 0) {
                            return {
                                level,
                                tag: container.tagName,
                                buttons: Array.from(btns).map(b => ({
                                    text: b.textContent.trim().substring(0, 30),
                                    ariaLabel: b.getAttribute('aria-label') || '',
                                    visible: b.offsetParent !== null,
                                    hasSvg: !!b.querySelector('svg'),
                                    hasImg: !!b.querySelector('img'),
                                    rect: b.getBoundingClientRect(),
                                })),
                                images: Array.from(imgs).map(i => ({
                                    src: i.src.substring(0, 100),
                                    w: i.naturalWidth, h: i.naturalHeight,
                                    alt: i.alt || '',
                                })),
                                fileInputs: Array.from(fis).map(fi => ({
                                    accept: fi.accept, multiple: fi.multiple,
                                })),
                            };
                        }
                    }
                    return {level: -1, note: 'No container found with buttons/images'};
                }
                return null;
            }""")

            if cover_info:
                print(f"  Cover container found at level {cover_info.get('level')}")
                print(f"  Buttons ({len(cover_info.get('buttons', []))}):")
                for b in cover_info.get('buttons', []):
                    print(f"    text='{b['text']}' aria='{b['ariaLabel']}' svg={b['hasSvg']} img={b['hasImg']} visible={b['visible']}")
                print(f"  Images ({len(cover_info.get('images', []))}):")
                for img in cover_info.get('images', []):
                    print(f"    {img['w']}x{img['h']} alt='{img['alt']}' src={img['src'][:60]}")
                print(f"  File inputs ({len(cover_info.get('fileInputs', []))}):")
                for fi in cover_info.get('fileInputs', []):
                    print(f"    accept={fi['accept']} multiple={fi['multiple']}")
            else:
                print("  Cover info: None")

            # Now try to:
            # 1. Delete old cover (hover thumbnail → click delete)
            # 2. Upload new cover via + button

            # Step 1: Try to delete old cover
            # Find button with img inside (the thumbnail) and hover it
            deleted = False
            if cover_info and cover_info.get('buttons'):
                # Find thumb button (has img) and delete button (has svg, no img)
                for b in cover_info['buttons']:
                    if b.get('hasImg') and b.get('visible'):
                        # This is the thumbnail button — hover it
                        await page.evaluate("""() => {
                            const h2s = document.querySelectorAll('h2');
                            for (const h2 of h2s) {
                                if (h2.textContent.trim() !== 'Cover') continue;
                                let container = h2;
                                for (let i = 0; i < 5; i++) {
                                    container = container.parentElement;
                                    if (!container) break;
                                    const btns = container.querySelectorAll('button');
                                    for (const btn of btns) {
                                        if (btn.querySelector('img')) {
                                            btn.setAttribute('data-cover-thumb-v3', 'true');
                                            return;
                                        }
                                    }
                                }
                            }
                        }""")

                        thumb = page.locator('[data-cover-thumb-v3="true"]').first
                        if await thumb.is_visible(timeout=3000):
                            await thumb.hover()
                            await asyncio.sleep(1)
                            await page.screenshot(path=str(SCREENSHOTS / "tc3_04_hover.png"))

                            # Look for delete button that appeared after hover
                            del_result = await page.evaluate("""() => {
                                const h2s = document.querySelectorAll('h2');
                                for (const h2 of h2s) {
                                    if (h2.textContent.trim() !== 'Cover') continue;
                                    let container = h2;
                                    for (let i = 0; i < 5; i++) {
                                        container = container.parentElement;
                                        if (!container) break;
                                        const btns = container.querySelectorAll('button');
                                        for (const btn of btns) {
                                            // Delete button: has SVG, no text, not the + button
                                            if (btn.querySelector('svg') && !btn.querySelector('img')
                                                && btn.textContent.trim() !== '+'
                                                && btn.offsetParent !== null) {
                                                const rect = btn.getBoundingClientRect();
                                                // Should be small and near the thumbnail
                                                if (rect.width < 50 && rect.height < 50) {
                                                    btn.click();
                                                    return {deleted: true, w: rect.width, h: rect.height};
                                                }
                                            }
                                        }
                                    }
                                }
                                return {deleted: false};
                            }""")
                            print(f"  Delete result: {del_result}")
                            if del_result.get('deleted'):
                                deleted = True
                                await asyncio.sleep(2)
                        break

            if not deleted:
                print("  Could not delete old cover")

            # Step 2: Upload new cover
            # Mark the + button
            plus_marked = await page.evaluate("""() => {
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() !== 'Cover') continue;
                    let container = h2;
                    for (let i = 0; i < 5; i++) {
                        container = container.parentElement;
                        if (!container) break;
                        const btns = container.querySelectorAll('button');
                        for (const btn of btns) {
                            if (btn.textContent.trim() === '+' && btn.offsetParent !== null) {
                                btn.setAttribute('data-cover-plus-v3', 'true');
                                return true;
                            }
                        }
                    }
                }
                return false;
            }""")

            cover_uploaded = False
            if plus_marked:
                plus_btn = page.locator('[data-cover-plus-v3="true"]').first
                try:
                    async with page.expect_file_chooser(timeout=5000) as fc_info:
                        await plus_btn.click()
                    chooser = await fc_info.value
                    await chooser.set_files(COVER_PATH)
                    print("  Cover uploaded via + file chooser!")
                    cover_uploaded = True
                    await asyncio.sleep(5)
                except Exception:
                    await asyncio.sleep(2)
                    # Menu appeared?
                    await page.screenshot(path=str(SCREENSHOTS / "tc3_05_plus_menu.png"))

                    # Try Computer files
                    for sel in ['button:has-text("Computer files")', '[role="menuitem"]:has-text("Computer")']:
                        try:
                            comp = page.locator(sel).first
                            if await comp.is_visible(timeout=3000):
                                async with page.expect_file_chooser(timeout=10000) as fc_info:
                                    await comp.click()
                                chooser = await fc_info.value
                                await chooser.set_files(COVER_PATH)
                                print("  Cover uploaded via Computer files!")
                                cover_uploaded = True
                                await asyncio.sleep(5)
                                break
                        except Exception:
                            continue

                    if not cover_uploaded:
                        # Try new file inputs
                        fi_all = await page.locator('input[type="file"]').all()
                        for fi in fi_all:
                            accept = await fi.evaluate("el => el.accept || ''")
                            if ".mov" in accept or ".mp4" in accept or ".wmv" in accept:
                                await fi.set_input_files(COVER_PATH)
                                print("  Cover via video file input!")
                                cover_uploaded = True
                                await asyncio.sleep(5)
                                break

            await page.screenshot(path=str(SCREENSHOTS / "tc3_06_after_cover.png"))

            # Save
            if cover_uploaded or deleted:
                await page.evaluate("window.scrollTo(0, 0)")
                await asyncio.sleep(1)
                save = page.locator('button:has-text("Save changes")').first
                if await save.is_visible(timeout=3000):
                    await save.click()
                    await asyncio.sleep(4)
                    print("  Saved!")

            await page.screenshot(path=str(SCREENSHOTS / "tc3_07_final.png"), full_page=True)

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
