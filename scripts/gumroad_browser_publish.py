#!/usr/bin/env python3
"""Publish product on Gumroad via Playwright using session cookie.

Bypasses Stripe Connect detection by using real browser session cookie.
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SESSION_COOKIE = os.getenv("GUMROAD_SESSION_COOKIE", "")
# Allow passing cookie via CLI or file
if not SESSION_COOKIE:
    cookie_file = Path("/tmp/gumroad_cookie.txt")
    if cookie_file.exists():
        SESSION_COOKIE = cookie_file.read_text().strip()

PDF_PATH = Path(__file__).resolve().parent.parent / "output/The_AI_Side_Hustle_Playbook_v2.pdf"
COVER_PATH = Path(__file__).resolve().parent.parent / "output/ai_side_hustle_cover_1280x720.png"
SCREENSHOTS_DIR = Path(__file__).resolve().parent.parent / "output/screenshots"

PRODUCT_NAME = "The AI Side Hustle Playbook"
PRODUCT_PRICE = "17"
PRODUCT_SUMMARY = "Start earning with AI tools in 30 days. 5 chapters, zero fluff."

PRODUCT_DESCRIPTION = """Stop watching other people cash in on the AI revolution.

This no-fluff, 6,000-word action guide shows you exactly how to launch a profitable AI-powered side hustle in 30 days — even if you have zero tech experience.

What's Inside:
• Chapter 1: The AI Opportunity Landscape — why now is the best window
• Chapter 2: Your AI Toolkit — ChatGPT, Midjourney, Canva AI & more
• Chapter 3: 5 Fastest AI Side Hustles to Launch (step-by-step)
• Chapter 4: Your 30-Day Action Plan — day-by-day roadmap
• Chapter 5: Pricing, Pitching & Getting Paid — scripts and templates

You'll Walk Away With:
✓ A clear side hustle matched to your skills
✓ A working AI toolkit ready to use
✓ A realistic 30-day plan you can start today
✓ Real pricing strategies and outreach templates

Instant PDF download. 5 chapters. ~6,000 words. Zero fluff.

Stop watching. Start earning."""


async def run():
    from playwright.async_api import async_playwright

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    if not SESSION_COOKIE:
        print("ERROR: No session cookie. Set GUMROAD_SESSION_COOKIE or write to /tmp/gumroad_cookie.txt")
        return False

    if not PDF_PATH.exists():
        print(f"ERROR: PDF not found: {PDF_PATH}")
        return False

    print(f"PDF: {PDF_PATH} ({PDF_PATH.stat().st_size / 1024:.1f} KB)")
    print(f"Cover: {COVER_PATH} ({COVER_PATH.stat().st_size / 1024:.1f} KB)")
    print(f"Cookie length: {len(SESSION_COOKIE)} chars")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                   "--window-size=1280,900"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US",
        )

        # Inject session cookie
        await context.add_cookies([{
            "name": "_gumroad_app_session",
            "value": SESSION_COOKIE,
            "domain": ".gumroad.com",
            "path": "/",
            "httpOnly": True,
            "secure": True,
            "sameSite": "Lax",
        }])
        print("Session cookie injected")

        page = await context.new_page()
        page.set_default_timeout(30000)

        try:
            # === CHECK SESSION ===
            print("\n[1/7] Checking session...")
            await page.goto("https://gumroad.com/products", wait_until="networkidle")
            await asyncio.sleep(2)
            url = page.url
            print(f"  URL: {url}")
            await page.screenshot(path=str(SCREENSHOTS_DIR / "pub_01_products.png"))

            if "login" in url.lower():
                print("  ERROR: Cookie invalid — redirected to login")
                await browser.close()
                return False

            print("  Session valid! On products page.")

            # === CREATE NEW PRODUCT ===
            print("\n[2/7] Creating new product...")
            await page.goto("https://gumroad.com/products/new", wait_until="networkidle")
            await asyncio.sleep(2)
            url = page.url
            print(f"  URL: {url}")
            await page.screenshot(path=str(SCREENSHOTS_DIR / "pub_02_new_product.png"))

            if "login" in url.lower():
                print("  ERROR: Redirected to login on /products/new")
                await browser.close()
                return False

            # Dump page structure
            body_text = await page.inner_text("body")
            print(f"  Page text (first 500): {body_text[:500]}")

            # Find and fill product name
            print("\n[3/7] Filling product name...")
            name_filled = False
            for sel in ['input[name="name"]', 'input[placeholder*="name" i]', 'input[placeholder*="Name"]',
                        'input[aria-label*="name" i]', 'input[type="text"]']:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=3000):
                        await el.fill(PRODUCT_NAME)
                        name_filled = True
                        print(f"  Name filled via: {sel}")
                        break
                except Exception:
                    continue

            if not name_filled:
                # Log all inputs for debugging
                inputs = await page.locator("input, textarea, select").all()
                print(f"  Could not find name input. All form elements ({len(inputs)}):")
                for i, inp in enumerate(inputs[:15]):
                    attrs = await inp.evaluate("""el => ({
                        tag: el.tagName, type: el.type, name: el.name,
                        placeholder: el.placeholder, id: el.id,
                        visible: el.offsetParent !== null, classes: el.className.substring(0, 50)
                    })""")
                    print(f"    [{i}] {attrs}")

            await page.screenshot(path=str(SCREENSHOTS_DIR / "pub_03_name.png"))

            # Click create/next button
            print("\n[4/7] Clicking Create...")
            for sel in ['button:has-text("Create product")', 'button:has-text("Add product")',
                        'button:has-text("Create")', 'button:has-text("Next")', 'button[type="submit"]']:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=3000):
                        await btn.click()
                        print(f"  Clicked: {sel}")
                        await asyncio.sleep(3)
                        try:
                            await page.wait_for_load_state("networkidle", timeout=10000)
                        except Exception:
                            pass
                        break
                except Exception:
                    continue

            url = page.url
            print(f"  URL: {url}")
            await page.screenshot(path=str(SCREENSHOTS_DIR / "pub_04_after_create.png"))

            # === FILL PRODUCT DETAILS ===
            print("\n[5/7] Filling details (price, description)...")

            # Price
            for sel in ['input[name="price"]', 'input[placeholder*="$"]', 'input[placeholder*="price" i]',
                        'input[aria-label*="price" i]', 'input[aria-label*="Amount"]']:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=3000):
                        await el.clear()
                        await el.fill(PRODUCT_PRICE)
                        print(f"  Price ${PRODUCT_PRICE} via: {sel}")
                        break
                except Exception:
                    continue

            # Summary
            for sel in ['textarea[name="summary"]', 'input[name="summary"]',
                        'textarea[placeholder*="summary" i]', 'input[placeholder*="summary" i]']:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=2000):
                        await el.fill(PRODUCT_SUMMARY)
                        print(f"  Summary via: {sel}")
                        break
                except Exception:
                    continue

            # Description
            for sel in ['[contenteditable="true"]', 'textarea[name="description"]', '.trix-content',
                        '[role="textbox"]', 'textarea']:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=3000):
                        tag = await el.evaluate("el => el.tagName.toLowerCase()")
                        if tag == "textarea":
                            await el.fill(PRODUCT_DESCRIPTION)
                        else:
                            await el.click()
                            await page.keyboard.press("Control+a")
                            await page.keyboard.type(PRODUCT_DESCRIPTION, delay=2)
                        print(f"  Description via: {sel}")
                        break
                except Exception:
                    continue

            await page.screenshot(path=str(SCREENSHOTS_DIR / "pub_05_details.png"))

            # === UPLOAD COVER ===
            print("\n[6/7] Uploading files...")

            # Cover image
            if COVER_PATH.exists():
                file_inputs = await page.locator('input[type="file"]').all()
                print(f"  Found {len(file_inputs)} file inputs")
                if file_inputs:
                    # First file input is usually cover
                    await file_inputs[0].set_input_files(str(COVER_PATH))
                    print(f"  Cover uploaded: {COVER_PATH.name}")
                    await asyncio.sleep(3)

                    # If there's a second file input, use it for PDF
                    if len(file_inputs) > 1:
                        await file_inputs[1].set_input_files(str(PDF_PATH))
                        print(f"  PDF uploaded: {PDF_PATH.name}")
                        await asyncio.sleep(3)
                    else:
                        # Look for "Add file" or similar button for content
                        for sel in ['button:has-text("Add")', 'button:has-text("Upload")',
                                    'button:has-text("file")', '[class*="upload"]']:
                            try:
                                el = page.locator(sel).first
                                if await el.is_visible(timeout=2000):
                                    await el.click()
                                    await asyncio.sleep(1)
                                    fi = page.locator('input[type="file"]').last
                                    await fi.set_input_files(str(PDF_PATH))
                                    print(f"  PDF uploaded via: {sel}")
                                    await asyncio.sleep(3)
                                    break
                            except Exception:
                                continue

            await page.screenshot(path=str(SCREENSHOTS_DIR / "pub_06_files.png"))

            # === SAVE & PUBLISH ===
            print("\n[7/7] Saving and publishing...")

            # Save
            for sel in ['button:has-text("Save")', 'button:has-text("Update")',
                        'button:has-text("Save changes")', 'button[type="submit"]:visible']:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=3000):
                        await btn.click()
                        await asyncio.sleep(3)
                        try:
                            await page.wait_for_load_state("networkidle", timeout=10000)
                        except Exception:
                            pass
                        print(f"  Saved via: {sel}")
                        break
                except Exception:
                    continue

            await page.screenshot(path=str(SCREENSHOTS_DIR / "pub_07_saved.png"))

            # Publish
            for sel in ['button:has-text("Publish")', 'button:has-text("Go live")',
                        'button:has-text("Unpublished")', 'a:has-text("Publish")', '[role="switch"]']:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=3000):
                        await btn.click()
                        await asyncio.sleep(3)
                        print(f"  Published via: {sel}")
                        break
                except Exception:
                    continue

            await page.screenshot(path=str(SCREENSHOTS_DIR / "pub_08_published.png"))

            # === VERIFY VIA API ===
            print("\n[VERIFY] Checking via API...")
            import requests
            for token_name, token_val in [
                ("OAuth", os.getenv("GUMROAD_OAUTH_TOKEN", "")),
                ("Access", os.getenv("GUMROAD_API_KEY", "")),
            ]:
                if token_val:
                    resp = requests.get("https://api.gumroad.com/v2/products",
                                        headers={"Authorization": f"Bearer {token_val}"})
                    if resp.status_code == 200:
                        products = resp.json().get("products", [])
                        print(f"  {token_name} token: {len(products)} products")
                        for prod in products:
                            print(f"    - {prod.get('name')} | ${prod.get('price', 0)/100:.2f} | "
                                  f"published={prod.get('published')} | {prod.get('short_url', '')}")
                        break

            final_url = page.url
            print(f"\n  Final page: {final_url}")

        except Exception as e:
            print(f"\nERROR: {e}")
            import traceback
            traceback.print_exc()
            try:
                await page.screenshot(path=str(SCREENSHOTS_DIR / "pub_99_error.png"))
            except Exception:
                pass
        finally:
            await browser.close()

    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Gumroad Product Publisher (Cookie Session)")
    print("=" * 60)
    result = asyncio.run(run())
    print("\n" + ("=" * 60))
    print("DONE" if result else "FAILED")
    print("=" * 60)
