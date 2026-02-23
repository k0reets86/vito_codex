#!/usr/bin/env python3
"""Fix cover (delete old $17 + upload new), set category + tags via JS clicks."""

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

            # ==========================================
            # STEP 1: COVER — delete old + upload new
            # ==========================================
            print("\n[2] Replacing cover...")

            # Scroll to Cover section
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

            # Dump the Cover section DOM to understand structure
            cover_html = await page.evaluate("""() => {
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() === 'Cover') {
                        // Get the section container (go up to find a reasonable parent)
                        let section = h2.parentElement;
                        // Return the first 5000 chars
                        return section ? section.innerHTML.substring(0, 5000) : 'no parent';
                    }
                }
                return 'not found';
            }""")
            print(f"  Cover section HTML (first 2000 chars):")
            print(f"  {cover_html[:2000]}")

            await page.screenshot(path=str(SCREENSHOTS / "ct_01_cover_section.png"))

            # Try to find cover thumbnail and hover it to get delete button
            # The thumbnail is likely an <img> or <div> with background-image
            # Let's look at the actual DOM elements in the cover area
            cover_elements = await page.evaluate("""() => {
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() === 'Cover') {
                        const parent = h2.parentElement;
                        if (!parent) continue;
                        const allEls = parent.querySelectorAll('*');
                        const result = [];
                        for (const el of allEls) {
                            if (el.tagName === 'IMG' || el.tagName === 'BUTTON' || el.tagName === 'INPUT' ||
                                el.tagName === 'SVG' || el.tagName === 'A' ||
                                (el.style && el.style.backgroundImage)) {
                                result.push({
                                    tag: el.tagName,
                                    classes: el.className ? el.className.toString().substring(0, 80) : '',
                                    src: el.src || '',
                                    ariaLabel: el.getAttribute('aria-label') || '',
                                    type: el.type || '',
                                    text: el.textContent.trim().substring(0, 30),
                                    role: el.getAttribute('role') || '',
                                    title: el.title || '',
                                });
                            }
                        }
                        return result;
                    }
                }
                return [];
            }""")
            print(f"\n  Cover section elements ({len(cover_elements)}):")
            for el in cover_elements:
                print(f"    {el['tag']} cls={el['classes'][:40]} aria={el['ariaLabel']} text={el['text']} src={el['src'][:60]}")

            # Strategy: hover over thumbnail, look for delete button, then click it
            # First, let's find any button with trash/delete/remove icon in cover section
            deleted = False

            # Try clicking the thumbnail image first
            thumb_in_cover = await page.evaluate("""() => {
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() === 'Cover') {
                        const parent = h2.parentElement;
                        // Find first button-like element that could be the thumbnail
                        const btns = parent.querySelectorAll('button');
                        for (const btn of btns) {
                            const img = btn.querySelector('img');
                            const svg = btn.querySelector('svg');
                            if (img) {
                                btn.setAttribute('data-cover-thumb', 'true');
                                return {found: true, type: 'img', src: img.src.substring(0, 80)};
                            }
                        }
                        // Find standalone images
                        const imgs = parent.querySelectorAll('img');
                        for (const img of imgs) {
                            img.setAttribute('data-cover-img', 'true');
                            return {found: true, type: 'standalone-img', src: img.src.substring(0, 80)};
                        }
                        // Check divs with background images
                        const divs = parent.querySelectorAll('div');
                        for (const div of divs) {
                            const bg = getComputedStyle(div).backgroundImage;
                            if (bg && bg !== 'none') {
                                div.setAttribute('data-cover-div', 'true');
                                return {found: true, type: 'bg-div', bg: bg.substring(0, 80)};
                            }
                        }
                        return {found: false};
                    }
                }
                return {found: false};
            }""")
            print(f"\n  Thumbnail search: {thumb_in_cover}")

            if thumb_in_cover and thumb_in_cover.get('found'):
                if thumb_in_cover['type'] == 'img':
                    thumb = page.locator('[data-cover-thumb="true"]').first
                elif thumb_in_cover['type'] == 'standalone-img':
                    thumb = page.locator('[data-cover-img="true"]').first
                else:
                    thumb = page.locator('[data-cover-div="true"]').first

                # Hover over the thumbnail to reveal delete button
                await thumb.hover()
                await asyncio.sleep(1)
                await page.screenshot(path=str(SCREENSHOTS / "ct_02_cover_hover.png"))

                # Now look for delete/remove/trash button that appeared
                del_btns = await page.evaluate("""() => {
                    const h2s = document.querySelectorAll('h2');
                    for (const h2 of h2s) {
                        if (h2.textContent.trim() === 'Cover') {
                            const parent = h2.parentElement;
                            const btns = parent.querySelectorAll('button');
                            const result = [];
                            for (const btn of btns) {
                                const visible = btn.offsetParent !== null;
                                const hasSvg = btn.querySelector('svg') ? true : false;
                                result.push({
                                    text: btn.textContent.trim().substring(0, 30),
                                    ariaLabel: btn.getAttribute('aria-label') || '',
                                    visible,
                                    hasSvg,
                                    classes: btn.className.toString().substring(0, 60),
                                });
                            }
                            return result;
                        }
                    }
                    return [];
                }""")
                print(f"  Buttons after hover ({len(del_btns)}):")
                for b in del_btns:
                    print(f"    visible={b['visible']} svg={b['hasSvg']} text='{b['text']}' aria='{b['ariaLabel']}'")

                # Click any button with SVG (likely trash icon) that's visible
                for b_info in del_btns:
                    if b_info['visible'] and b_info['hasSvg'] and b_info['text'] != '+':
                        # Try to click it via JS to bypass overlays
                        deleted = await page.evaluate("""(btnInfo) => {
                            const h2s = document.querySelectorAll('h2');
                            for (const h2 of h2s) {
                                if (h2.textContent.trim() === 'Cover') {
                                    const parent = h2.parentElement;
                                    const btns = parent.querySelectorAll('button');
                                    for (const btn of btns) {
                                        if (btn.offsetParent !== null && btn.querySelector('svg')
                                            && btn.textContent.trim() !== '+') {
                                            btn.click();
                                            return true;
                                        }
                                    }
                                }
                            }
                            return false;
                        }""", del_btns[0])
                        if deleted:
                            print("  Deleted old cover!")
                            await asyncio.sleep(2)
                        break

            if not deleted:
                print("  Could not delete old cover. Will add new one alongside it.")

            # Upload new cover via "+" button
            print("  Uploading new cover via + button...")

            # Find "+" button in Cover section
            plus_uploaded = False
            plus_btn_found = await page.evaluate("""() => {
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() === 'Cover') {
                        const parent = h2.parentElement;
                        const btns = parent.querySelectorAll('button');
                        for (const btn of btns) {
                            if (btn.textContent.trim() === '+' || btn.textContent.trim() === '') {
                                btn.setAttribute('data-cover-plus', 'true');
                                return true;
                            }
                        }
                    }
                }
                return false;
            }""")

            if plus_btn_found:
                plus_btn = page.locator('[data-cover-plus="true"]').first
                try:
                    async with page.expect_file_chooser(timeout=10000) as fc_info:
                        await plus_btn.click()
                    chooser = await fc_info.value
                    await chooser.set_files(COVER_PATH)
                    print("  New cover uploaded via + button (file chooser)!")
                    plus_uploaded = True
                    await asyncio.sleep(5)
                except Exception as e:
                    print(f"  + button file chooser failed: {e}")
                    # Menu might have appeared
                    await asyncio.sleep(2)
                    await page.screenshot(path=str(SCREENSHOTS / "ct_03_plus_menu.png"))

                    # Try "Computer files"
                    comp = page.locator('button:has-text("Computer files"), [role="menuitem"]:has-text("Computer files")').first
                    try:
                        if await comp.is_visible(timeout=3000):
                            async with page.expect_file_chooser(timeout=10000) as fc_info:
                                await comp.click()
                            chooser = await fc_info.value
                            await chooser.set_files(COVER_PATH)
                            print("  Cover uploaded via Computer files menu!")
                            plus_uploaded = True
                            await asyncio.sleep(5)
                    except Exception as e2:
                        print(f"  Computer files failed too: {e2}")

            if not plus_uploaded:
                # Try to find hidden file inputs that appeared after clicking +
                fi_all = await page.locator('input[type="file"]').all()
                print(f"  File inputs now: {len(fi_all)}")
                for i, fi in enumerate(fi_all):
                    accept = await fi.evaluate("el => el.accept || ''")
                    print(f"    [{i}] accept={accept}")
                    if ".mov" in accept or ".mp4" in accept:
                        await fi.set_input_files(COVER_PATH)
                        print(f"  Cover uploaded via file input [{i}]!")
                        plus_uploaded = True
                        await asyncio.sleep(5)
                        break

            await page.screenshot(path=str(SCREENSHOTS / "ct_04_after_cover.png"))

            # Save
            print("\n  Saving...")
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)
            save = page.locator('button:has-text("Save changes")').first
            if await save.is_visible(timeout=3000):
                await save.click()
                await asyncio.sleep(4)
                print("  Saved!")

            # ==========================================
            # STEP 2: SHARE TAB — category + tags
            # ==========================================
            print("\n[3] Share tab — category + tags...")

            share_tab = page.locator('button:has-text("Share")').first
            try:
                await share_tab.click()
                await asyncio.sleep(3)
            except Exception:
                share_tab = page.locator('a:has-text("Share")').first
                await share_tab.click()
                await asyncio.sleep(3)

            # Scroll to Category section
            await page.evaluate("""() => {
                const labels = document.querySelectorAll('*');
                for (const el of labels) {
                    if (el.textContent.trim() === 'Category' && el.offsetParent !== null
                        && el.getBoundingClientRect().height < 40) {
                        el.scrollIntoView({behavior: 'instant', block: 'center'});
                        return true;
                    }
                }
                return false;
            }""")
            await asyncio.sleep(1)
            await page.screenshot(path=str(SCREENSHOTS / "ct_05_share_cat.png"))

            # Category — it's a combobox/dropdown showing "Other"
            # Clear it and type "Self Improvement"
            # First try to find and click the X to clear current selection
            cat_set = False
            try:
                # Find the combobox near Category label
                # The dropdown uses a custom combobox, not native select
                # Let's click the X button first to clear, then type
                x_result = await page.evaluate("""() => {
                    const labels = document.querySelectorAll('*');
                    for (const el of labels) {
                        if (el.textContent.trim() === 'Category' && el.offsetParent !== null
                            && el.getBoundingClientRect().height < 40) {
                            // Find the combobox container nearby
                            const sibling = el.nextElementSibling;
                            if (sibling) {
                                // Find X/clear button (usually has an svg and is small)
                                const btns = sibling.querySelectorAll('button');
                                for (const btn of btns) {
                                    if (btn.querySelector('svg') && btn.textContent.trim() === '') {
                                        btn.click();
                                        return {cleared: true};
                                    }
                                }
                                // Try input inside
                                const input = sibling.querySelector('input');
                                if (input) {
                                    input.setAttribute('data-cat-input', 'true');
                                    return {input: true, value: input.value};
                                }
                            }
                        }
                    }
                    return {found: false};
                }""")
                print(f"  Category clear: {x_result}")
                await asyncio.sleep(1)

                # Now type in the category input
                cat_input = page.locator('[data-cat-input="true"]').first
                try:
                    if await cat_input.is_visible(timeout=3000):
                        await cat_input.click()
                        await cat_input.fill("Self Improvement")
                        await asyncio.sleep(1)
                        await page.screenshot(path=str(SCREENSHOTS / "ct_06_cat_dropdown.png"))

                        # Select from dropdown via JS click (avoids overlay issues)
                        cat_selected = await page.evaluate("""() => {
                            // Look for dropdown options
                            const options = document.querySelectorAll('[role="option"], [role="listbox"] li, [class*="option"]');
                            for (const opt of options) {
                                if (opt.textContent.includes('Self Improvement') && opt.offsetParent !== null) {
                                    opt.click();
                                    return {selected: true, text: opt.textContent.trim()};
                                }
                            }
                            // Try any visible element with "Self Improvement"
                            const all = document.querySelectorAll('*');
                            for (const el of all) {
                                if (el.children.length === 0 && el.textContent.trim() === 'Self Improvement'
                                    && el.offsetParent !== null && el.getBoundingClientRect().height < 50) {
                                    el.click();
                                    return {selected: true, text: 'Self Improvement', method: 'text-click'};
                                }
                            }
                            return {selected: false};
                        }""")
                        print(f"  Category select: {cat_selected}")
                        if cat_selected.get('selected'):
                            cat_set = True
                        await asyncio.sleep(1)
                except Exception as e:
                    print(f"  Cat input error: {e}")

                if not cat_set:
                    # Try "Education" instead
                    cat_input2 = page.locator('[data-cat-input="true"]').first
                    try:
                        await cat_input2.click()
                        await cat_input2.fill("")
                        await cat_input2.fill("Education")
                        await asyncio.sleep(1)
                        edu_selected = await page.evaluate("""() => {
                            const all = document.querySelectorAll('*');
                            for (const el of all) {
                                if (el.children.length === 0 && el.textContent.trim() === 'Education'
                                    && el.offsetParent !== null && el.getBoundingClientRect().height < 50) {
                                    el.click();
                                    return true;
                                }
                            }
                            return false;
                        }""")
                        print(f"  Education selected: {edu_selected}")
                        if edu_selected:
                            cat_set = True
                    except Exception as e:
                        print(f"  Education error: {e}")
            except Exception as e:
                print(f"  Category error: {e}")

            # Tags
            print("\n  Adding tags...")
            tag_input = page.locator('input[placeholder*="tag" i]').first
            tags_added = False
            try:
                if await tag_input.is_visible(timeout=5000):
                    for tag in TAGS:
                        await tag_input.click()
                        await tag_input.fill(tag)
                        await asyncio.sleep(0.3)
                        await page.keyboard.press("Enter")
                        await asyncio.sleep(0.5)
                    print(f"  Added {len(TAGS)} tags!")
                    tags_added = True
                else:
                    print("  Tag input not visible, trying JS...")
                    # Try finding it via JS
                    found_tag = await page.evaluate("""() => {
                        const inputs = document.querySelectorAll('input');
                        for (const inp of inputs) {
                            if (inp.placeholder && inp.placeholder.toLowerCase().includes('tag')
                                && inp.offsetParent !== null) {
                                inp.setAttribute('data-tag-input', 'true');
                                return {found: true, ph: inp.placeholder};
                            }
                        }
                        return {found: false};
                    }""")
                    print(f"  Tag input search: {found_tag}")
                    if found_tag.get('found'):
                        ti = page.locator('[data-tag-input="true"]').first
                        for tag in TAGS:
                            await ti.click()
                            await ti.fill(tag)
                            await asyncio.sleep(0.3)
                            await page.keyboard.press("Enter")
                            await asyncio.sleep(0.5)
                        print(f"  Added {len(TAGS)} tags via JS!")
                        tags_added = True
            except Exception as e:
                print(f"  Tags error: {e}")

            await page.screenshot(path=str(SCREENSHOTS / "ct_07_tags_done.png"))

            # Save Share tab
            print("\n  Saving...")
            save = page.locator('button:has-text("Save changes")').first
            if await save.is_visible(timeout=3000):
                await save.click()
                await asyncio.sleep(4)
                print("  Saved!")

            await page.screenshot(path=str(SCREENSHOTS / "ct_08_final.png"), full_page=True)

        except Exception as e:
            print(f"\nERROR: {e}")
            import traceback; traceback.print_exc()
            try:
                await page.screenshot(path=str(SCREENSHOTS / "ct_99_error.png"), full_page=True)
            except Exception:
                pass
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
            print(f"  Price: {prod.get('formatted_price')} ({prod.get('price')} cents)")
            print(f"  PWYW: {prod.get('customizable_price')}")
            print(f"  Published: {prod.get('published')}")
            print(f"  Covers: {len(prod.get('covers', []))}")
            print(f"  Tags: {prod.get('tags', [])}")
            # Check if covers contain our new image
            for c in prod.get('covers', []):
                print(f"    Cover: {c.get('url', '')[:80]}")


if __name__ == "__main__":
    print("=" * 60)
    print("Gumroad: Cover Replace + Category + Tags")
    print("=" * 60)
    asyncio.run(run())
