#!/usr/bin/env python3
"""Debug: Full DOM of Cover section to understand how to select/delete covers."""

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

            # Get FULL structure of Cover section
            cover_dom = await page.evaluate("""() => {
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() !== 'Cover') continue;
                    let section = h2;
                    for (let i = 0; i < 3; i++) section = section.parentElement;
                    if (!section) return null;

                    function describe(el, depth=0, maxDepth=6) {
                        if (!el || depth > maxDepth) return null;
                        const rect = el.getBoundingClientRect();
                        const node = {
                            tag: el.tagName.toLowerCase(),
                            vis: el.offsetParent !== null || el.tagName === 'IMG',
                            w: Math.round(rect.width),
                            h: Math.round(rect.height),
                        };
                        if (el.className && typeof el.className === 'string')
                            node.cls = el.className.substring(0, 60);
                        if (el.id) node.id = el.id;
                        if (el.getAttribute('role')) node.role = el.getAttribute('role');
                        if (el.tagName === 'IMG') node.src = el.src.substring(el.src.lastIndexOf('/') + 1, el.src.lastIndexOf('/') + 20);
                        if (el.tagName === 'BUTTON') {
                            node.text = el.textContent.trim().substring(0, 20);
                            node.hasSvg = !!el.querySelector('svg');
                            node.hasImg = !!el.querySelector('img');
                        }
                        if (el.tagName === 'INPUT') {
                            node.type = el.type;
                            node.accept = el.accept;
                        }
                        if (el.getAttribute('aria-label'))
                            node.ariaLabel = el.getAttribute('aria-label');

                        const children = [];
                        for (const child of el.children) {
                            const c = describe(child, depth + 1, maxDepth);
                            if (c) children.push(c);
                        }
                        if (children.length > 0) node.children = children;
                        return node;
                    }

                    return describe(section);
                }
                return null;
            }""")

            print("[2] Cover section DOM:")
            print(json.dumps(cover_dom, indent=2)[:5000])

            await page.screenshot(path=str(SCREENSHOTS / "cover_dom_01.png"))

            # Also check: are there clickable elements for each cover image?
            # Maybe they're not buttons but divs or other elements
            clickable_covers = await page.evaluate("""() => {
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() !== 'Cover') continue;
                    let section = h2;
                    for (let i = 0; i < 3; i++) section = section.parentElement;
                    if (!section) return null;

                    // Get all elements that contain exactly one img
                    const containers = [];
                    const allElements = section.querySelectorAll('*');
                    for (const el of allElements) {
                        const directImgs = el.querySelectorAll(':scope > img');
                        if (directImgs.length === 1 && el.children.length <= 2) {
                            const img = directImgs[0];
                            const rect = el.getBoundingClientRect();
                            if (rect.width > 30 && rect.width < 100) {
                                // Likely a thumbnail
                                el.setAttribute('data-thumb-container', containers.length.toString());
                                containers.push({
                                    idx: containers.length,
                                    tag: el.tagName,
                                    w: Math.round(rect.width),
                                    h: Math.round(rect.height),
                                    imgSrc: img.src.substring(img.src.lastIndexOf('/') + 1).substring(0, 20),
                                    cursor: window.getComputedStyle(el).cursor,
                                    role: el.getAttribute('role') || '',
                                    tabIndex: el.tabIndex,
                                });
                            }
                        }
                    }
                    return containers;
                }
                return null;
            }""")
            print(f"\n[3] Clickable cover containers: {json.dumps(clickable_covers, indent=2)}")

        except Exception as e:
            print(f"\nERROR: {e}")
            import traceback; traceback.print_exc()
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(run())
