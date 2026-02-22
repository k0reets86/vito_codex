#!/usr/bin/env python3
"""Upload cover image to Gumroad Cover section using file chooser."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

COOKIE = Path("/tmp/gumroad_cookie.txt").read_text().strip()
COVER = str(Path(__file__).resolve().parent.parent / "output/ai_side_hustle_cover_1280x720.png")
SHOTS = str(Path(__file__).resolve().parent.parent / "output/screenshots")


async def run():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        br = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = await br.new_context(
            viewport={"width": 1280, "height": 1400},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        )
        await ctx.add_cookies([{
            "name": "_gumroad_app_session", "value": COOKIE,
            "domain": ".gumroad.com", "path": "/", "httpOnly": True,
            "secure": True, "sameSite": "Lax",
        }])
        page = await ctx.new_page()
        page.set_default_timeout(20000)

        await page.goto("https://gumroad.com/products/wblqda/edit", wait_until="networkidle")
        await asyncio.sleep(2)
        if "login" in page.url:
            print("COOKIE EXPIRED")
            await br.close()
            return
        print(f"Loaded: {page.url}")

        # Scroll to Cover section using JS
        found = await page.evaluate("""() => {
            const all = document.querySelectorAll('h2, h3, span, div, label, p');
            for (const el of all) {
                if (el.textContent.trim() === 'Cover' && el.offsetParent !== null
                    && el.getBoundingClientRect().height < 50) {
                    el.scrollIntoView({block: 'center'});
                    return true;
                }
            }
            return false;
        }""")
        print(f"Scrolled to Cover: {found}")
        await asyncio.sleep(1)
        await page.screenshot(path=f"{SHOTS}/cover_01_scrolled.png")

        # Find and click the upload button
        upload_btn = page.locator('button:has-text("Upload images or videos")').first
        is_visible = await upload_btn.is_visible(timeout=5000)
        print(f"'Upload images or videos' visible: {is_visible}")

        if is_visible:
            # Step 1: Click to open dropdown menu
            await upload_btn.click()
            await asyncio.sleep(2)
            await page.screenshot(path=f"{SHOTS}/cover_01b_menu.png")

            # Step 2: Click "Computer files" in the menu
            comp_btn = page.locator('button:has-text("Computer files")').first
            comp_visible = await comp_btn.is_visible(timeout=5000)
            print(f"'Computer files' visible after click: {comp_visible}")

            if comp_visible:
                async with page.expect_file_chooser(timeout=15000) as fc_info:
                    await comp_btn.click()
                chooser = await fc_info.value
                await chooser.set_files(COVER)
                print("Cover uploaded via Computer files!")
                await asyncio.sleep(6)
            else:
                # Maybe the upload button directly triggers file input
                # Try finding hidden file input near Cover section
                fi_all = await page.locator('input[type="file"]').all()
                print(f"File inputs on page: {len(fi_all)}")
                for i, fi in enumerate(fi_all):
                    attrs = await fi.evaluate("el => ({accept: el.accept, multiple: el.multiple})")
                    print(f"  [{i}] {attrs}")
                # Cover input is [2] — the one that accepts video formats (.mov, .mp4)
                # Description input is [0] — images only (.jpg, .png, .webp)
                for fi in fi_all:
                    accept = await fi.evaluate("el => el.accept || ''")
                    if ".mov" in accept or ".mp4" in accept:
                        await fi.set_input_files(COVER)
                        print("Cover uploaded via COVER file input (video-accepting)!")
                        await asyncio.sleep(6)
                        break
        else:
            print("Upload button not found")

        await page.screenshot(path=f"{SHOTS}/cover_02_uploaded.png", full_page=True)

        # Save
        save = page.locator('button:has-text("Save")').first
        if await save.is_visible(timeout=3000):
            await save.click()
            await asyncio.sleep(4)
            print("Saved!")

        await page.screenshot(path=f"{SHOTS}/cover_03_saved.png", full_page=True)

        # Verify
        import requests
        token = os.getenv("GUMROAD_OAUTH_TOKEN", "")
        r = requests.get("https://api.gumroad.com/v2/products",
                         headers={"Authorization": f"Bearer {token}"})
        prod = r.json()["products"][0]
        print(f"Price: {prod['formatted_price']}")
        print(f"Published: {prod['published']}")
        print(f"Thumbnail: {prod.get('thumbnail_url', 'none')}")
        # Check if cover exists by looking at preview
        print(f"Preview URL: {prod.get('preview_url', 'none')}")

        await br.close()


asyncio.run(run())
