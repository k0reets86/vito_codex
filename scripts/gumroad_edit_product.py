#!/usr/bin/env python3
"""Edit Gumroad product: upload cover, thumbnail, PDF, fill description, save."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SESSION_COOKIE = Path("/tmp/gumroad_cookie.txt").read_text().strip() if Path("/tmp/gumroad_cookie.txt").exists() else ""
PRODUCT_SLUG = "wblqda"
EDIT_URL = f"https://gumroad.com/products/{PRODUCT_SLUG}/edit"

PDF_PATH = Path(__file__).resolve().parent.parent / "output/The_AI_Side_Hustle_Playbook_v2.pdf"
COVER_PATH = Path(__file__).resolve().parent.parent / "output/ai_side_hustle_cover_1280x720.png"
THUMB_PATH = Path(__file__).resolve().parent.parent / "output/ai_side_hustle_thumb_600x600.png"
SCREENSHOTS = Path(__file__).resolve().parent.parent / "output/screenshots"

DESCRIPTION = """Stop watching other people cash in on the AI revolution.

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

Instant PDF download. 5 chapters. ~6,000 words."""

SUMMARY = "Start earning with AI tools in 30 days. 5 chapters, actionable roadmap, zero fluff."


async def run():
    from playwright.async_api import async_playwright

    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    if not SESSION_COOKIE:
        print("ERROR: No cookie"); return False

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 1200},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        await ctx.add_cookies([{
            "name": "_gumroad_app_session", "value": SESSION_COOKIE,
            "domain": ".gumroad.com", "path": "/", "httpOnly": True, "secure": True, "sameSite": "Lax",
        }])
        page = await ctx.new_page()
        page.set_default_timeout(15000)

        try:
            # ===== STEP 1: Load Product tab =====
            print("[1] Loading Product tab...")
            await page.goto(EDIT_URL, wait_until="networkidle")
            await asyncio.sleep(2)
            if "login" in page.url.lower():
                print("  ERROR: Cookie expired"); return False
            print(f"  OK: {page.url}")
            await page.screenshot(path=str(SCREENSHOTS / "e2_01_product_tab.png"), full_page=True)

            # ===== STEP 2: Upload Cover (1280x720) =====
            print("\n[2] Uploading cover image...")
            # File inputs on Product tab:
            #   [0] images (multiple=True) → Cover
            #   [1] audio → skip
            #   [2] images (single) → Thumbnail
            fi = await page.locator('input[type="file"]').all()
            print(f"  File inputs: {len(fi)}")

            # Find the cover file input (images, multiple=True)
            cover_done = False
            for i, f in enumerate(fi):
                attrs = await f.evaluate("el => ({accept: el.accept, multiple: el.multiple})")
                if "image" in (attrs.get("accept") or "") or ".jpg" in (attrs.get("accept") or "") or ".png" in (attrs.get("accept") or ""):
                    if attrs.get("multiple"):
                        await f.set_input_files(str(COVER_PATH))
                        print(f"  Cover → input[{i}] (multiple=True)")
                        cover_done = True
                        await asyncio.sleep(3)
                        break

            if not cover_done:
                # Fallback: click "Upload images or videos" button
                try:
                    btn = page.locator('button:has-text("Upload images")').first
                    if await btn.is_visible(timeout=3000):
                        await btn.click()
                        await asyncio.sleep(1)
                        last_fi = page.locator('input[type="file"]').last
                        await last_fi.set_input_files(str(COVER_PATH))
                        print("  Cover via Upload images button")
                        cover_done = True
                        await asyncio.sleep(3)
                except Exception as e:
                    print(f"  Cover fallback failed: {e}")

            await page.screenshot(path=str(SCREENSHOTS / "e2_02_cover_uploaded.png"), full_page=True)

            # ===== STEP 3: Upload Thumbnail (600x600) =====
            print("\n[3] Uploading thumbnail...")
            # Scroll down to Thumbnail section
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1)

            fi = await page.locator('input[type="file"]').all()
            thumb_done = False
            for i, f in enumerate(fi):
                attrs = await f.evaluate("el => ({accept: el.accept, multiple: el.multiple})")
                if (".jpg" in (attrs.get("accept") or "") or ".png" in (attrs.get("accept") or "")):
                    if not attrs.get("multiple"):
                        await f.set_input_files(str(THUMB_PATH))
                        print(f"  Thumbnail → input[{i}] (single image)")
                        thumb_done = True
                        await asyncio.sleep(3)
                        break

            await page.screenshot(path=str(SCREENSHOTS / "e2_03_thumb_uploaded.png"), full_page=True)

            # ===== STEP 4: Fill Description =====
            print("\n[4] Filling description...")
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)

            desc_done = False
            for sel in ['[contenteditable="true"]', '.ProseMirror', '[role="textbox"]', 'textarea']:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=3000):
                        await el.click()
                        await asyncio.sleep(0.3)
                        # Select all and delete existing content
                        await page.keyboard.press("Control+a")
                        await page.keyboard.press("Backspace")
                        await asyncio.sleep(0.2)
                        # Type new description
                        for line in DESCRIPTION.strip().split("\n"):
                            if line.strip():
                                await page.keyboard.type(line, delay=1)
                            await page.keyboard.press("Enter")
                        print(f"  Description via: {sel}")
                        desc_done = True
                        break
                except Exception:
                    continue

            # ===== STEP 5: Fill Summary =====
            print("\n[5] Filling summary...")
            for sel in ['input[placeholder*="You\'ll get"]', 'input[placeholder*="summary" i]']:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=3000):
                        await el.clear()
                        await el.fill(SUMMARY)
                        print(f"  Summary via: {sel}")
                        break
                except Exception:
                    continue

            # ===== STEP 6: Save Product tab =====
            print("\n[6] Saving Product tab...")
            save_btn = page.locator('button:has-text("Save")').first
            try:
                if await save_btn.is_visible(timeout=3000):
                    await save_btn.click()
                    await asyncio.sleep(3)
                    print("  Saved!")
            except Exception as e:
                print(f"  Save error: {e}")

            await page.screenshot(path=str(SCREENSHOTS / "e2_04_saved_product.png"), full_page=True)

            # ===== STEP 7: Go to Content tab, upload PDF =====
            print("\n[7] Switching to Content tab...")
            content_tab = page.locator('button:has-text("Content"), a:has-text("Content")').first
            try:
                await content_tab.click()
                await asyncio.sleep(3)
                await page.wait_for_load_state("networkidle")
            except Exception:
                # Direct navigation
                await page.goto(f"{EDIT_URL}/content", wait_until="networkidle")
                await asyncio.sleep(2)

            print(f"  URL: {page.url}")
            await page.screenshot(path=str(SCREENSHOTS / "e2_05_content_tab.png"), full_page=True)

            # Find "Upload your files" or "Upload files" on Content tab
            print("\n[8] Uploading PDF on Content tab...")
            pdf_done = False

            # Try clicking "Upload your files" button
            for sel in ['button:has-text("Upload your files")', 'button:has-text("Upload files")',
                        'a:has-text("Upload your files")', 'button:has-text("Upload")']:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=3000):
                        await el.click()
                        await asyncio.sleep(2)
                        # Check for file input that appeared
                        fi_all = await page.locator('input[type="file"]').all()
                        for f in fi_all:
                            accept = await f.evaluate("el => el.accept || ''")
                            # Content file input should accept any file or PDF
                            if "image" not in accept and "audio" not in accept:
                                await f.set_input_files(str(PDF_PATH))
                                print(f"  PDF uploaded via: {sel}")
                                pdf_done = True
                                await asyncio.sleep(5)
                                break
                            elif accept == "":
                                # No accept filter = accepts all
                                await f.set_input_files(str(PDF_PATH))
                                print(f"  PDF uploaded via: {sel} (no accept filter)")
                                pdf_done = True
                                await asyncio.sleep(5)
                                break
                        if pdf_done:
                            break
                except Exception:
                    continue

            # Try toolbar "Upload files" button in content editor
            if not pdf_done:
                try:
                    toolbar_upload = page.locator('button:has-text("Upload files")').first
                    if await toolbar_upload.is_visible(timeout=3000):
                        await toolbar_upload.click()
                        await asyncio.sleep(2)
                        fi_all = await page.locator('input[type="file"]').all()
                        if fi_all:
                            await fi_all[-1].set_input_files(str(PDF_PATH))
                            print("  PDF via toolbar Upload files")
                            pdf_done = True
                            await asyncio.sleep(5)
                except Exception:
                    pass

            # Last resort: any file input without image/audio filter
            if not pdf_done:
                fi_all = await page.locator('input[type="file"]').all()
                for f in fi_all:
                    accept = await f.evaluate("el => el.accept || ''")
                    if accept == "" or ".pdf" in accept:
                        await f.set_input_files(str(PDF_PATH))
                        print("  PDF via generic file input")
                        pdf_done = True
                        await asyncio.sleep(5)
                        break

            await page.screenshot(path=str(SCREENSHOTS / "e2_06_pdf_uploaded.png"), full_page=True)

            # Save content
            print("\n[9] Saving Content...")
            try:
                save_btn = page.locator('button:has-text("Save")').first
                if await save_btn.is_visible(timeout=3000):
                    await save_btn.click()
                    await asyncio.sleep(3)
                    print("  Content saved!")
            except Exception:
                pass

            await page.screenshot(path=str(SCREENSHOTS / "e2_07_final.png"), full_page=True)

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
                        print(f"  Price: {prod.get('formatted_price')}")
                        print(f"  Published: {prod.get('published')}")
                        print(f"  URL: {prod.get('short_url')}")
                        print(f"  Thumbnail: {prod.get('thumbnail_url', 'none')}")
                        print(f"  Files: {prod.get('file_info', {})}")
                        print(f"  Summary: {prod.get('custom_summary', '')}")
                        desc = prod.get('description', '')
                        print(f"  Description: {desc[:100]}...")

        except Exception as e:
            print(f"\nERROR: {e}")
            import traceback; traceback.print_exc()
            try:
                await page.screenshot(path=str(SCREENSHOTS / "e2_99_error.png"), full_page=True)
            except Exception:
                pass
        finally:
            await browser.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Gumroad Product Editor v2")
    print("=" * 60)
    asyncio.run(run())
