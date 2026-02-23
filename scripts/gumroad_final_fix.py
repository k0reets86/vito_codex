#!/usr/bin/env python3
"""Final fix: PWYW via Playwright click, replace cover, set category + tags on Share tab."""

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
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        await ctx.add_cookies([{
            "name": "_gumroad_app_session", "value": SESSION_COOKIE,
            "domain": ".gumroad.com", "path": "/", "httpOnly": True, "secure": True, "sameSite": "Lax",
        }])
        page = await ctx.new_page()
        page.set_default_timeout(20000)

        try:
            print("[1] Loading edit page...")
            await page.goto(EDIT_URL, wait_until="networkidle")
            await asyncio.sleep(3)
            if "login" in page.url.lower():
                print("ERROR: Cookie expired!"); await browser.close(); return
            print(f"  OK: {page.url}")

            # ==========================================
            # STEP 1: DISABLE PWYW via Playwright click
            # ==========================================
            print("\n[2] Disabling PWYW...")

            # Scroll to Pricing section
            await page.evaluate("""() => {
                const els = document.querySelectorAll('h2');
                for (const el of els) {
                    if (el.textContent.trim() === 'Pricing') {
                        el.scrollIntoView({behavior: 'instant', block: 'start'});
                        return true;
                    }
                }
                return false;
            }""")
            await asyncio.sleep(1)

            # Use Playwright to find the PWYW checkbox by its label text and click it
            # The checkbox is inside a label with text "Allow customers to pay what they want"
            pwyw_label = page.locator('label:has-text("Allow customers to pay what they want")').first
            try:
                if await pwyw_label.is_visible(timeout=5000):
                    # Find the checkbox inside the label
                    pwyw_cb = pwyw_label.locator('input[type="checkbox"]').first
                    is_checked = await pwyw_cb.is_checked()
                    print(f"  PWYW checkbox checked: {is_checked}")

                    if is_checked:
                        # Use Playwright click on the label (triggers React onChange properly)
                        await pwyw_label.click()
                        await asyncio.sleep(2)

                        # Verify
                        is_checked_after = await pwyw_cb.is_checked()
                        print(f"  PWYW after label click: {is_checked_after}")

                        if is_checked_after:
                            # Try clicking the checkbox directly via Playwright
                            await pwyw_cb.click(force=True)
                            await asyncio.sleep(2)
                            is_checked_after2 = await pwyw_cb.is_checked()
                            print(f"  PWYW after checkbox force click: {is_checked_after2}")

                            if is_checked_after2:
                                # Try dispatch change event
                                await page.evaluate("""() => {
                                    const cbs = document.querySelectorAll('input[type="checkbox"]');
                                    for (const cb of cbs) {
                                        const label = cb.closest('label');
                                        if (label && label.textContent.includes('pay what you want') && cb.checked) {
                                            // React uses synthetic events, try dispatching native events
                                            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                                                window.HTMLInputElement.prototype, 'checked'
                                            ).set;
                                            nativeInputValueSetter.call(cb, false);
                                            cb.dispatchEvent(new Event('input', { bubbles: true }));
                                            cb.dispatchEvent(new Event('change', { bubbles: true }));
                                            return true;
                                        }
                                    }
                                    return false;
                                }""")
                                await asyncio.sleep(2)
                                is_checked_final = await pwyw_cb.is_checked()
                                print(f"  PWYW after React dispatch: {is_checked_final}")
                    else:
                        print("  PWYW already disabled!")
                else:
                    print("  PWYW label not found")
            except Exception as e:
                print(f"  PWYW error: {e}")

            await page.screenshot(path=str(SCREENSHOTS / "final_02_pwyw.png"))

            # Save
            print("  Saving after PWYW...")
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)
            save = page.locator('button:has-text("Save changes")').first
            if await save.is_visible(timeout=3000):
                await save.click()
                await asyncio.sleep(4)
                print("  Saved!")

            # ==========================================
            # STEP 2: REPLACE COVER IMAGE
            # ==========================================
            print("\n[3] Replacing cover image...")

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

            # First, try to delete the existing cover
            # Look for delete button on the cover thumbnail (trash icon or X)
            cover_deleted = False
            try:
                # The cover thumbnail should have a delete/remove button when hovered
                # Find the small thumbnail image in Cover section
                cover_thumb = await page.evaluate("""() => {
                    const h2s = document.querySelectorAll('h2');
                    for (const h2 of h2s) {
                        if (h2.textContent.trim() === 'Cover') {
                            const section = h2.parentElement;
                            if (section) {
                                const imgs = section.querySelectorAll('img');
                                const buttons = section.querySelectorAll('button');
                                return {
                                    imgs: imgs.length,
                                    buttons: Array.from(buttons).map(b => ({
                                        text: b.textContent.trim().substring(0, 40),
                                        ariaLabel: b.getAttribute('aria-label') || '',
                                        title: b.title || '',
                                    })),
                                };
                            }
                        }
                    }
                    return null;
                }""")
                print(f"  Cover section elements: {cover_thumb}")

                # Click on the cover thumbnail to select it, then look for delete
                # On the screenshot, there's a small thumbnail + "+" button
                # Try clicking the thumbnail
                cover_section_imgs = page.locator('h2:has-text("Cover") ~ * img, h2:has-text("Cover") + * img')
                img_count = await cover_section_imgs.count()
                print(f"  Cover section images: {img_count}")

                if img_count > 0:
                    # Click the thumbnail
                    await cover_section_imgs.first.click()
                    await asyncio.sleep(1)
                    await page.screenshot(path=str(SCREENSHOTS / "final_03a_cover_clicked.png"))

                    # Look for delete button (trash icon)
                    delete_btns = page.locator('button[aria-label*="delete" i], button[aria-label*="remove" i], button[title*="delete" i], button[title*="remove" i]')
                    del_count = await delete_btns.count()
                    print(f"  Delete buttons found: {del_count}")

                    if del_count > 0:
                        await delete_btns.first.click()
                        await asyncio.sleep(2)
                        cover_deleted = True
                        print("  Old cover deleted!")
                    else:
                        # Try finding trash icon button near cover
                        # Look at all buttons in cover section parent
                        trash_found = await page.evaluate("""() => {
                            const h2s = document.querySelectorAll('h2');
                            for (const h2 of h2s) {
                                if (h2.textContent.trim() === 'Cover') {
                                    const parent = h2.parentElement;
                                    if (!parent) continue;
                                    const btns = parent.querySelectorAll('button');
                                    const result = [];
                                    for (const b of btns) {
                                        result.push({
                                            text: b.textContent.trim().substring(0, 30),
                                            svg: b.querySelector('svg') ? true : false,
                                            ariaLabel: b.getAttribute('aria-label') || '',
                                            classes: b.className.substring(0, 50),
                                        });
                                    }
                                    return result;
                                }
                            }
                            return [];
                        }""")
                        print(f"  Cover section buttons: {trash_found}")
            except Exception as e:
                print(f"  Cover delete error: {e}")

            # Now upload new cover
            # The "+" button near cover section should add new cover
            try:
                # Find the "+" button near Cover section
                plus_btn = await page.evaluate("""() => {
                    const h2s = document.querySelectorAll('h2');
                    for (const h2 of h2s) {
                        if (h2.textContent.trim() === 'Cover') {
                            const parent = h2.parentElement;
                            if (!parent) continue;
                            const btns = parent.querySelectorAll('button');
                            for (const b of btns) {
                                if (b.textContent.trim() === '+' || b.textContent.trim() === '') {
                                    b.setAttribute('data-plus-btn', 'true');
                                    return true;
                                }
                            }
                        }
                    }
                    return false;
                }""")
                if plus_btn:
                    plus = page.locator('[data-plus-btn="true"]').first
                    try:
                        if await plus.is_visible(timeout=3000):
                            # Click + and expect file chooser or menu
                            async with page.expect_file_chooser(timeout=10000) as fc_info:
                                await plus.click()
                            chooser = await fc_info.value
                            await chooser.set_files(COVER_PATH)
                            print("  New cover uploaded via + button!")
                            await asyncio.sleep(5)
                    except Exception as e:
                        print(f"  + button file chooser failed: {e}")
                        # After clicking +, menu might appear
                        await asyncio.sleep(2)
                        await page.screenshot(path=str(SCREENSHOTS / "final_03b_plus_menu.png"))

                        comp_btn = page.locator('button:has-text("Computer files")').first
                        try:
                            if await comp_btn.is_visible(timeout=3000):
                                async with page.expect_file_chooser(timeout=10000) as fc_info:
                                    await comp_btn.click()
                                chooser = await fc_info.value
                                await chooser.set_files(COVER_PATH)
                                print("  New cover uploaded via Computer files!")
                                await asyncio.sleep(5)
                        except Exception as e2:
                            print(f"  Computer files failed: {e2}")
                            # Try any newly visible file input
                            fi_all = await page.locator('input[type="file"]').all()
                            for fi in fi_all:
                                accept = await fi.evaluate("el => el.accept || ''")
                                if ".mov" in accept or ".mp4" in accept:
                                    await fi.set_input_files(COVER_PATH)
                                    print("  Cover uploaded via video-accepting file input!")
                                    await asyncio.sleep(5)
                                    break
            except Exception as e:
                print(f"  Cover upload error: {e}")

            await page.screenshot(path=str(SCREENSHOTS / "final_03c_cover_done.png"))

            # Save
            print("  Saving after cover...")
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)
            save = page.locator('button:has-text("Save changes")').first
            if await save.is_visible(timeout=3000):
                await save.click()
                await asyncio.sleep(4)
                print("  Saved!")

            # ==========================================
            # STEP 3: SHARE TAB — CATEGORY + TAGS
            # ==========================================
            print("\n[4] Setting category and tags on Share tab...")

            # Click Share tab
            share_tab = page.locator('button:has-text("Share")').first
            if await share_tab.is_visible(timeout=3000):
                await share_tab.click()
                await asyncio.sleep(3)
            else:
                # Try link
                share_link = page.locator('a:has-text("Share")').first
                if await share_link.is_visible(timeout=3000):
                    await share_link.click()
                    await asyncio.sleep(3)

            # Set Category
            print("  Setting category...")
            # Category is a dropdown/combobox — currently "Other"
            # Try clicking it and selecting "Education" or "Self Improvement"
            cat_select = page.locator('text=Category').first
            try:
                await cat_select.scroll_into_view_if_needed()
                await asyncio.sleep(1)
            except Exception:
                pass

            # Find the category dropdown - it shows "Other" with X and dropdown arrow
            cat_dropdown = await page.evaluate("""() => {
                // Look for select elements or combobox
                const selects = document.querySelectorAll('select');
                for (const s of selects) {
                    const options = Array.from(s.options).map(o => o.text);
                    if (options.some(o => o.includes('Other') || o.includes('Education'))) {
                        return {type: 'select', id: s.id, options: options.slice(0, 20)};
                    }
                }
                // Look for div-based dropdown
                const labels = document.querySelectorAll('label, h3, span');
                for (const l of labels) {
                    if (l.textContent.trim() === 'Category') {
                        const sibling = l.nextElementSibling;
                        if (sibling) {
                            return {type: 'div', tag: sibling.tagName, text: sibling.textContent.trim().substring(0, 100)};
                        }
                    }
                }
                return null;
            }""")
            print(f"  Category dropdown: {cat_dropdown}")

            if cat_dropdown and cat_dropdown.get('type') == 'select':
                # Use Playwright to select
                sel = page.locator(f'#{cat_dropdown["id"]}') if cat_dropdown.get('id') else page.locator('select').first
                options = cat_dropdown.get('options', [])
                print(f"  Available categories: {options}")
                # Pick "Self Improvement" or "Education"
                for target in ['Self Improvement', 'Education', 'Business & Finance']:
                    if target in options:
                        await sel.select_option(label=target)
                        print(f"  Category set to: {target}")
                        break
            else:
                # Try clicking the combobox and selecting
                # Look for the "Other" text in a button/combobox
                other_btn = page.locator('button:has-text("Other")').first
                try:
                    if not await other_btn.is_visible(timeout=2000):
                        # Try the div that shows "Other"
                        pass
                except Exception:
                    pass

                # Click the X to clear current category, then type new one
                x_btn = page.locator('button:has(svg):near(:text("Other"))').first
                try:
                    # Just try clicking the combobox area near Category label
                    cat_input = page.locator('input:near(:text("Category"))').first
                    if await cat_input.is_visible(timeout=2000):
                        await cat_input.click()
                        await cat_input.fill("Education")
                        await asyncio.sleep(1)
                        # Select from dropdown
                        edu_option = page.locator('text=Education').first
                        if await edu_option.is_visible(timeout=3000):
                            await edu_option.click()
                            print("  Category set to Education!")
                except Exception as e:
                    print(f"  Category input error: {e}")

            await asyncio.sleep(1)

            # Add Tags
            print("\n  Adding tags...")
            tag_input = page.locator('input[placeholder*="tag" i]').first
            try:
                if await tag_input.is_visible(timeout=5000):
                    for tag in TAGS:
                        await tag_input.click()
                        await tag_input.fill(tag)
                        await asyncio.sleep(0.3)
                        await page.keyboard.press("Enter")
                        await asyncio.sleep(0.5)
                    print(f"  Added {len(TAGS)} tags!")
                else:
                    print("  Tag input not visible")
            except Exception as e:
                print(f"  Tags error: {e}")

            await page.screenshot(path=str(SCREENSHOTS / "final_04_share.png"))

            # Save on Share tab
            print("  Saving...")
            save = page.locator('button:has-text("Save changes")').first
            if await save.is_visible(timeout=3000):
                await save.click()
                await asyncio.sleep(4)
                print("  Saved!")

            await page.screenshot(path=str(SCREENSHOTS / "final_05_done.png"), full_page=True)

        except Exception as e:
            print(f"\nERROR: {e}")
            import traceback; traceback.print_exc()
            try:
                await page.screenshot(path=str(SCREENSHOTS / "final_99_error.png"), full_page=True)
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
            print(f"  URL: {prod.get('short_url')}")
            print(f"  Covers: {len(prod.get('covers', []))}")
            print(f"  Tags: {prod.get('tags', [])}")


if __name__ == "__main__":
    print("=" * 60)
    print("Gumroad FINAL Fix: PWYW + Cover + Category + Tags")
    print("=" * 60)
    asyncio.run(run())
