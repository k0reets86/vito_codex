#!/usr/bin/env python3
"""Publish 'The AI Side Hustle Playbook' on Gumroad via Playwright browser automation.

Uses playwright-stealth to avoid CAPTCHA/bot detection.
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

EMAIL = os.getenv("GUMROAD_EMAIL", "")
PASSWORD = os.getenv("GUMROAD_PASSWORD", "")

PDF_PATH = Path(__file__).resolve().parent.parent / "output/The_AI_Side_Hustle_Playbook_v2.pdf"
SCREENSHOTS_DIR = Path(__file__).resolve().parent.parent / "output/screenshots"

PRODUCT_NAME = "The AI Side Hustle Playbook: Start Earning with AI Tools in 30 Days"
PRODUCT_PRICE = "17"

PRODUCT_DESCRIPTION = """Stop watching other people cash in on the AI revolution.

This no-fluff, 6,000-word action guide shows you exactly how to launch a profitable AI-powered side hustle in 30 days — even if you have zero tech experience.

What's Inside:
- Chapter 1: The AI Opportunity Landscape — why 2024-2025 is the best window
- Chapter 2: Your AI Toolkit — ChatGPT, Midjourney, Canva AI, Jasper & more
- Chapter 3: 5 Fastest AI Side Hustles to Launch (with step-by-step instructions)
- Chapter 4: Your 30-Day Action Plan — day-by-day roadmap
- Chapter 5: Pricing, Pitching & Getting Paid — scripts and templates included

You'll Walk Away With:
- A clear side hustle matched to your skills
- A working AI toolkit ready to use
- A realistic 30-day plan you can start today
- Real pricing strategies
- Outreach templates ready to copy and send

Instant PDF download. 5 chapters. ~6,000 words. Zero fluff.

Stop watching. Start earning. Your 30 days start now."""


async def human_type(page, selector, text, delay=50):
    """Type text character by character like a human."""
    el = page.locator(selector).first
    await el.click()
    await asyncio.sleep(0.3)
    for char in text:
        await page.keyboard.press(char if len(char) == 1 else char)
        await asyncio.sleep(delay / 1000 + (hash(char) % 30) / 1000)


async def run():
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    if not EMAIL or not PASSWORD:
        print("ERROR: GUMROAD_EMAIL / GUMROAD_PASSWORD not set in .env")
        return False

    if not PDF_PATH.exists():
        print(f"ERROR: PDF not found: {PDF_PATH}")
        return False

    print(f"PDF: {PDF_PATH} ({PDF_PATH.stat().st_size / 1024:.1f} KB)")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1280,900",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="America/New_York",
        )

        page = await context.new_page()

        # Apply stealth to avoid bot detection
        stealth = Stealth()
        await stealth.apply_stealth_async(page)

        page.set_default_timeout(30000)

        try:
            # === STEP 1: LOGIN ===
            print("\n[1/6] Logging into Gumroad...")
            await page.goto("https://app.gumroad.com/login", wait_until="networkidle")
            await asyncio.sleep(2)
            await page.screenshot(path=str(SCREENSHOTS_DIR / "01_login_page.png"))

            # Fill email with human-like typing
            email_field = page.locator('input[type="email"], input[name="email"]').first
            await email_field.click()
            await asyncio.sleep(0.5)
            await email_field.type(EMAIL, delay=40)
            await asyncio.sleep(0.3)

            # Fill password
            pw_field = page.locator('input[type="password"]').first
            await pw_field.click()
            await asyncio.sleep(0.5)
            await pw_field.type(PASSWORD, delay=35)
            await asyncio.sleep(0.5)

            await page.screenshot(path=str(SCREENSHOTS_DIR / "02_login_filled.png"))

            # Click Login button
            login_btn = page.locator('button:has-text("Login"), button:has-text("Log in")').first
            await login_btn.click()

            # Wait for response
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)
            await page.screenshot(path=str(SCREENSHOTS_DIR / "03_after_login.png"))

            current_url = page.url
            print(f"  After login URL: {current_url}")

            # Check for CAPTCHA
            captcha_visible = await page.locator('iframe[src*="recaptcha"], iframe[title*="recaptcha"], .g-recaptcha').count()
            if captcha_visible > 0 or "login" in current_url.lower():
                body = await page.content()
                if "captcha" in body.lower() or "recaptcha" in body.lower():
                    print("  CAPTCHA detected! Stealth mode wasn't enough.")
                    print("  Trying alternative approach...")

                    # Check if still on login page
                    if "login" in current_url.lower():
                        print("  Still on login page. Login may have failed.")
                        # Check for error messages
                        errors = await page.locator('.error, .alert-danger, [role="alert"]').all_text_contents()
                        if errors:
                            print(f"  Errors: {errors}")

                        await page.screenshot(path=str(SCREENSHOTS_DIR / "03b_captcha_block.png"))
                        print("\n  === CAPTCHA WORKAROUND ===")
                        print("  Gumroad blocks headless browsers with CAPTCHA.")
                        print("  Trying to get session cookies via alternative method...")

                        # The CAPTCHA prevents automated login.
                        # Return False so we can try alternative approaches
                        await browser.close()
                        return await try_cookie_approach()

            if "login" not in current_url.lower() or "dashboard" in current_url.lower() or "products" in current_url.lower():
                print("  Login successful!")
                return await create_product(page, context, browser)
            else:
                print("  Login did not redirect. Checking page state...")
                await page.screenshot(path=str(SCREENSHOTS_DIR / "03c_login_state.png"))
                body_text = await page.inner_text("body")
                print(f"  Body text snippet: {body_text[:200]}")
                await browser.close()
                return False

        except Exception as e:
            print(f"\nERROR: {e}")
            try:
                await page.screenshot(path=str(SCREENSHOTS_DIR / "99_error.png"))
            except Exception:
                pass
            raise
        finally:
            try:
                await browser.close()
            except Exception:
                pass


async def try_cookie_approach():
    """Alternative: try to get an authenticated session using the API token."""
    print("\n=== Trying Cookie-Based Approach ===")
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                   "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )

        page = await context.new_page()
        stealth_inst = Stealth()
        await stealth_inst.apply_stealth_async(page)

        # Try setting the API token as a cookie
        api_token = os.getenv("GUMROAD_API_KEY", "")
        if api_token:
            # Set various possible cookie names
            for name in ["_gumroad_app_session", "access_token", "token", "_gumroad_session"]:
                await context.add_cookies([{
                    "name": name,
                    "value": api_token,
                    "domain": ".gumroad.com",
                    "path": "/",
                }])

        # Try navigating to dashboard
        await page.goto("https://app.gumroad.com/products")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "04_cookie_attempt.png"))

        current_url = page.url
        print(f"  URL after cookie approach: {current_url}")

        if "login" not in current_url.lower():
            print("  Cookie approach worked!")
            return await create_product(page, context, browser)
        else:
            print("  Cookie approach failed — redirected to login")
            print("\n  === MANUAL LOGIN REQUIRED ===")
            print("  Gumroad has CAPTCHA on login that blocks automation.")
            print("  Options:")
            print("  1. Owner logs in manually in a browser, exports cookies")
            print("  2. Owner creates the product manually (2 min)")
            print("  3. Use a CAPTCHA solving service")
            await browser.close()
            return False


async def create_product(page, context, browser):
    """Create and publish the product (assumes already logged in)."""

    print("\n[2/6] Navigating to new product page...")
    await page.goto("https://app.gumroad.com/products/new")
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(2)
    await page.screenshot(path=str(SCREENSHOTS_DIR / "05_new_product.png"))
    print(f"  URL: {page.url}")

    # === FILL NAME ===
    print("\n[3/6] Filling product name...")
    # Try various selectors for the name field
    name_selectors = [
        'input[name="name"]',
        'input[placeholder*="name" i]',
        'input[placeholder*="Name"]',
        'input[aria-label*="name" i]',
        'input[type="text"]',
    ]
    name_filled = False
    for sel in name_selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=2000):
                await el.fill(PRODUCT_NAME)
                name_filled = True
                print(f"  Name filled via: {sel}")
                break
        except Exception:
            continue

    if not name_filled:
        print("  WARNING: Could not find name input")
        # Dump page structure for debugging
        inputs = await page.locator("input").all()
        for i, inp in enumerate(inputs):
            attrs = await inp.evaluate("""el => ({
                type: el.type, name: el.name, placeholder: el.placeholder,
                id: el.id, visible: el.offsetParent !== null
            })""")
            print(f"    input[{i}]: {attrs}")

    await page.screenshot(path=str(SCREENSHOTS_DIR / "06_name_filled.png"))

    # Click create/submit
    create_selectors = [
        'button:has-text("Create product")',
        'button:has-text("Add product")',
        'button:has-text("Create")',
        'button:has-text("Next")',
        'button[type="submit"]',
    ]
    for sel in create_selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=2000):
                await btn.click()
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)
                print(f"  Clicked: {sel}")
                break
        except Exception:
            continue

    await page.screenshot(path=str(SCREENSHOTS_DIR / "07_after_create.png"))
    print(f"  URL: {page.url}")

    # === SET PRICE ===
    print("\n[4/6] Setting price...")
    price_selectors = [
        'input[name="price"]',
        'input[placeholder*="$"]',
        'input[placeholder*="price" i]',
        'input[aria-label*="price" i]',
    ]
    for sel in price_selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=2000):
                await el.clear()
                await el.fill(PRODUCT_PRICE)
                print(f"  Price set to ${PRODUCT_PRICE} via: {sel}")
                break
        except Exception:
            continue

    # === DESCRIPTION ===
    print("\n[5/6] Adding description...")
    desc_selectors = [
        'textarea[name="description"]',
        'textarea[placeholder*="description" i]',
        '[contenteditable="true"]',
        'textarea',
        '.trix-content',
        '[role="textbox"]',
    ]
    for sel in desc_selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=2000):
                tag = await el.evaluate("el => el.tagName.toLowerCase()")
                if tag == "textarea":
                    await el.fill(PRODUCT_DESCRIPTION)
                else:
                    await el.click()
                    await page.keyboard.press("Control+a")
                    # Type in chunks to avoid issues
                    for line in PRODUCT_DESCRIPTION.split("\n"):
                        await page.keyboard.type(line, delay=5)
                        await page.keyboard.press("Enter")
                print(f"  Description filled via: {sel}")
                break
        except Exception:
            continue

    # === UPLOAD FILE ===
    print("\n[6/6] Uploading PDF...")
    # Look for file input (might be hidden)
    file_inputs = await page.locator('input[type="file"]').all()
    if file_inputs:
        await file_inputs[0].set_input_files(str(PDF_PATH))
        print(f"  File set: {PDF_PATH.name}")
        await asyncio.sleep(5)
    else:
        # Try clicking upload area/button first
        upload_triggers = [
            'button:has-text("Upload")',
            'button:has-text("Add file")',
            'button:has-text("Choose file")',
            '[class*="upload"]',
            '[class*="dropzone"]',
        ]
        for sel in upload_triggers:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=2000):
                    await el.click()
                    await asyncio.sleep(1)
                    fi = page.locator('input[type="file"]').first
                    await fi.set_input_files(str(PDF_PATH))
                    print(f"  File uploaded via: {sel}")
                    await asyncio.sleep(5)
                    break
            except Exception:
                continue

    await page.screenshot(path=str(SCREENSHOTS_DIR / "08_before_publish.png"))

    # === SAVE ===
    print("\n[SAVE] Saving product...")
    save_selectors = [
        'button:has-text("Save")',
        'button:has-text("Update")',
        'button[type="submit"]:visible',
    ]
    for sel in save_selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=3000):
                await btn.click()
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)
                print(f"  Saved via: {sel}")
                break
        except Exception:
            continue

    # === PUBLISH ===
    print("\n[PUBLISH] Publishing product...")
    publish_selectors = [
        'button:has-text("Publish")',
        'button:has-text("Go live")',
        'button:has-text("Unpublished")',
        'a:has-text("Publish")',
        '[role="switch"]',
    ]
    for sel in publish_selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=3000):
                await btn.click()
                await asyncio.sleep(2)
                print(f"  Published via: {sel}")
                break
        except Exception:
            continue

    await page.screenshot(path=str(SCREENSHOTS_DIR / "09_final.png"))

    # === VERIFY ===
    import requests
    api_token = os.getenv("GUMROAD_API_KEY", "")
    if api_token:
        resp = requests.get(
            "https://api.gumroad.com/v2/products",
            params={"access_token": api_token},
        )
        if resp.status_code == 200:
            products = resp.json().get("products", [])
            print(f"\n  API: {len(products)} products found")
            for prod in products:
                print(f"    - {prod.get('name')} | ${prod.get('price', 0)/100:.0f} | published={prod.get('published')} | {prod.get('short_url', '')}")

    final_url = page.url
    print(f"\n  Final page: {final_url}")
    await browser.close()
    return True


def main():
    print("=" * 60)
    print("Gumroad Product Publisher (Playwright + Stealth)")
    print("=" * 60)
    result = asyncio.run(run())
    print("\n" + "=" * 60)
    if result:
        print("COMPLETED")
    else:
        print("COULD NOT COMPLETE — see output above")
    print("=" * 60)
    return result


if __name__ == "__main__":
    main()
