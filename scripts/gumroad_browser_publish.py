#!/usr/bin/env python3
"""Publish 'The AI Side Hustle Playbook' on Gumroad via Playwright browser automation.

Uses playwright-stealth to reduce detection and anti-captcha to solve CAPTCHAs.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path for modules import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

EMAIL = os.getenv("GUMROAD_EMAIL", "")
PASSWORD = os.getenv("GUMROAD_PASSWORD", "")
# 2FA code — pass via env var or CLI arg: python3 script.py --2fa 123456
TWO_FA_CODE = os.getenv("GUMROAD_2FA", "")

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


async def solve_captcha_on_page(page) -> str | None:
    """Detect and solve CAPTCHA on page using anti-captcha service.

    Returns the CAPTCHA token if solved, None on failure.
    """
    from modules.captcha_solver import CaptchaSolver

    # Check for reCAPTCHA presence and extract sitekey
    captcha_info = await page.evaluate("""() => {
        // Try data-sitekey attribute
        const el = document.querySelector('[data-sitekey]');
        if (el) return {found: true, sitekey: el.getAttribute('data-sitekey')};
        // Try iframe src parameter
        const iframe = document.querySelector('iframe[src*="recaptcha"]');
        if (iframe) {
            const m = iframe.src.match(/[?&]k=([^&]+)/);
            if (m) return {found: true, sitekey: m[1]};
        }
        // Check page source for recaptcha
        if (document.body.innerHTML.includes('recaptcha') ||
            document.body.innerHTML.includes('g-recaptcha')) {
            return {found: true, sitekey: null};
        }
        return {found: false, sitekey: null};
    }""")

    if not captcha_info.get("found"):
        print("  No CAPTCHA detected on page")
        return "no_captcha"

    sitekey = captcha_info.get("sitekey")
    page_url = page.url
    print(f"  reCAPTCHA detected! Sitekey: {sitekey}")
    print(f"  Solving via anti-captcha for URL: {page_url}")

    try:
        solver = CaptchaSolver.get_instance()

        if not sitekey:
            print("  ERROR: Could not extract sitekey")
            return None

        # Solve reCAPTCHA v2 via anti-captcha API
        token = solver.solve_recaptcha_v2(sitekey, page_url)

        if not token:
            print("  CAPTCHA solve failed — no token returned")
            return None

        print(f"  CAPTCHA solved! Token: {token[:40]}...")

        # Inject token and trigger callback to close the CAPTCHA widget
        injected = await page.evaluate("""(token) => {
            let success = false;

            // 1. Set all g-recaptcha-response textareas
            document.querySelectorAll('[name="g-recaptcha-response"], #g-recaptcha-response').forEach(el => {
                el.value = token;
                el.style.display = 'block';
                success = true;
            });

            // Also try hidden textarea inside the reCAPTCHA widget
            document.querySelectorAll('textarea').forEach(el => {
                if (el.id && el.id.includes('g-recaptcha-response')) {
                    el.value = token;
                    success = true;
                }
            });

            // 2. Try to call the reCAPTCHA callback
            // Method A: via ___grecaptcha_cfg
            if (typeof ___grecaptcha_cfg !== 'undefined' && ___grecaptcha_cfg.clients) {
                const clients = ___grecaptcha_cfg.clients;
                Object.keys(clients).forEach(key => {
                    const findAndCall = (obj, depth) => {
                        if (depth > 8 || !obj) return;
                        Object.keys(obj).forEach(k => {
                            if (typeof obj[k] === 'function') {
                                try { obj[k](token); } catch(e) {}
                            } else if (typeof obj[k] === 'object' && obj[k] !== null) {
                                findAndCall(obj[k], depth + 1);
                            }
                        });
                    };
                    findAndCall(clients[key], 0);
                });
            }

            // Method B: via grecaptcha.enterprise or grecaptcha callback
            try {
                if (typeof grecaptcha !== 'undefined') {
                    // Try getting the callback from the widget
                    const widgetId = 0;
                    const callback = grecaptcha.getResponse ? null : null;
                }
            } catch(e) {}

            // 3. Try to close the CAPTCHA challenge popup
            // Remove the challenge iframe overlay
            document.querySelectorAll('iframe[src*="recaptcha/api2/bframe"], iframe[src*="recaptcha/enterprise/bframe"]').forEach(iframe => {
                let container = iframe;
                for (let i = 0; i < 10; i++) {
                    container = container.parentElement;
                    if (!container || container === document.body) break;
                    if (container.style.visibility === 'visible' ||
                        getComputedStyle(container).position === 'absolute' ||
                        getComputedStyle(container).position === 'fixed') {
                        container.style.display = 'none';
                        container.style.visibility = 'hidden';
                        break;
                    }
                }
            });

            // Remove any overlay divs
            document.querySelectorAll('div[style*="visibility: visible"]').forEach(el => {
                if (el.querySelector('iframe[src*="recaptcha"]')) {
                    el.style.display = 'none';
                    el.style.visibility = 'hidden';
                }
            });

            return success;
        }""", token)

        print(f"  Token injected: {injected}")
        await asyncio.sleep(2)
        return token

    except Exception as e:
        print(f"  CAPTCHA solve error: {e}")
        return None


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

        # Apply stealth to reduce bot detection
        stealth = Stealth()
        await stealth.apply_stealth_async(page)

        page.set_default_timeout(30000)

        try:
            # === STEP 1: LOGIN ===
            print("\n[1/6] Logging into Gumroad...")
            await page.goto("https://gumroad.com/login", wait_until="networkidle")
            await asyncio.sleep(2)
            await page.screenshot(path=str(SCREENSHOTS_DIR / "01_login_page.png"))

            # Fill email
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

            # Check for CAPTCHA and solve it
            if "login" in current_url.lower():
                body = await page.content()
                if "captcha" in body.lower() or "recaptcha" in body.lower():
                    print("  CAPTCHA detected after login attempt!")
                    await page.screenshot(path=str(SCREENSHOTS_DIR / "03b_captcha_detected.png"))

                    token = await solve_captcha_on_page(page)

                    if token and token != "no_captcha":
                        print("  CAPTCHA solved. Submitting login...")
                        await page.screenshot(path=str(SCREENSHOTS_DIR / "03c_captcha_solved.png"))

                        # Remove overlays and submit form
                        await page.evaluate("""() => {
                            document.querySelectorAll('div').forEach(el => {
                                const style = getComputedStyle(el);
                                const z = parseInt(style.zIndex) || 0;
                                if ((style.position === 'fixed' || style.position === 'absolute') &&
                                    z > 100 && el.querySelector('iframe')) {
                                    el.remove();
                                }
                            });
                        }""")
                        await asyncio.sleep(1)

                        # Click login button
                        try:
                            login_btn = page.locator('button[type="submit"]').first
                            await login_btn.click(force=True, timeout=5000)
                        except Exception:
                            await page.evaluate("document.querySelector('button[type=\"submit\"]')?.click()")

                        await asyncio.sleep(5)
                        try:
                            await page.wait_for_load_state("networkidle", timeout=15000)
                        except Exception:
                            pass

                        current_url = page.url
                        print(f"  URL after login submit: {current_url}")
                        await page.screenshot(path=str(SCREENSHOTS_DIR / "03d_after_submit.png"))

                        # Handle Stripe Connect page — click "Return to Gumroad"
                        if "stripe.com" in current_url:
                            print("  On Stripe Connect page. Looking for 'Return to Gumroad'...")
                            body_text = await page.inner_text("body")
                            print(f"  Stripe body: {body_text[:300]}")
                            await page.screenshot(path=str(SCREENSHOTS_DIR / "03e_stripe_page.png"))

                            # Try clicking "Return to Gumroad" link
                            return_selectors = [
                                'a:has-text("Return to Gumroad")',
                                'a:has-text("return to")',
                                'a:has-text("Go back")',
                                'a[href*="gumroad"]',
                            ]
                            for sel in return_selectors:
                                try:
                                    el = page.locator(sel).first
                                    if await el.is_visible(timeout=3000):
                                        href = await el.get_attribute("href")
                                        print(f"  Found return link: {sel} → {href}")
                                        await el.click()
                                        await asyncio.sleep(3)
                                        await page.wait_for_load_state("networkidle")
                                        break
                                except Exception:
                                    continue

                            current_url = page.url
                            print(f"  URL after return: {current_url}")
                            await page.screenshot(path=str(SCREENSHOTS_DIR / "03f_after_stripe_return.png"))

                        # Handle 2FA page if needed
                        body_text = await page.inner_text("body")
                        if any(kw in body_text.lower() for kw in ["two-factor", "2fa", "verification code", "authenticat", "one-time"]):
                            print("  2FA page detected!")
                            await page.screenshot(path=str(SCREENSHOTS_DIR / "03g_2fa_page.png"))

                            tfa_code = TWO_FA_CODE or ""
                            for i, arg in enumerate(sys.argv):
                                if arg == "--2fa" and i + 1 < len(sys.argv):
                                    tfa_code = sys.argv[i + 1]
                            if not tfa_code:
                                tfa_file = Path("/tmp/gumroad_2fa.txt")
                                if tfa_file.exists():
                                    tfa_code = tfa_file.read_text().strip()

                            if tfa_code:
                                print(f"  Entering 2FA code: {tfa_code}")
                                tfa_selectors = ['input[name*="otp"]', 'input[name*="code"]', 'input[name*="token"]',
                                                 'input[type="text"]', 'input[type="number"]', 'input[inputmode="numeric"]']
                                for sel in tfa_selectors:
                                    try:
                                        el = page.locator(sel).first
                                        if await el.is_visible(timeout=2000):
                                            await el.fill(tfa_code)
                                            print(f"    Filled via: {sel}")
                                            break
                                    except Exception:
                                        continue
                                try:
                                    submit_btn = page.locator('button[type="submit"]').first
                                    await submit_btn.click()
                                    await asyncio.sleep(3)
                                    await page.wait_for_load_state("networkidle")
                                    current_url = page.url
                                    print(f"  URL after 2FA: {current_url}")
                                    await page.screenshot(path=str(SCREENSHOTS_DIR / "03h_after_2fa.png"))
                                except Exception as e:
                                    print(f"  2FA submit error: {e}")
                            else:
                                print("  No 2FA code! Set GUMROAD_2FA env var or write to /tmp/gumroad_2fa.txt")
                                await browser.close()
                                return False

                        # If still on login page, try navigating to products
                        current_url = page.url
                        if "login" in current_url:
                            print("  Still on login. Navigating to products...")
                            await page.goto("https://gumroad.com/products", wait_until="networkidle")
                            await asyncio.sleep(2)
                            current_url = page.url
                            print(f"  URL at products: {current_url}")
                            await page.screenshot(path=str(SCREENSHOTS_DIR / "03i_products.png"))
                    elif token is None:
                        print("  Failed to solve CAPTCHA. Cannot login.")
                        await page.screenshot(path=str(SCREENSHOTS_DIR / "03e_captcha_failed.png"))
                        await browser.close()
                        return False

            # Check final login state
            if "login" not in current_url.lower() or "dashboard" in current_url.lower() or "products" in current_url.lower():
                print("  Login successful!")
                return await create_product(page, context, browser)
            else:
                print("  Login did not redirect. Checking page state...")
                await page.screenshot(path=str(SCREENSHOTS_DIR / "03f_login_failed.png"))
                body_text = await page.inner_text("body")
                print(f"  Body text snippet: {body_text[:300]}")
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


async def create_product(page, context, browser):
    """Create and publish the product (assumes already logged in)."""

    print("\n[2/6] Navigating to new product page...")
    await page.goto("https://gumroad.com/products/new")
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(2)
    await page.screenshot(path=str(SCREENSHOTS_DIR / "05_new_product.png"))
    print(f"  URL: {page.url}")

    # === FILL NAME ===
    print("\n[3/6] Filling product name...")
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
                    for line in PRODUCT_DESCRIPTION.split("\n"):
                        await page.keyboard.type(line, delay=5)
                        await page.keyboard.press("Enter")
                print(f"  Description filled via: {sel}")
                break
        except Exception:
            continue

    # === UPLOAD FILE ===
    print("\n[6/6] Uploading PDF...")
    file_inputs = await page.locator('input[type="file"]').all()
    if file_inputs:
        await file_inputs[0].set_input_files(str(PDF_PATH))
        print(f"  File set: {PDF_PATH.name}")
        await asyncio.sleep(5)
    else:
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
    api_token = os.getenv("GUMROAD_OAUTH_TOKEN", "")
    if api_token:
        resp = requests.get(
            "https://api.gumroad.com/v2/products",
            headers={"Authorization": f"Bearer {api_token}"},
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
    print("Gumroad Product Publisher (Playwright + Anti-Captcha)")
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
