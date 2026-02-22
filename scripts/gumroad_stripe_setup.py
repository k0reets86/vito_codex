#!/usr/bin/env python3
"""Complete Stripe Connect onboarding for Gumroad account via Playwright.

Gumroad forces Stripe Connect for all new accounts before any functionality works.
This script: login → Stripe Connect → fill email → continue → see what's next.
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

EMAIL = os.getenv("GUMROAD_EMAIL", "")
PASSWORD = os.getenv("GUMROAD_PASSWORD", "")
SCREENSHOTS_DIR = Path(__file__).resolve().parent.parent / "output/screenshots"


async def solve_captcha_on_page(page):
    """Solve reCAPTCHA on page via anti-captcha."""
    from modules.captcha_solver import CaptchaSolver

    captcha_info = await page.evaluate("""() => {
        const el = document.querySelector('[data-sitekey]');
        if (el) return {found: true, sitekey: el.getAttribute('data-sitekey')};
        const iframe = document.querySelector('iframe[src*="recaptcha"]');
        if (iframe) {
            const m = iframe.src.match(/[?&]k=([^&]+)/);
            if (m) return {found: true, sitekey: m[1]};
        }
        if (document.body.innerHTML.includes('recaptcha')) return {found: true, sitekey: null};
        return {found: false, sitekey: null};
    }""")

    if not captcha_info.get("found"):
        print("  No CAPTCHA on page")
        return "no_captcha"

    sitekey = captcha_info.get("sitekey")
    if not sitekey:
        print("  CAPTCHA found but no sitekey")
        return None

    print(f"  Solving CAPTCHA (sitekey: {sitekey[:20]}...)")
    solver = CaptchaSolver.get_instance()
    token = solver.solve_recaptcha_v2(sitekey, page.url)
    if not token:
        print("  CAPTCHA solve failed")
        return None

    print(f"  CAPTCHA solved! Injecting token...")
    await page.evaluate("""(token) => {
        document.querySelectorAll('[name="g-recaptcha-response"], #g-recaptcha-response, textarea[id*="g-recaptcha"]').forEach(el => {
            el.value = token;
        });
        if (typeof ___grecaptcha_cfg !== 'undefined' && ___grecaptcha_cfg.clients) {
            Object.keys(___grecaptcha_cfg.clients).forEach(key => {
                const walk = (obj, d) => {
                    if (d > 8 || !obj) return;
                    Object.keys(obj).forEach(k => {
                        if (typeof obj[k] === 'function') { try { obj[k](token); } catch(e) {} }
                        else if (typeof obj[k] === 'object' && obj[k]) walk(obj[k], d+1);
                    });
                };
                walk(___grecaptcha_cfg.clients[key], 0);
            });
        }
        // Remove overlay
        document.querySelectorAll('div').forEach(el => {
            const s = getComputedStyle(el);
            if ((s.position==='fixed'||s.position==='absolute') && (parseInt(s.zIndex)||0)>100 && el.querySelector('iframe'))
                el.remove();
        });
    }""", token)
    await asyncio.sleep(2)
    return token


async def run():
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                   "--disable-blink-features=AutomationControlled", "--window-size=1280,900"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US", timezone_id="America/New_York",
        )
        page = await context.new_page()
        stealth = Stealth()
        await stealth.apply_stealth_async(page)
        page.set_default_timeout(30000)

        try:
            # === LOGIN ===
            print("[1] Logging in...")
            await page.goto("https://gumroad.com/login", wait_until="networkidle")
            await asyncio.sleep(2)

            await page.locator('input[type="email"]').first.type(EMAIL, delay=40)
            await asyncio.sleep(0.3)
            await page.locator('input[type="password"]').first.type(PASSWORD, delay=35)
            await asyncio.sleep(0.5)

            await page.locator('button[type="submit"]').first.click()
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)

            url = page.url
            print(f"  URL: {url}")
            await page.screenshot(path=str(SCREENSHOTS_DIR / "stripe_01_after_login.png"))

            # Solve CAPTCHA if needed
            if "login" in url.lower():
                body = await page.content()
                if "captcha" in body.lower() or "recaptcha" in body.lower():
                    print("  CAPTCHA detected, solving...")
                    token = await solve_captcha_on_page(page)
                    if token and token != "no_captcha":
                        # Remove overlays and submit
                        await page.evaluate("""() => {
                            document.querySelectorAll('div').forEach(el => {
                                const s = getComputedStyle(el);
                                if ((s.position==='fixed'||s.position==='absolute') && (parseInt(s.zIndex)||0)>100 && el.querySelector('iframe'))
                                    el.remove();
                            });
                        }""")
                        await asyncio.sleep(1)
                        try:
                            await page.locator('button[type="submit"]').first.click(force=True, timeout=5000)
                        except Exception:
                            await page.evaluate("document.querySelector('button[type=\"submit\"]')?.click()")

                        await asyncio.sleep(5)
                        try:
                            await page.wait_for_load_state("networkidle", timeout=15000)
                        except Exception:
                            pass

                        url = page.url
                        print(f"  URL after submit: {url}")
                        await page.screenshot(path=str(SCREENSHOTS_DIR / "stripe_02_after_captcha.png"))

            # === STRIPE CONNECT ===
            if "stripe.com" in url:
                print(f"\n[2] On Stripe Connect page")
                await page.screenshot(path=str(SCREENSHOTS_DIR / "stripe_03_stripe_page.png"))

                # Fill email
                email_input = page.locator('input[type="email"], input[name="email"]').first
                try:
                    if await email_input.is_visible(timeout=5000):
                        await email_input.fill(EMAIL)
                        print(f"  Filled email: {EMAIL}")
                        await asyncio.sleep(1)
                        await page.screenshot(path=str(SCREENSHOTS_DIR / "stripe_04_email_filled.png"))

                        # Click Continue — try multiple selectors
                        clicked = False
                        for sel in [
                            'button:has-text("Continue")',
                            'a:has-text("Continue")',
                            '[data-test="continue-button"]',
                            'button[type="submit"]',
                            '*:has-text("Continue") >> visible=true',
                        ]:
                            try:
                                el = page.locator(sel).first
                                if await el.is_visible(timeout=3000):
                                    await el.click(force=True)
                                    clicked = True
                                    print(f"  Clicked Continue via: {sel}")
                                    break
                            except Exception:
                                continue
                        if not clicked:
                            # JS fallback
                            await page.evaluate("""() => {
                                const els = [...document.querySelectorAll('button, a, [role="button"]')];
                                const btn = els.find(el => el.textContent.trim() === 'Continue');
                                if (btn) btn.click();
                            }""")
                            print("  Clicked Continue via JS fallback")

                        await asyncio.sleep(5)
                        try:
                            await page.wait_for_load_state("networkidle", timeout=15000)
                        except Exception:
                            pass

                        url = page.url
                        print(f"  URL after Continue: {url}")
                        await page.screenshot(path=str(SCREENSHOTS_DIR / "stripe_05_after_continue.png"))

                        # Dump page content to see what's next
                        body_text = await page.inner_text("body")
                        print(f"\n  Page content (first 1000 chars):")
                        print(f"  {body_text[:1000]}")

                        # Check all visible inputs
                        inputs = await page.locator("input:visible, select:visible").all()
                        print(f"\n  Visible form fields: {len(inputs)}")
                        for i, inp in enumerate(inputs):
                            attrs = await inp.evaluate("""el => ({
                                tag: el.tagName, type: el.type, name: el.name,
                                placeholder: el.placeholder, id: el.id,
                                label: el.labels?.[0]?.textContent || ''
                            })""")
                            print(f"    [{i}] {attrs}")

                except Exception as e:
                    print(f"  Email input error: {e}")
                    # Maybe it's a different Stripe page layout
                    body_text = await page.inner_text("body")
                    print(f"  Page text: {body_text[:500]}")

            elif "gumroad.com" in url and "login" not in url:
                print(f"\n[2] Already on Gumroad! URL: {url}")
                print("  Stripe Connect might already be done!")

            else:
                print(f"\n[2] Unexpected URL: {url}")
                body_text = await page.inner_text("body")
                print(f"  Page text: {body_text[:500]}")

            await page.screenshot(path=str(SCREENSHOTS_DIR / "stripe_99_final.png"))

        except Exception as e:
            print(f"\nERROR: {e}")
            try:
                await page.screenshot(path=str(SCREENSHOTS_DIR / "stripe_99_error.png"))
            except Exception:
                pass
        finally:
            await browser.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Gumroad Stripe Connect Setup")
    print("=" * 60)
    asyncio.run(run())
