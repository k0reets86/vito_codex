#!/usr/bin/env python3
"""Fix Gumroad product: upload cover to Cover section, set price $9."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SESSION_COOKIE = Path("/tmp/gumroad_cookie.txt").read_text().strip() if Path("/tmp/gumroad_cookie.txt").exists() else ""
EDIT_URL = "https://gumroad.com/products/wblqda/edit"
COVER_PATH = Path(__file__).resolve().parent.parent / "output/ai_side_hustle_cover_1280x720.png"
SCREENSHOTS = Path(__file__).resolve().parent.parent / "output/screenshots"


async def run():
    from playwright.async_api import async_playwright

    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    if not SESSION_COOKIE:
        print("ERROR: No cookie"); return False

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
            await asyncio.sleep(2)
            if "login" in page.url.lower():
                print("  ERROR: Cookie expired"); return False
            print(f"  OK: {page.url}")

            # ===== FIX 1: COVER IMAGE =====
            print("\n[2] Uploading cover to Cover section...")

            # Scroll to Cover section
            await page.evaluate("""() => {
                const headings = document.querySelectorAll('h2, h3, label, span, div');
                for (const el of headings) {
                    if (el.textContent.trim() === 'Cover') {
                        el.scrollIntoView({behavior: 'instant', block: 'center'});
                        return true;
                    }
                }
                return false;
            }""")
            await asyncio.sleep(1)
            await page.screenshot(path=str(SCREENSHOTS / "fix2_01_cover_section.png"))

            # Click "Computer files" button in Cover section
            comp_files_btn = page.locator('button:has-text("Computer files")').first
            try:
                if await comp_files_btn.is_visible(timeout=5000):
                    print("  Found 'Computer files' button, clicking...")
                    async with page.expect_file_chooser(timeout=10000) as fc_info:
                        await comp_files_btn.click()
                    file_chooser = await fc_info.value
                    await file_chooser.set_files(str(COVER_PATH))
                    print(f"  Cover uploaded! ({COVER_PATH.name})")
                    await asyncio.sleep(5)
                else:
                    print("  'Computer files' button not visible")
            except Exception as e:
                print(f"  File chooser approach failed: {e}")
                # Try alternative: find hidden file input near Cover
                try:
                    # Evaluate to find file input in Cover section context
                    result = await page.evaluate("""() => {
                        const sections = document.querySelectorAll('*');
                        let coverSection = null;
                        for (const el of sections) {
                            if (el.textContent.trim() === 'Cover' && (el.tagName === 'H2' || el.tagName === 'H3' || el.tagName === 'LABEL' || el.tagName === 'SPAN')) {
                                coverSection = el.closest('section') || el.parentElement?.parentElement;
                                break;
                            }
                        }
                        if (coverSection) {
                            const fi = coverSection.querySelector('input[type="file"]');
                            if (fi) {
                                fi.setAttribute('data-cover-input', 'true');
                                return 'found';
                            }
                        }
                        return 'not_found';
                    }""")
                    if result == 'found':
                        fi = page.locator('input[data-cover-input="true"]')
                        await fi.set_input_files(str(COVER_PATH))
                        print("  Cover uploaded via section file input!")
                        await asyncio.sleep(5)
                    else:
                        print("  Could not find cover file input in section")
                except Exception as e2:
                    print(f"  Alternative also failed: {e2}")

            await page.screenshot(path=str(SCREENSHOTS / "fix2_02_after_cover.png"))

            # ===== FIX 2: PRICE $9 =====
            print("\n[3] Setting price to $9...")

            # Scroll to Pricing section
            await page.evaluate("""() => {
                const headings = document.querySelectorAll('h2, h3, label, span, div');
                for (const el of headings) {
                    if (el.textContent.trim() === 'Pricing' || el.textContent.trim() === 'Amount') {
                        el.scrollIntoView({behavior: 'instant', block: 'center'});
                        return true;
                    }
                }
                // Fallback: scroll to bottom
                window.scrollTo(0, document.body.scrollHeight);
                return false;
            }""")
            await asyncio.sleep(1)
            await page.screenshot(path=str(SCREENSHOTS / "fix2_03_pricing_section.png"))

            # Find price input — try multiple approaches
            price_set = False

            # Dump all visible inputs for debugging
            inputs_info = await page.evaluate("""() => {
                const inputs = document.querySelectorAll('input:not([type="hidden"]):not([type="file"])');
                return Array.from(inputs).map((el, i) => ({
                    i, tag: el.tagName, type: el.type, name: el.name,
                    placeholder: el.placeholder, value: el.value,
                    id: el.id, visible: el.offsetParent !== null,
                    ariaLabel: el.getAttribute('aria-label') || '',
                    classes: el.className.substring(0, 60)
                }));
            }""")
            print(f"  All inputs ({len(inputs_info)}):")
            for info in inputs_info:
                if info.get('visible'):
                    print(f"    [{info['i']}] type={info['type']} name={info['name']} placeholder={info['placeholder']} value={info['value']} aria={info['ariaLabel']}")

            # Try to find price input by value "17" or placeholder
            for info in inputs_info:
                if info.get('value') == '17' or info.get('value') == '17.00':
                    # Found the price input!
                    idx = info['i']
                    all_inputs = page.locator('input:not([type="hidden"]):not([type="file"])')
                    price_el = all_inputs.nth(idx)
                    await price_el.scroll_into_view_if_needed()
                    await asyncio.sleep(0.5)
                    await price_el.click()
                    await price_el.fill("")
                    await price_el.type("9", delay=50)
                    print(f"  Price changed from $17 to $9 (input [{idx}])")
                    price_set = True
                    break

            if not price_set:
                # Try by placeholder
                for sel in ['input[placeholder*="Price"]', 'input[placeholder*="price"]',
                            'input[placeholder*="Amount"]', 'input[placeholder*="0"]']:
                    try:
                        el = page.locator(sel).first
                        if await el.is_visible(timeout=2000):
                            val = await el.input_value()
                            print(f"  Found input via {sel}, current value: {val}")
                            await el.click()
                            await el.fill("9")
                            print(f"  Price set to $9 via: {sel}")
                            price_set = True
                            break
                    except Exception:
                        continue

            await page.screenshot(path=str(SCREENSHOTS / "fix2_04_price_set.png"))

            # ===== SAVE =====
            print("\n[4] Saving...")
            # Scroll to top where Save button is
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)

            for sel in ['button:has-text("Save and continue")', 'button:has-text("Save changes")',
                        'button:has-text("Save")']:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=3000):
                        await btn.click()
                        await asyncio.sleep(4)
                        try:
                            await page.wait_for_load_state("networkidle", timeout=10000)
                        except Exception:
                            pass
                        print(f"  Saved via: {sel}")
                        break
                except Exception:
                    continue

            await page.screenshot(path=str(SCREENSHOTS / "fix2_05_saved.png"), full_page=True)

            # ===== VERIFY =====
            print("\n[VERIFY]")
            import requests
            token = os.getenv("GUMROAD_OAUTH_TOKEN", "")
            if token:
                r = requests.get("https://api.gumroad.com/v2/products",
                                 headers={"Authorization": f"Bearer {token}"})
                if r.status_code == 200:
                    for prod in r.json().get("products", []):
                        print(f"  Name: {prod.get('name')}")
                        print(f"  Price: {prod.get('formatted_price')} (raw: {prod.get('price')} cents)")
                        print(f"  Published: {prod.get('published')}")
                        print(f"  URL: {prod.get('short_url')}")
                        covers = prod.get('covers', [])
                        print(f"  Covers: {len(covers) if covers else 'none'}")
                        print(f"  Thumbnail: {'yes' if prod.get('thumbnail_url') else 'no'}")

        except Exception as e:
            print(f"\nERROR: {e}")
            import traceback; traceback.print_exc()
            try:
                await page.screenshot(path=str(SCREENSHOTS / "fix2_99_error.png"), full_page=True)
            except Exception:
                pass
        finally:
            await browser.close()

    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Gumroad Fix v2 (cover + price $9)")
    print("=" * 60)
    asyncio.run(run())
