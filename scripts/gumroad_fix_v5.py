#!/usr/bin/env python3
"""V5: Tags via React Select focus + Cover via 'Upload images or videos' button."""

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

            # React Select: Click the container to focus, then type
            # The placeholder "Begin typing to add a tag..." is shown in a div inside the component
            # When clicked, an <input> appears inside that gets focus

            # Click on the React Select container area
            placeholder_div = page.locator('text=Begin typing to add a tag').first
            try:
                await placeholder_div.click()
                await asyncio.sleep(1)

                # After clicking, an input should be focused inside the component
                # Dump active element
                active = await page.evaluate("""() => {
                    const el = document.activeElement;
                    return {
                        tag: el.tagName,
                        type: el.type || '',
                        id: el.id || '',
                        ph: el.placeholder || '',
                        role: el.getAttribute('role') || '',
                        ariaLabel: el.getAttribute('aria-label') || '',
                    };
                }""")
                print(f"  Active element after click: {active}")

                if active['tag'] == 'INPUT':
                    # Great, input is focused — type tags
                    for tag in TAGS:
                        await page.keyboard.type(tag, delay=30)
                        await asyncio.sleep(0.5)

                        # Check if dropdown appeared, then press Enter
                        await page.screenshot(path=str(SCREENSHOTS / f"v5_tag_{tag.replace(' ', '_')}.png"))
                        await page.keyboard.press("Enter")
                        await asyncio.sleep(0.5)

                    print(f"  Typed {len(TAGS)} tags!")
                else:
                    # Try to find and click the hidden input
                    print(f"  Active element is {active['tag']}, looking for input...")
                    # The react-select input might be very small/hidden
                    rs_input = await page.evaluate("""() => {
                        const containers = document.querySelectorAll('[class*="b62m3t"]');
                        for (const c of containers) {
                            const inp = c.querySelector('input');
                            if (inp) {
                                inp.focus();
                                inp.setAttribute('data-rs-inp', 'true');
                                return {found: true, id: inp.id};
                            }
                        }
                        return {found: false};
                    }""")
                    print(f"  RS input: {rs_input}")
                    if rs_input.get('found'):
                        inp = page.locator('[data-rs-inp="true"]').first
                        await inp.click(force=True)
                        await asyncio.sleep(0.5)
                        for tag in TAGS:
                            await page.keyboard.type(tag, delay=30)
                            await asyncio.sleep(0.3)
                            await page.keyboard.press("Enter")
                            await asyncio.sleep(0.5)
                        print(f"  Typed {len(TAGS)} tags via force-focused input!")

            except Exception as e:
                print(f"  Tag input error: {e}")

            await page.screenshot(path=str(SCREENSHOTS / "v5_02_tags.png"))

            # Save
            save = page.locator('button:has-text("Save changes")').first
            if await save.is_visible(timeout=3000):
                await save.click()
                await asyncio.sleep(4)
                print("  Saved!")
            await page.screenshot(path=str(SCREENSHOTS / "v5_02b_tags_saved.png"))

            # ==========================================
            # STEP 2: COVER
            # ==========================================
            print("\n[3] Loading Product tab...")
            await page.goto("https://gumroad.com/products/wblqda/edit", wait_until="networkidle")
            await asyncio.sleep(3)

            print("[4] Cover...")

            # Scroll to cover
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
            await page.screenshot(path=str(SCREENSHOTS / "v5_03_cover.png"))

            # Cover section is at level 3 (SECTION)
            # But the "+" button had empty text and no SVG/img
            # Let me look more carefully at what buttons exist

            cover_btns = await page.evaluate("""() => {
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() !== 'Cover') continue;
                    let el = h2;
                    for (let i = 0; i < 3; i++) el = el.parentElement;
                    if (!el) return null;

                    const btns = el.querySelectorAll('button');
                    return Array.from(btns).map((b, i) => ({
                        i,
                        text: b.textContent.trim(),
                        outerHTML: b.outerHTML.substring(0, 300),
                        visible: b.offsetParent !== null,
                        rect: b.getBoundingClientRect(),
                    }));
                }
                return null;
            }""")
            if cover_btns:
                print(f"  Cover buttons ({len(cover_btns)}):")
                for b in cover_btns:
                    print(f"    [{b['i']}] text='{b['text'][:30]}' vis={b['visible']} w={b['rect']['width']:.0f} h={b['rect']['height']:.0f}")
                    print(f"       HTML: {b['outerHTML'][:200]}")

            # The cover section should have:
            # - A small thumbnail (could be a div with bg or img)
            # - A "+" or add button
            # - The large preview image
            # - "Upload images or videos" button (may be hidden)

            # Try to find any clickable element that triggers file upload
            # Let's try: click the big preview image area to replace
            cover_uploaded = False

            # Approach: use "Upload images or videos" button — it exists but was hidden
            # Maybe we need to trigger it by removing display:none or scrolling better
            upload_btn = page.locator('button:has-text("Upload images or videos")').first
            try:
                # Force-click it even if not visible
                await upload_btn.click(force=True)
                await asyncio.sleep(2)
                await page.screenshot(path=str(SCREENSHOTS / "v5_04_upload_menu.png"))

                # Should have opened a menu
                comp = page.locator('button:has-text("Computer files")').first
                if await comp.is_visible(timeout=3000):
                    async with page.expect_file_chooser(timeout=10000) as fc_info:
                        await comp.click()
                    chooser = await fc_info.value
                    await chooser.set_files(COVER_PATH)
                    print("  Cover uploaded via Upload→Computer files!")
                    cover_uploaded = True
                    await asyncio.sleep(5)
                else:
                    # Check for file inputs
                    fi_all = await page.locator('input[type="file"]').all()
                    print(f"  File inputs after forced click: {len(fi_all)}")
                    for fi in fi_all:
                        accept = await fi.evaluate("el => el.accept || ''")
                        print(f"    accept={accept}")

            except Exception as e:
                print(f"  Upload button error: {e}")

            if not cover_uploaded:
                # Try the first button in cover section (the empty one)
                try:
                    first_btn = await page.evaluate("""() => {
                        const h2s = document.querySelectorAll('h2');
                        for (const h2 of h2s) {
                            if (h2.textContent.trim() !== 'Cover') continue;
                            let el = h2;
                            for (let i = 0; i < 3; i++) el = el.parentElement;
                            if (!el) return false;
                            const btns = el.querySelectorAll('button');
                            for (const btn of btns) {
                                if (btn.offsetParent !== null) {
                                    btn.setAttribute('data-first-cover-btn', 'true');
                                    return true;
                                }
                            }
                            return false;
                        }
                        return false;
                    }""")

                    if first_btn:
                        btn = page.locator('[data-first-cover-btn="true"]').first
                        try:
                            async with page.expect_file_chooser(timeout=5000) as fc_info:
                                await btn.click()
                            chooser = await fc_info.value
                            await chooser.set_files(COVER_PATH)
                            print("  Cover uploaded via first cover button!")
                            cover_uploaded = True
                            await asyncio.sleep(5)
                        except Exception:
                            print("  First button didn't trigger file chooser")
                            await asyncio.sleep(2)
                            await page.screenshot(path=str(SCREENSHOTS / "v5_05_after_first_btn.png"))

                            # Maybe it opened a menu
                            comp = page.locator('button:has-text("Computer files")').first
                            try:
                                if await comp.is_visible(timeout=3000):
                                    async with page.expect_file_chooser(timeout=10000) as fc_info:
                                        await comp.click()
                                    chooser = await fc_info.value
                                    await chooser.set_files(COVER_PATH)
                                    print("  Cover uploaded via first btn → Computer files!")
                                    cover_uploaded = True
                                    await asyncio.sleep(5)
                            except Exception as e:
                                print(f"  Menu Computer files failed: {e}")
                except Exception as e:
                    print(f"  First button error: {e}")

            await page.screenshot(path=str(SCREENSHOTS / "v5_06_cover_done.png"))

            # Save
            if cover_uploaded:
                await page.evaluate("window.scrollTo(0, 0)")
                await asyncio.sleep(1)
                save = page.locator('button:has-text("Save changes")').first
                if await save.is_visible(timeout=3000):
                    await save.click()
                    await asyncio.sleep(4)
                    print("  Saved!")

            await page.screenshot(path=str(SCREENSHOTS / "v5_07_final.png"), full_page=True)

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
