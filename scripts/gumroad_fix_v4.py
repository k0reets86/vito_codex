#!/usr/bin/env python3
"""V4: Tags via React Select + Cover at level 3 (SECTION)."""

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
                print("COOKIE EXPIRED"); await browser.close(); return

            print("[2] Adding tags via React Select...")

            # The tag input is a React Select component
            # It has class "css-b62m3t-container" and contains an actual input
            # We need to click the container to focus, then type + Enter

            # First scroll to Tags section
            await page.evaluate("""() => {
                const labels = document.querySelectorAll('label');
                for (const l of labels) {
                    if (l.textContent.trim() === 'Tags') {
                        l.scrollIntoView({behavior: 'instant', block: 'center'});
                        return true;
                    }
                }
                return false;
            }""")
            await asyncio.sleep(1)

            # Find the React Select input inside the container
            # React Select creates a hidden input inside the component
            react_input = await page.evaluate("""() => {
                // Find the react-select container near Tags label
                const labels = document.querySelectorAll('label');
                for (const label of labels) {
                    if (label.textContent.trim() === 'Tags') {
                        // The react-select is likely a sibling of the label
                        let sibling = label.nextElementSibling;
                        while (sibling) {
                            // Look for react-select container
                            const rs = sibling.querySelector('[class*="b62m3t-container"]') || sibling;
                            if (rs) {
                                // Find the actual input inside react-select
                                const input = rs.querySelector('input');
                                if (input) {
                                    input.setAttribute('data-rs-tag-input', 'true');
                                    return {found: true, id: input.id, role: input.getAttribute('role')};
                                }
                                // Try clicking the value container to focus
                                const valueContainer = rs.querySelector('[class*="ValueContainer"]');
                                if (valueContainer) {
                                    valueContainer.click();
                                    // Re-check for input
                                    const inp2 = rs.querySelector('input');
                                    if (inp2) {
                                        inp2.setAttribute('data-rs-tag-input', 'true');
                                        return {found: true, id: inp2.id, method: 'after-click'};
                                    }
                                }
                            }
                            sibling = sibling.nextElementSibling;
                        }
                    }
                }
                return {found: false};
            }""")
            print(f"  React Select input: {react_input}")

            tags_added = False
            if react_input.get('found'):
                rs_input = page.locator('[data-rs-tag-input="true"]').first
                for tag in TAGS:
                    await rs_input.click()
                    await rs_input.fill(tag)
                    await asyncio.sleep(0.5)
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(0.5)
                print(f"  Added {len(TAGS)} tags!")
                tags_added = True
            else:
                # Fallback: click the container div, then type
                print("  Trying fallback: click container + type...")
                container = page.locator('[class*="b62m3t-container"]').first
                try:
                    await container.click()
                    await asyncio.sleep(1)
                    # Now the input should be focused
                    for tag in TAGS:
                        await page.keyboard.type(tag, delay=30)
                        await asyncio.sleep(0.3)
                        await page.keyboard.press("Enter")
                        await asyncio.sleep(0.5)
                    print(f"  Added {len(TAGS)} tags via container click!")
                    tags_added = True
                except Exception as e:
                    print(f"  Fallback failed: {e}")

            await page.screenshot(path=str(SCREENSHOTS / "v4_02_tags.png"))

            # Save
            save = page.locator('button:has-text("Save changes")').first
            if await save.is_visible(timeout=3000):
                await save.click()
                await asyncio.sleep(4)
                print("  Saved!")

            # ==========================================
            # STEP 2: COVER at Level 3 (SECTION)
            # ==========================================
            print("\n[3] Loading Product tab...")
            await page.goto("https://gumroad.com/products/wblqda/edit", wait_until="networkidle")
            await asyncio.sleep(3)

            print("[4] Replacing cover...")

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

            # Get Cover SECTION (level 3 from h2)
            cover_section = await page.evaluate("""() => {
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() !== 'Cover') continue;
                    // Go up 3 levels: h2 → div → header → section
                    let el = h2;
                    for (let i = 0; i < 3; i++) {
                        el = el.parentElement;
                        if (!el) return null;
                    }

                    const btns = el.querySelectorAll('button');
                    const imgs = el.querySelectorAll('img');

                    // Mark buttons for Playwright access
                    const btnInfo = [];
                    for (const btn of btns) {
                        const hasImg = !!btn.querySelector('img');
                        const hasSvg = !!btn.querySelector('svg');
                        const text = btn.textContent.trim().substring(0, 30);
                        btnInfo.push({text, hasImg, hasSvg, visible: btn.offsetParent !== null});

                        // Mark the + button
                        if (text === '+' || (text === '' && hasSvg && !hasImg)) {
                            btn.setAttribute('data-cover-add-btn', 'true');
                        }
                        // Mark the thumbnail button (has img)
                        if (hasImg) {
                            btn.setAttribute('data-cover-thumb-btn', 'true');
                        }
                    }

                    return {
                        tag: el.tagName,
                        btnCount: btns.length,
                        imgCount: imgs.length,
                        buttons: btnInfo,
                    };
                }
                return null;
            }""")
            print(f"  Cover section: {cover_section}")

            # Step 2a: Delete old cover by hovering thumbnail + clicking delete
            deleted = False
            if cover_section and cover_section.get('imgCount', 0) > 0:
                thumb_btn = page.locator('[data-cover-thumb-btn="true"]').first
                try:
                    if await thumb_btn.is_visible(timeout=3000):
                        # Hover to reveal delete button
                        await thumb_btn.hover()
                        await asyncio.sleep(1)
                        await page.screenshot(path=str(SCREENSHOTS / "v4_03_hover.png"))

                        # After hover, look for the delete/X button that appeared
                        # It should be a small button with SVG overlaying the thumbnail
                        del_found = await page.evaluate("""() => {
                            const section = document.querySelector('[data-cover-thumb-btn="true"]')?.closest('section');
                            if (!section) return false;
                            const btns = section.querySelectorAll('button');
                            for (const btn of btns) {
                                // Delete button: small, visible, has SVG, no text or just "x"
                                if (btn.offsetParent !== null && btn.querySelector('svg')
                                    && !btn.querySelector('img')
                                    && (btn.textContent.trim() === '' || btn.textContent.trim() === '×')
                                    && btn.textContent.trim() !== '+') {
                                    const rect = btn.getBoundingClientRect();
                                    if (rect.width < 60) {
                                        btn.click();
                                        return true;
                                    }
                                }
                            }
                            return false;
                        }""")
                        if del_found:
                            print("  Old cover deleted!")
                            deleted = True
                            await asyncio.sleep(2)
                        else:
                            # Try using Playwright to find buttons overlaying the thumb
                            # Look at all visible buttons with SVG in cover section
                            btns_after = await page.evaluate("""() => {
                                const section = document.querySelector('[data-cover-thumb-btn="true"]')?.closest('section');
                                if (!section) return [];
                                return Array.from(section.querySelectorAll('button')).map(b => ({
                                    text: b.textContent.trim(),
                                    visible: b.offsetParent !== null,
                                    hasSvg: !!b.querySelector('svg'),
                                    hasImg: !!b.querySelector('img'),
                                    rect: b.getBoundingClientRect(),
                                    ariaLabel: b.getAttribute('aria-label') || '',
                                }));
                            }""")
                            print(f"  Buttons after hover:")
                            for b in btns_after:
                                print(f"    text='{b['text']}' svg={b['hasSvg']} img={b['hasImg']} vis={b['visible']} w={b['rect']['width']:.0f} aria='{b['ariaLabel']}'")
                except Exception as e:
                    print(f"  Thumbnail hover error: {e}")

            # Step 2b: Upload new cover via + button
            cover_uploaded = False
            add_btn = page.locator('[data-cover-add-btn="true"]').first
            try:
                if await add_btn.is_visible(timeout=3000):
                    try:
                        async with page.expect_file_chooser(timeout=5000) as fc_info:
                            await add_btn.click()
                        chooser = await fc_info.value
                        await chooser.set_files(COVER_PATH)
                        print("  Cover uploaded via + file chooser!")
                        cover_uploaded = True
                        await asyncio.sleep(5)
                    except Exception:
                        # Menu appeared
                        await asyncio.sleep(2)
                        await page.screenshot(path=str(SCREENSHOTS / "v4_04_menu.png"))

                        # Check for Computer files
                        comp = page.locator('button:has-text("Computer files")').first
                        try:
                            if await comp.is_visible(timeout=3000):
                                async with page.expect_file_chooser(timeout=10000) as fc_info:
                                    await comp.click()
                                chooser = await fc_info.value
                                await chooser.set_files(COVER_PATH)
                                print("  Cover uploaded via Computer files!")
                                cover_uploaded = True
                                await asyncio.sleep(5)
                        except Exception as e:
                            print(f"  Computer files failed: {e}")

                        if not cover_uploaded:
                            # Check for new file inputs
                            fi_all = await page.locator('input[type="file"]').all()
                            print(f"  File inputs: {len(fi_all)}")
                            for fi in fi_all:
                                accept = await fi.evaluate("el => el.accept || ''")
                                if ".mov" in accept or ".mp4" in accept or ".wmv" in accept:
                                    await fi.set_input_files(COVER_PATH)
                                    print("  Cover via video file input!")
                                    cover_uploaded = True
                                    await asyncio.sleep(5)
                                    break
                else:
                    print("  + button not visible")
            except Exception as e:
                print(f"  + button error: {e}")

            await page.screenshot(path=str(SCREENSHOTS / "v4_05_after_cover.png"))

            # Save
            if cover_uploaded or deleted:
                await page.evaluate("window.scrollTo(0, 0)")
                await asyncio.sleep(1)
                save = page.locator('button:has-text("Save changes")').first
                if await save.is_visible(timeout=3000):
                    await save.click()
                    await asyncio.sleep(4)
                    print("  Saved!")

            await page.screenshot(path=str(SCREENSHOTS / "v4_06_final.png"), full_page=True)

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
