#!/usr/bin/env python3
"""Check if hovering the big cover preview reveals a delete button."""

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

            # First select the old $17 cover (first tab)
            first_tab = page.locator('[role="tablist"][aria-label="Product covers"] [role="tab"]').first
            await first_tab.click()
            await asyncio.sleep(1)

            # Find the big preview image
            big_img = page.locator('[role="tabpanel"] img').first
            if not await big_img.is_visible(timeout=3000):
                # Try finding the large image in the cover section
                big_img = page.locator('img[src*="qhwxpetkogb8m13d"]').last  # Last is likely the big one

            # Get all elements before hover
            before_hover = await page.evaluate("""() => {
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() !== 'Cover') continue;
                    let section = h2;
                    for (let i = 0; i < 3; i++) section = section.parentElement;
                    if (!section) return {};

                    // Count ALL elements
                    const allEls = section.querySelectorAll('*');
                    const visible = Array.from(allEls).filter(el => el.offsetParent !== null);
                    return {
                        total: allEls.length,
                        visible: visible.length,
                    };
                }
                return {};
            }""")
            print(f"[2] Before hover: {before_hover}")

            # Hover over the big preview
            print("[3] Hovering big preview...")
            if await big_img.is_visible(timeout=3000):
                await big_img.hover()
                await asyncio.sleep(1)
            else:
                # Hover over the center of the cover section preview area
                await page.mouse.move(500, 300)
                await asyncio.sleep(1)

            # Check if new elements appeared
            after_hover = await page.evaluate("""() => {
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() !== 'Cover') continue;
                    let section = h2;
                    for (let i = 0; i < 3; i++) section = section.parentElement;
                    if (!section) return {};

                    const allEls = section.querySelectorAll('*');
                    const visible = Array.from(allEls).filter(el => el.offsetParent !== null);

                    // Find anything new that's visible
                    const interactive = [];
                    for (const el of visible) {
                        if (['BUTTON', 'A'].includes(el.tagName) || el.getAttribute('role') === 'button') {
                            const rect = el.getBoundingClientRect();
                            interactive.push({
                                tag: el.tagName,
                                text: el.textContent.trim().substring(0, 30),
                                ariaLabel: el.getAttribute('aria-label') || '',
                                title: el.title || '',
                                hasSvg: !!el.querySelector('svg'),
                                w: Math.round(rect.width),
                                h: Math.round(rect.height),
                                classes: el.className?.toString().substring(0, 60) || '',
                            });
                        }
                    }

                    return {
                        total: allEls.length,
                        visible: visible.length,
                        interactive,
                    };
                }
                return {};
            }""")
            print(f"  After hover: total={after_hover.get('total')}, visible={after_hover.get('visible')}")
            print(f"  Interactive elements:")
            for el in after_hover.get('interactive', []):
                print(f"    {el['tag']} text='{el['text']}' aria='{el['ariaLabel']}' title='{el.get('title','')}' svg={el['hasSvg']} {el['w']}x{el['h']}")

            await page.screenshot(path=str(SCREENSHOTS / "cover_hover_01.png"))

            # Maybe hover needs to be over a specific area — try hovering over each tabpanel
            print("\n[4] Looking for tabpanels...")
            panels = await page.evaluate("""() => {
                const panels = document.querySelectorAll('[role="tabpanel"]');
                return Array.from(panels).map((p, i) => ({
                    idx: i,
                    visible: p.offsetParent !== null,
                    html: p.innerHTML.substring(0, 300),
                    w: Math.round(p.getBoundingClientRect().width),
                    h: Math.round(p.getBoundingClientRect().height),
                }));
            }""")
            for panel in panels:
                print(f"  Panel [{panel['idx']}] vis={panel['visible']} {panel['w']}x{panel['h']}")
                if panel['visible']:
                    print(f"    HTML: {panel['html'][:200]}")

            # Try hovering directly on the tabpanel area
            if panels:
                visible_panel = next((p for p in panels if p['visible']), None)
                if visible_panel:
                    print(f"\n[5] Hovering visible panel...")
                    panel_loc = page.locator('[role="tabpanel"]:visible').first
                    await panel_loc.hover()
                    await asyncio.sleep(1)

                    # Check again
                    after_panel_hover = await page.evaluate("""() => {
                        const h2s = document.querySelectorAll('h2');
                        for (const h2 of h2s) {
                            if (h2.textContent.trim() !== 'Cover') continue;
                            let section = h2;
                            for (let i = 0; i < 3; i++) section = section.parentElement;
                            if (!section) return [];

                            // Find ALL visible interactive elements
                            const btns = section.querySelectorAll('button, [role="button"]');
                            return Array.from(btns).filter(b => b.offsetParent !== null).map(b => ({
                                text: b.textContent.trim().substring(0, 30),
                                ariaLabel: b.getAttribute('aria-label') || '',
                                hasSvg: !!b.querySelector('svg'),
                                w: Math.round(b.getBoundingClientRect().width),
                                classes: b.className?.toString().substring(0, 60) || '',
                            }));
                        }
                        return [];
                    }""")
                    print(f"  Buttons after panel hover: {json.dumps(after_panel_hover)}")

                    await page.screenshot(path=str(SCREENSHOTS / "cover_hover_02_panel.png"))

            # Last resort: check if there's a hidden delete button that becomes visible on CSS hover
            print("\n[6] Checking for CSS hover-only elements...")
            hover_elements = await page.evaluate("""() => {
                // Force show all elements that might be hidden behind CSS :hover
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() !== 'Cover') continue;
                    let section = h2;
                    for (let i = 0; i < 3; i++) section = section.parentElement;
                    if (!section) return [];

                    // Find ALL elements (including invisible) that have delete-like attributes
                    const allEls = section.querySelectorAll('*');
                    const result = [];
                    for (const el of allEls) {
                        const text = el.textContent.trim().toLowerCase();
                        const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                        const title = (el.title || '').toLowerCase();
                        const cls = (el.className?.toString() || '').toLowerCase();

                        if (text.includes('delete') || text.includes('remove') ||
                            aria.includes('delete') || aria.includes('remove') ||
                            title.includes('delete') || title.includes('remove') ||
                            cls.includes('delete') || cls.includes('trash')) {
                            result.push({
                                tag: el.tagName,
                                text: el.textContent.trim().substring(0, 30),
                                ariaLabel: el.getAttribute('aria-label') || '',
                                visible: el.offsetParent !== null,
                                classes: cls.substring(0, 60),
                                display: window.getComputedStyle(el).display,
                                opacity: window.getComputedStyle(el).opacity,
                            });
                        }
                    }

                    // Also look for group/tooltip patterns that might hide a delete button
                    const tooltips = section.querySelectorAll('[class*="group"], [class*="tooltip"]');
                    for (const tt of tooltips) {
                        const btns = tt.querySelectorAll('button');
                        for (const btn of btns) {
                            if (btn.getAttribute('aria-label')?.toLowerCase().includes('delete') ||
                                btn.getAttribute('aria-label')?.toLowerCase().includes('remove')) {
                                result.push({
                                    tag: 'TOOLTIP_BTN',
                                    ariaLabel: btn.getAttribute('aria-label') || '',
                                    visible: btn.offsetParent !== null,
                                    display: window.getComputedStyle(btn).display,
                                });
                            }
                        }
                    }
                    return result;
                }
                return [];
            }""")
            print(f"  Delete-like elements: {json.dumps(hover_elements, indent=2)}")

        except Exception as e:
            print(f"\nERROR: {e}")
            import traceback; traceback.print_exc()
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(run())
