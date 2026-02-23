#!/usr/bin/env python3
"""Find all cover thumbnails, identify the $17 one, delete it."""

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SESSION_COOKIE = Path("/tmp/gumroad_cookie.txt").read_text().strip() if Path("/tmp/gumroad_cookie.txt").exists() else ""
SCREENSHOTS = Path(__file__).resolve().parent.parent / "output/screenshots"
SCREENSHOTS.mkdir(parents=True, exist_ok=True)


async def run():
    from playwright.async_api import async_playwright

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
            print("[1] Loading Product tab...")
            await page.goto("https://gumroad.com/products/wblqda/edit", wait_until="networkidle")
            await asyncio.sleep(3)
            if "login" in page.url.lower():
                print("COOKIE EXPIRED"); return

            # Scroll to Cover
            await page.evaluate("""() => {
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() === 'Cover') {
                        h2.scrollIntoView({behavior: 'instant', block: 'start'});
                        return;
                    }
                }
            }""")
            await asyncio.sleep(1)

            # Find ALL cover thumbnails
            thumbs = await page.evaluate("""() => {
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() !== 'Cover') continue;
                    let section = h2;
                    for (let i = 0; i < 3; i++) section = section.parentElement;
                    if (!section) return [];

                    // Find all buttons with images (these are cover thumbnails)
                    const btns = section.querySelectorAll('button');
                    const result = [];
                    let idx = 0;
                    for (const btn of btns) {
                        if (btn.offsetParent !== null) {
                            const img = btn.querySelector('img');
                            const rect = btn.getBoundingClientRect();
                            if (img) {
                                btn.setAttribute('data-cover-idx', idx.toString());
                                result.push({
                                    idx,
                                    src: img.src,
                                    w: Math.round(rect.width),
                                    h: Math.round(rect.height),
                                    x: Math.round(rect.x),
                                    y: Math.round(rect.y),
                                });
                            }
                            idx++;
                        }
                    }
                    return result;
                }
                return [];
            }""")

            print(f"[2] Cover thumbnails ({len(thumbs)}):")
            for t in thumbs:
                print(f"    [{t['idx']}] {t['w']}x{t['h']} src={t['src'][:80]}")

            await page.screenshot(path=str(SCREENSHOTS / "delete_old_01_thumbs.png"))

            # Download each thumbnail to identify which one has $17
            import requests as req
            for i, t in enumerate(thumbs):
                url = t['src']
                if url.startswith('/'):
                    url = 'https://gumroad.com' + url
                try:
                    r = req.get(url, timeout=10)
                    fpath = str(SCREENSHOTS / f"delete_old_thumb_{i}.png")
                    with open(fpath, 'wb') as f:
                        f.write(r.content)
                    print(f"    Saved thumb {i}: {fpath} ({len(r.content)} bytes)")
                except Exception as e:
                    print(f"    Failed to download thumb {i}: {e}")

            if len(thumbs) == 0:
                print("  No thumbnails found! Maybe covers are showing differently.")
                # Check the big preview area
                big_preview = await page.evaluate("""() => {
                    const h2s = document.querySelectorAll('h2');
                    for (const h2 of h2s) {
                        if (h2.textContent.trim() !== 'Cover') continue;
                        let section = h2;
                        for (let i = 0; i < 3; i++) section = section.parentElement;
                        if (!section) return null;
                        // Get all images in section
                        const imgs = section.querySelectorAll('img');
                        return Array.from(imgs).map(img => ({
                            src: img.src.substring(0, 100),
                            w: img.naturalWidth,
                            h: img.naturalHeight,
                        }));
                    }
                    return null;
                }""")
                print(f"  Big preview images: {json.dumps(big_preview)}")

            # Now let's try to delete covers one by one
            # First, click each thumbnail to select it, then find the delete button
            for t in thumbs:
                print(f"\n[3] Testing thumbnail [{t['idx']}]...")
                btn_loc = page.locator(f'[data-cover-idx="{t["idx"]}"]').first

                # Click to select
                await btn_loc.click()
                await asyncio.sleep(1)

                # Hover to show delete button
                await btn_loc.hover()
                await asyncio.sleep(1)

                # Screenshot
                await page.screenshot(path=str(SCREENSHOTS / f"delete_old_02_hover_{t['idx']}.png"))

                # Check for any new buttons or overlays that appeared
                overlay = await page.evaluate(f"""() => {{
                    const h2s = document.querySelectorAll('h2');
                    for (const h2 of h2s) {{
                        if (h2.textContent.trim() !== 'Cover') continue;
                        let section = h2;
                        for (let i = 0; i < 3; i++) section = section.parentElement;
                        if (!section) return null;

                        // Look for all visible buttons with SVG icons (delete buttons)
                        const btns = section.querySelectorAll('button');
                        const result = [];
                        for (const btn of btns) {{
                            if (btn.offsetParent === null) continue;
                            const svg = btn.querySelector('svg');
                            const img = btn.querySelector('img');
                            const rect = btn.getBoundingClientRect();
                            if (svg && !img) {{
                                btn.setAttribute('data-svg-btn', result.length.toString());
                                result.push({{
                                    text: btn.textContent.trim(),
                                    w: Math.round(rect.width),
                                    h: Math.round(rect.height),
                                    x: Math.round(rect.x),
                                    y: Math.round(rect.y),
                                    title: btn.title || '',
                                    ariaLabel: btn.getAttribute('aria-label') || '',
                                    svgPaths: Array.from(btn.querySelectorAll('svg path')).length,
                                }});
                            }}
                        }}
                        return result;
                    }}
                    return null;
                }}""")
                print(f"  SVG buttons after hover: {json.dumps(overlay)}")

                # Remove markers
                await page.evaluate("() => document.querySelectorAll('[data-svg-btn]').forEach(e => e.removeAttribute('data-svg-btn'))")

        except Exception as e:
            print(f"\nERROR: {e}")
            import traceback; traceback.print_exc()
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(run())
