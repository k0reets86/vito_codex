#!/usr/bin/env python3
"""Add tags on Share tab + replace cover via grandparent DOM traversal."""

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

            # ==========================================
            # STEP 1: TAGS on Share tab
            # ==========================================
            print("\n[2] Adding tags on Share tab...")
            share_tab = page.locator('button:has-text("Share")').first
            await share_tab.click()
            await asyncio.sleep(3)

            # Scroll to Tags section
            await page.evaluate("""() => {
                const els = document.querySelectorAll('*');
                for (const el of els) {
                    if (el.textContent.trim() === 'Tags' && el.offsetParent !== null
                        && el.getBoundingClientRect().height < 40
                        && el.children.length === 0) {
                        el.scrollIntoView({behavior: 'instant', block: 'center'});
                        return true;
                    }
                }
                return false;
            }""")
            await asyncio.sleep(1)

            # Find tag input — use broader search
            tag_input_sel = await page.evaluate("""() => {
                const inputs = document.querySelectorAll('input');
                for (const inp of inputs) {
                    const ph = inp.placeholder || '';
                    if (ph.toLowerCase().includes('tag') || ph.toLowerCase().includes('begin typing')) {
                        inp.setAttribute('data-tag-inp', 'true');
                        return {found: true, ph: ph, visible: inp.offsetParent !== null};
                    }
                }
                return {found: false};
            }""")
            print(f"  Tag input: {tag_input_sel}")

            if tag_input_sel.get('found'):
                tag_inp = page.locator('[data-tag-inp="true"]').first
                for tag in TAGS:
                    await tag_inp.click()
                    await tag_inp.fill(tag)
                    await asyncio.sleep(0.5)
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(0.5)
                print(f"  Added {len(TAGS)} tags!")
            else:
                print("  Tag input still not found")

            await page.screenshot(path=str(SCREENSHOTS / "tc2_02_tags.png"))

            # Save
            save = page.locator('button:has-text("Save changes")').first
            if await save.is_visible(timeout=3000):
                await save.click()
                await asyncio.sleep(4)
                print("  Saved!")

            # ==========================================
            # STEP 2: COVER — navigate grandparent
            # ==========================================
            print("\n[3] Replacing cover...")

            # Go to Product tab
            product_tab = page.locator('button:has-text("Product")').first
            await product_tab.click()
            await asyncio.sleep(3)

            # Scroll to Cover h2
            await page.evaluate("""() => {
                const els = document.querySelectorAll('h2');
                for (const el of els) {
                    if (el.textContent.trim() === 'Cover') {
                        el.scrollIntoView({behavior: 'instant', block: 'start'});
                        return true;
                    }
                }
                return false;
            }""")
            await asyncio.sleep(1)

            # Get GRANDPARENT HTML to find the actual cover elements
            cover_gp_html = await page.evaluate("""() => {
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() === 'Cover') {
                        // Go up multiple levels to find the real container
                        let container = h2.parentElement;
                        if (container) container = container.parentElement;
                        if (container) {
                            return {
                                html: container.innerHTML.substring(0, 5000),
                                children: container.children.length,
                                tag: container.tagName,
                            };
                        }
                    }
                }
                return null;
            }""")
            print(f"  Grandparent tag: {cover_gp_html.get('tag') if cover_gp_html else 'null'}")
            print(f"  Grandparent children: {cover_gp_html.get('children') if cover_gp_html else 0}")
            if cover_gp_html:
                print(f"  HTML preview: {cover_gp_html['html'][:3000]}")

            # Find all buttons and images inside the grandparent
            cover_gp_elements = await page.evaluate("""() => {
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() === 'Cover') {
                        let container = h2.parentElement;
                        if (container) container = container.parentElement;
                        if (container) {
                            const btns = container.querySelectorAll('button');
                            const imgs = container.querySelectorAll('img');
                            const inputs = container.querySelectorAll('input[type="file"]');
                            return {
                                buttons: Array.from(btns).map(b => ({
                                    text: b.textContent.trim().substring(0, 30),
                                    ariaLabel: b.getAttribute('aria-label') || '',
                                    hasSvg: !!b.querySelector('svg'),
                                    visible: b.offsetParent !== null,
                                })),
                                images: Array.from(imgs).map(i => ({
                                    src: i.src.substring(0, 80),
                                    w: i.naturalWidth,
                                    h: i.naturalHeight,
                                })),
                                fileInputs: Array.from(inputs).map(fi => ({
                                    accept: fi.accept,
                                    multiple: fi.multiple,
                                })),
                            };
                        }
                    }
                }
                return null;
            }""")
            if cover_gp_elements:
                print(f"\n  Buttons in grandparent ({len(cover_gp_elements['buttons'])}):")
                for b in cover_gp_elements['buttons']:
                    print(f"    text='{b['text']}' aria='{b['ariaLabel']}' svg={b['hasSvg']} visible={b['visible']}")
                print(f"  Images ({len(cover_gp_elements['images'])}):")
                for img in cover_gp_elements['images']:
                    print(f"    {img['w']}x{img['h']} src={img['src']}")
                print(f"  File inputs ({len(cover_gp_elements['fileInputs'])}):")
                for fi in cover_gp_elements['fileInputs']:
                    print(f"    accept={fi['accept']} multiple={fi['multiple']}")

            # Try to find the + button and click it
            plus_clicked = False
            try:
                # Mark the + button
                await page.evaluate("""() => {
                    const h2s = document.querySelectorAll('h2');
                    for (const h2 of h2s) {
                        if (h2.textContent.trim() === 'Cover') {
                            let container = h2.parentElement;
                            if (container) container = container.parentElement;
                            if (container) {
                                const btns = container.querySelectorAll('button');
                                for (const btn of btns) {
                                    if (btn.textContent.trim() === '+' || (btn.querySelector('svg') && btn.textContent.trim() === '')) {
                                        btn.setAttribute('data-cover-plus-btn', 'true');
                                        return true;
                                    }
                                }
                            }
                        }
                    }
                    return false;
                }""")

                plus_btn = page.locator('[data-cover-plus-btn="true"]').first
                if await plus_btn.is_visible(timeout=3000):
                    # Try file chooser first
                    try:
                        async with page.expect_file_chooser(timeout=5000) as fc_info:
                            await plus_btn.click()
                        chooser = await fc_info.value
                        await chooser.set_files(COVER_PATH)
                        print("  Cover uploaded via + button file chooser!")
                        plus_clicked = True
                        await asyncio.sleep(5)
                    except Exception:
                        # Menu appeared
                        await asyncio.sleep(2)
                        await page.screenshot(path=str(SCREENSHOTS / "tc2_03_plus_menu.png"))

                        # Try Computer files
                        comp = page.locator('button:has-text("Computer files")').first
                        try:
                            if await comp.is_visible(timeout=3000):
                                async with page.expect_file_chooser(timeout=10000) as fc_info:
                                    await comp.click()
                                chooser = await fc_info.value
                                await chooser.set_files(COVER_PATH)
                                print("  Cover uploaded via Computer files!")
                                plus_clicked = True
                                await asyncio.sleep(5)
                        except Exception as e2:
                            print(f"  Computer files failed: {e2}")

                        if not plus_clicked:
                            # Check if new file inputs appeared
                            fi_all = await page.locator('input[type="file"]').all()
                            print(f"  File inputs after + click: {len(fi_all)}")
                            for fi in fi_all:
                                accept = await fi.evaluate("el => el.accept || ''")
                                print(f"    accept={accept}")
                                if ".mov" in accept or ".mp4" in accept:
                                    await fi.set_input_files(COVER_PATH)
                                    print("  Cover uploaded via new file input!")
                                    plus_clicked = True
                                    await asyncio.sleep(5)
                                    break
            except Exception as e:
                print(f"  + button error: {e}")

            await page.screenshot(path=str(SCREENSHOTS / "tc2_04_cover.png"))

            # Save
            if plus_clicked:
                await page.evaluate("window.scrollTo(0, 0)")
                await asyncio.sleep(1)
                save = page.locator('button:has-text("Save changes")').first
                if await save.is_visible(timeout=3000):
                    await save.click()
                    await asyncio.sleep(4)
                    print("  Saved!")

            await page.screenshot(path=str(SCREENSHOTS / "tc2_05_final.png"), full_page=True)

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
    print("=" * 60)
    asyncio.run(run())
