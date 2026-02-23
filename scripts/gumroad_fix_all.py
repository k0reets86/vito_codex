#!/usr/bin/env python3
"""Fix Gumroad product: disable PWYW, set $9, upload cover (no price), add tags/category."""

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
            # === LOAD EDIT PAGE ===
            print("[1] Loading edit page...")
            await page.goto(EDIT_URL, wait_until="networkidle")
            await asyncio.sleep(3)
            if "login" in page.url.lower():
                print("ERROR: Cookie expired!")
                await browser.close()
                return
            print(f"  OK: {page.url}")
            await page.screenshot(path=str(SCREENSHOTS / "fixall_01_loaded.png"), full_page=True)

            # === FIX PWYW: Find and click the toggle switch ===
            print("\n[2] Disabling PWYW toggle...")

            # Scroll to Pricing section
            await page.evaluate("""() => {
                const els = document.querySelectorAll('h2, h3, label, span, div');
                for (const el of els) {
                    const t = el.textContent.trim();
                    if ((t === 'Pricing' || t === 'Amount') && el.offsetParent !== null) {
                        el.scrollIntoView({behavior: 'instant', block: 'center'});
                        return true;
                    }
                }
                window.scrollTo(0, document.body.scrollHeight / 2);
                return false;
            }""")
            await asyncio.sleep(1)

            # Find the PWYW toggle - try multiple approaches
            pwyw_toggled = False

            # Approach 1: Find role="switch" near "pay what you want" text
            try:
                toggle = await page.evaluate("""() => {
                    // Find text containing "pay what you want"
                    const allText = document.querySelectorAll('*');
                    for (const el of allText) {
                        if (el.children.length === 0 && el.textContent.toLowerCase().includes('pay what you want')) {
                            // Find toggle near this element - look in parent containers
                            let container = el.parentElement;
                            for (let i = 0; i < 5; i++) {
                                if (!container) break;
                                // Look for switch role, checkbox input, or toggle-like elements
                                const sw = container.querySelector('[role="switch"], input[type="checkbox"], .toggle, [class*="toggle"], [class*="switch"]');
                                if (sw) {
                                    sw.click();
                                    return {found: true, tag: sw.tagName, role: sw.getAttribute('role'), type: sw.type};
                                }
                                container = container.parentElement;
                            }
                        }
                    }
                    return {found: false};
                }""")
                print(f"  Toggle search result: {toggle}")
                if toggle.get("found"):
                    pwyw_toggled = True
                    print("  Clicked PWYW toggle via JS!")
                    await asyncio.sleep(2)
            except Exception as e:
                print(f"  Approach 1 failed: {e}")

            # Approach 2: Try clicking the label/text itself as toggle trigger
            if not pwyw_toggled:
                try:
                    # Look for the clickable toggle area
                    result = await page.evaluate("""() => {
                        const els = document.querySelectorAll('label, div, span, button');
                        for (const el of els) {
                            if (el.textContent.includes('pay what you want') && el.offsetParent !== null) {
                                // Check if this element or its children have an input
                                const input = el.querySelector('input[type="checkbox"]');
                                if (input) {
                                    input.click();
                                    return {found: true, method: 'checkbox_in_label'};
                                }
                                // Check for a toggle button within
                                const btn = el.querySelector('button, [role="switch"]');
                                if (btn) {
                                    btn.click();
                                    return {found: true, method: 'button_in_label'};
                                }
                            }
                        }
                        // Try all checkboxes on the page
                        const checkboxes = document.querySelectorAll('input[type="checkbox"]');
                        const info = [];
                        for (const cb of checkboxes) {
                            const label = cb.closest('label, div, section');
                            const text = label ? label.textContent.substring(0, 80) : '';
                            info.push({checked: cb.checked, text, id: cb.id, name: cb.name});
                        }
                        return {found: false, checkboxes: info};
                    }""")
                    print(f"  Approach 2: {result}")
                    if result.get("found"):
                        pwyw_toggled = True
                        await asyncio.sleep(2)
                except Exception as e:
                    print(f"  Approach 2 failed: {e}")

            # Approach 3: Try using Playwright locator for the toggle
            if not pwyw_toggled:
                try:
                    # Try clicking elements that look like toggles
                    for selector in [
                        'button[role="switch"]',
                        '[class*="toggle"]',
                        'label:has-text("pay what you want") input',
                        'label:has-text("pay what you want")',
                    ]:
                        try:
                            el = page.locator(selector).first
                            if await el.is_visible(timeout=2000):
                                await el.click()
                                print(f"  Clicked toggle via: {selector}")
                                pwyw_toggled = True
                                await asyncio.sleep(2)
                                break
                        except Exception:
                            continue
                except Exception as e:
                    print(f"  Approach 3 failed: {e}")

            # Approach 4: Dump DOM around PWYW for debugging
            if not pwyw_toggled:
                html_dump = await page.evaluate("""() => {
                    const els = document.querySelectorAll('*');
                    for (const el of els) {
                        if (el.children.length === 0 && el.textContent.toLowerCase().includes('pay what you want')) {
                            // Get parent chain HTML
                            let parent = el.parentElement;
                            for (let i = 0; i < 3; i++) {
                                if (parent && parent.parentElement) parent = parent.parentElement;
                            }
                            return parent ? parent.outerHTML.substring(0, 3000) : 'no parent';
                        }
                    }
                    return 'not found';
                }""")
                print(f"  PWYW DOM dump:\n{html_dump[:2000]}")

            await page.screenshot(path=str(SCREENSHOTS / "fixall_02_pwyw.png"), full_page=True)

            # === SET PRICE ===
            print("\n[3] Setting price...")

            # Find all visible inputs and their values
            inputs_info = await page.evaluate("""() => {
                const inputs = document.querySelectorAll('input:not([type="hidden"]):not([type="file"]):not([type="checkbox"])');
                return Array.from(inputs).map((el, i) => ({
                    i, type: el.type, name: el.name || '',
                    placeholder: el.placeholder || '', value: el.value,
                    visible: el.offsetParent !== null,
                    ariaLabel: el.getAttribute('aria-label') || '',
                }));
            }""")

            print(f"  Visible inputs:")
            for info in inputs_info:
                if info.get('visible'):
                    print(f"    [{info['i']}] type={info['type']} name={info['name']} ph={info['placeholder']} val={info['value']}")

            # Set price to 9
            price_set = False
            all_inputs = page.locator('input:not([type="hidden"]):not([type="file"]):not([type="checkbox"])')

            for info in inputs_info:
                if not info.get('visible'):
                    continue
                val = info.get('value', '')
                # Look for price-like inputs (current value 9 or contains dollar amount)
                if val in ('9', '9.00', '17', '17.00', '0', '0.00'):
                    idx = info['i']
                    el = all_inputs.nth(idx)
                    await el.scroll_into_view_if_needed()
                    await el.click()
                    await el.fill("")
                    await el.type("9", delay=50)
                    print(f"  Price set to $9 (input [{idx}], was '{val}')")
                    price_set = True
                    break

            if not price_set:
                # Try placeholder-based search
                for sel in ['input[placeholder*="Amount"]', 'input[placeholder*="Price"]',
                            'input[placeholder*="price"]', 'input[aria-label*="price" i]']:
                    try:
                        el = page.locator(sel).first
                        if await el.is_visible(timeout=2000):
                            await el.click()
                            await el.fill("9")
                            print(f"  Price set to $9 via: {sel}")
                            price_set = True
                            break
                    except Exception:
                        continue

            await page.screenshot(path=str(SCREENSHOTS / "fixall_03_price.png"))

            # === SAVE (after price fix) ===
            print("\n[3b] Saving after price fix...")
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)
            for sel in ['button:has-text("Save and continue")', 'button:has-text("Save changes")', 'button:has-text("Save")']:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=3000):
                        await btn.click()
                        await asyncio.sleep(4)
                        print(f"  Saved via: {sel}")
                        break
                except Exception:
                    continue

            # === UPLOAD COVER ===
            print("\n[4] Uploading new cover (no price)...")

            # Scroll to Cover section
            await page.evaluate("""() => {
                const els = document.querySelectorAll('h2, h3, label, span, div');
                for (const el of els) {
                    if (el.textContent.trim() === 'Cover' && el.offsetParent !== null
                        && el.getBoundingClientRect().height < 50) {
                        el.scrollIntoView({behavior: 'instant', block: 'center'});
                        return true;
                    }
                }
                return false;
            }""")
            await asyncio.sleep(1)

            # Find cover file input (accepts video formats .mov/.mp4)
            cover_uploaded = False
            fi_all = await page.locator('input[type="file"]').all()
            print(f"  File inputs on page: {len(fi_all)}")
            for i, fi in enumerate(fi_all):
                attrs = await fi.evaluate("el => ({accept: el.accept || '', multiple: el.multiple})")
                print(f"    [{i}] accept={attrs['accept'][:60]} multiple={attrs['multiple']}")
                if ".mov" in attrs["accept"] or ".mp4" in attrs["accept"]:
                    await fi.set_input_files(COVER_PATH)
                    print(f"  Cover uploaded via file input [{i}]!")
                    cover_uploaded = True
                    await asyncio.sleep(5)
                    break

            if not cover_uploaded:
                print("  WARNING: Could not find cover file input")

            await page.screenshot(path=str(SCREENSHOTS / "fixall_04_cover.png"))

            # === SAVE (after cover) ===
            print("\n[4b] Saving after cover...")
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)
            for sel in ['button:has-text("Save and continue")', 'button:has-text("Save changes")', 'button:has-text("Save")']:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=3000):
                        await btn.click()
                        await asyncio.sleep(4)
                        print(f"  Saved via: {sel}")
                        break
                except Exception:
                    continue

            # === ADD TAGS ===
            print("\n[5] Adding tags...")

            # Look for tag input on the page
            tags_to_add = ["AI", "side hustle", "passive income", "ChatGPT", "make money online", "ebook", "artificial intelligence"]

            # Scroll down to find tags section
            await page.evaluate("""() => {
                const els = document.querySelectorAll('h2, h3, label, span, div');
                for (const el of els) {
                    const t = el.textContent.trim().toLowerCase();
                    if ((t === 'tags' || t === 'discover') && el.offsetParent !== null) {
                        el.scrollIntoView({behavior: 'instant', block: 'center'});
                        return true;
                    }
                }
                return false;
            }""")
            await asyncio.sleep(1)

            # Try to find tag input
            tag_input_found = False
            for sel in [
                'input[placeholder*="tag" i]',
                'input[placeholder*="Tag" i]',
                'input[aria-label*="tag" i]',
                'input[placeholder*="Add" i]',
            ]:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=2000):
                        for tag in tags_to_add:
                            await el.click()
                            await el.fill(tag)
                            await page.keyboard.press("Enter")
                            await asyncio.sleep(0.5)
                        print(f"  Added {len(tags_to_add)} tags via: {sel}")
                        tag_input_found = True
                        break
                except Exception:
                    continue

            if not tag_input_found:
                # Dump page to find tags section
                tags_dump = await page.evaluate("""() => {
                    const result = [];
                    const inputs = document.querySelectorAll('input:not([type="hidden"]):not([type="file"])');
                    for (const inp of inputs) {
                        if (inp.offsetParent !== null) {
                            result.push({
                                ph: inp.placeholder,
                                type: inp.type,
                                name: inp.name,
                                ariaLabel: inp.getAttribute('aria-label') || '',
                                value: inp.value,
                            });
                        }
                    }
                    return result;
                }""")
                print(f"  All visible inputs for tags: {tags_dump}")

            await page.screenshot(path=str(SCREENSHOTS / "fixall_05_tags.png"))

            # === SET CATEGORY ===
            print("\n[6] Setting category...")

            # Look for category selector
            category_set = False
            for sel in [
                'select[name*="category" i]',
                '[class*="category"] select',
                'button:has-text("Choose a category")',
                'button:has-text("Select category")',
            ]:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=2000):
                        tag_name = await el.evaluate("el => el.tagName")
                        if tag_name.lower() == 'select':
                            # Try to select "Education" or "Other"
                            options = await el.evaluate("""el => Array.from(el.options).map(o => ({value: o.value, text: o.text}))""")
                            print(f"  Category options: {options}")
                            for opt in options:
                                if 'education' in opt['text'].lower() or 'self' in opt['text'].lower():
                                    await el.select_option(value=opt['value'])
                                    print(f"  Category set to: {opt['text']}")
                                    category_set = True
                                    break
                            if not category_set and options:
                                # Pick "Other" or first non-empty
                                for opt in options:
                                    if opt['value'] and opt['text'] != '':
                                        await el.select_option(value=opt['value'])
                                        print(f"  Category set to: {opt['text']}")
                                        category_set = True
                                        break
                        else:
                            await el.click()
                            await asyncio.sleep(1)
                            # Look for "Education" in dropdown
                            edu = page.locator('text=Education').first
                            try:
                                if await edu.is_visible(timeout=2000):
                                    await edu.click()
                                    print("  Category set to: Education")
                                    category_set = True
                            except Exception:
                                pass
                        break
                except Exception:
                    continue

            if not category_set:
                # Try dropdown button approach
                cat_dump = await page.evaluate("""() => {
                    const selects = document.querySelectorAll('select');
                    const result = [];
                    for (const s of selects) {
                        result.push({
                            name: s.name, id: s.id,
                            visible: s.offsetParent !== null,
                            options: Array.from(s.options).map(o => o.text).slice(0, 5),
                        });
                    }
                    return result;
                }""")
                print(f"  All selects: {cat_dump}")

            await page.screenshot(path=str(SCREENSHOTS / "fixall_06_category.png"))

            # === FINAL SAVE ===
            print("\n[7] Final save...")
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)
            for sel in ['button:has-text("Save and continue")', 'button:has-text("Save changes")', 'button:has-text("Save")']:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=3000):
                        await btn.click()
                        await asyncio.sleep(4)
                        print(f"  Final saved via: {sel}")
                        break
                except Exception:
                    continue

            await page.screenshot(path=str(SCREENSHOTS / "fixall_07_final.png"), full_page=True)

        except Exception as e:
            print(f"\nERROR: {e}")
            import traceback; traceback.print_exc()
            try:
                await page.screenshot(path=str(SCREENSHOTS / "fixall_99_error.png"), full_page=True)
            except Exception:
                pass
        finally:
            await browser.close()

    # === VERIFY VIA API ===
    print("\n[VERIFY] Checking via API...")
    import requests
    token = os.getenv("GUMROAD_API_KEY", "")
    if token:
        r = requests.get("https://api.gumroad.com/v2/products", params={"access_token": token})
        if r.status_code == 200:
            for prod in r.json().get("products", []):
                print(f"  Name: {prod.get('name')}")
                print(f"  Price: {prod.get('formatted_price')} (raw: {prod.get('price')} cents)")
                print(f"  PWYW: {prod.get('customizable_price')}")
                print(f"  Published: {prod.get('published')}")
                print(f"  URL: {prod.get('short_url')}")
                print(f"  Covers: {len(prod.get('covers', []))}")
                print(f"  Tags: {prod.get('tags', [])}")


if __name__ == "__main__":
    print("=" * 60)
    print("Gumroad Fix All: PWYW + Price + Cover + Tags + Category")
    print("=" * 60)
    asyncio.run(run())
