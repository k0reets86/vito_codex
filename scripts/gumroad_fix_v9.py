#!/usr/bin/env python3
"""V9: Delete old cover (first thumbnail) + Tags via server-side autocomplete dropdown."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SESSION_COOKIE = Path("/tmp/gumroad_cookie.txt").read_text().strip() if Path("/tmp/gumroad_cookie.txt").exists() else ""
SCREENSHOTS = Path(__file__).resolve().parent.parent / "output/screenshots"
SCREENSHOTS.mkdir(parents=True, exist_ok=True)

# Tags to search for in Gumroad's autocomplete
TAG_SEARCHES = ["ai", "passive income", "chatgpt", "ebook", "side hustle", "money", "artificial intelligence"]


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
            # ==========================================
            # STEP 1: DELETE OLD COVER
            # ==========================================
            print("[1] Loading Product tab...")
            await page.goto("https://gumroad.com/products/wblqda/edit", wait_until="networkidle")
            await asyncio.sleep(3)
            if "login" in page.url.lower():
                print("COOKIE EXPIRED"); return

            print("[2] Deleting old cover (first thumbnail)...")

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

            # Find all thumbnail buttons in Cover section
            thumbs = await page.evaluate("""() => {
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {
                    if (h2.textContent.trim() !== 'Cover') continue;
                    let el = h2;
                    for (let i = 0; i < 3; i++) el = el.parentElement;
                    if (!el) return [];

                    const btns = el.querySelectorAll('button');
                    const result = [];
                    let idx = 0;
                    for (const btn of btns) {
                        if (btn.offsetParent !== null) {
                            const img = btn.querySelector('img');
                            const rect = btn.getBoundingClientRect();
                            result.push({
                                idx,
                                hasImg: !!img,
                                src: img ? img.src.substring(0, 80) : '',
                                w: rect.width,
                                h: rect.height,
                                text: btn.textContent.trim().substring(0, 20),
                            });
                            btn.setAttribute('data-cover-btn-' + idx, 'true');
                            idx++;
                        }
                    }
                    return result;
                }
                return [];
            }""")
            print(f"  Cover buttons ({len(thumbs)}):")
            for t in thumbs:
                print(f"    [{t['idx']}] hasImg={t['hasImg']} {t['w']:.0f}x{t['h']:.0f} text='{t['text']}' src={t['src'][:50]}")

            # Click on the FIRST thumbnail (old cover with $17) to select it
            deleted = False
            if len(thumbs) >= 2:
                # First thumbnail = old cover, we want to delete it
                first_thumb = page.locator('[data-cover-btn-0="true"]').first
                await first_thumb.click()
                await asyncio.sleep(1)
                await page.screenshot(path=str(SCREENSHOTS / "v9_01_thumb_clicked.png"))

                # Check if clicking the first thumb selected it and showed the big preview
                # The big preview should be showing the old cover now
                # Look for a delete/remove icon on or near the selected thumbnail

                # Hover over the first thumbnail
                await first_thumb.hover()
                await asyncio.sleep(1)

                # Check for delete button overlaying the thumbnail
                del_btn = await page.evaluate("""() => {
                    const h2s = document.querySelectorAll('h2');
                    for (const h2 of h2s) {
                        if (h2.textContent.trim() !== 'Cover') continue;
                        let el = h2;
                        for (let i = 0; i < 3; i++) el = el.parentElement;
                        if (!el) return null;

                        // After clicking/hovering thumb, a delete button might appear
                        const btns = el.querySelectorAll('button');
                        const result = [];
                        for (const btn of btns) {
                            if (btn.offsetParent !== null) {
                                result.push({
                                    text: btn.textContent.trim().substring(0, 30),
                                    hasImg: !!btn.querySelector('img'),
                                    hasSvg: !!btn.querySelector('svg'),
                                    w: btn.getBoundingClientRect().width,
                                    h: btn.getBoundingClientRect().height,
                                    x: btn.getBoundingClientRect().x,
                                    y: btn.getBoundingClientRect().y,
                                    title: btn.title || '',
                                    ariaLabel: btn.getAttribute('aria-label') || '',
                                });
                            }
                        }
                        return result;
                    }
                    return null;
                }""")
                print(f"  Buttons after hover:")
                if del_btn:
                    for b in del_btn:
                        print(f"    text='{b['text']}' svg={b['hasSvg']} img={b['hasImg']} {b['w']:.0f}x{b['h']:.0f} aria='{b['ariaLabel']}' title='{b['title']}'")

                await page.screenshot(path=str(SCREENSHOTS / "v9_02_hover.png"))

                # Look for a small button with SVG (trash/X icon) overlapping the thumbnail
                # It should be positioned near the top of the thumbnail area
                if del_btn:
                    for b in del_btn:
                        if b['hasSvg'] and not b['hasImg'] and b['text'] != '+' and b['w'] < 50:
                            # This might be a delete button
                            # Click it via evaluate to bypass overlays
                            del_result = await page.evaluate("""() => {
                                const h2s = document.querySelectorAll('h2');
                                for (const h2 of h2s) {
                                    if (h2.textContent.trim() !== 'Cover') continue;
                                    let el = h2;
                                    for (let i = 0; i < 3; i++) el = el.parentElement;
                                    if (!el) return false;
                                    const btns = el.querySelectorAll('button');
                                    for (const btn of btns) {
                                        if (btn.offsetParent !== null && btn.querySelector('svg')
                                            && !btn.querySelector('img') && btn.textContent.trim() !== '+'
                                            && btn.getBoundingClientRect().width < 50) {
                                            btn.click();
                                            return true;
                                        }
                                    }
                                    return false;
                                }
                                return false;
                            }""")
                            if del_result:
                                print("  Clicked delete button!")
                                deleted = True
                                await asyncio.sleep(2)
                            break

                if not deleted:
                    # Maybe there's no delete button on hover. Try right-click or keyboard delete
                    print("  No delete button found. Trying keyboard Delete...")
                    await first_thumb.click()
                    await asyncio.sleep(0.5)
                    await page.keyboard.press("Delete")
                    await asyncio.sleep(1)
                    await page.keyboard.press("Backspace")
                    await asyncio.sleep(1)

                    # Check if thumbnail was removed
                    thumbs_after = await page.evaluate("""() => {
                        const h2s = document.querySelectorAll('h2');
                        for (const h2 of h2s) {
                            if (h2.textContent.trim() !== 'Cover') continue;
                            let el = h2;
                            for (let i = 0; i < 3; i++) el = el.parentElement;
                            if (!el) return 0;
                            return el.querySelectorAll('button img').length;
                        }
                        return -1;
                    }""")
                    print(f"  Thumbnails after Delete/Backspace: {thumbs_after}")

            await page.screenshot(path=str(SCREENSHOTS / "v9_03_after_delete.png"))

            # Save
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)
            save = page.locator('button:has-text("Save changes")').first
            if await save.is_visible(timeout=3000):
                await save.click()
                await asyncio.sleep(4)
                print("  Saved!")

            # ==========================================
            # STEP 2: TAGS via autocomplete dropdown
            # ==========================================
            print("\n[3] Loading Share tab...")
            await page.goto("https://gumroad.com/products/wblqda/edit/share", wait_until="networkidle")
            await asyncio.sleep(3)

            print("[4] Tags via autocomplete...")

            # Scroll to Tags
            await page.evaluate("""() => {
                const labels = document.querySelectorAll('label');
                for (const l of labels) {
                    if (l.textContent.trim() === 'Tags') {
                        l.scrollIntoView({behavior: 'instant', block: 'center'});
                        return;
                    }
                }
            }""")
            await asyncio.sleep(1)

            tags_added = 0
            for search_term in TAG_SEARCHES:
                # Click React Select container
                rs = page.locator('[data-value]').first
                await rs.click()
                await asyncio.sleep(0.5)

                # Clear any existing text
                await page.keyboard.press("Control+a")
                await page.keyboard.press("Backspace")
                await asyncio.sleep(0.3)

                # Type search term slowly
                await page.keyboard.type(search_term, delay=80)
                await asyncio.sleep(3)  # Wait for server-side search results

                # Screenshot to see dropdown
                if search_term == TAG_SEARCHES[0]:
                    await page.screenshot(path=str(SCREENSHOTS / f"v9_04_tag_{search_term}.png"))

                # Check for dropdown options
                options = await page.evaluate("""() => {
                    const opts = document.querySelectorAll('[role="option"], [class*="option"]:not([class*="placeholder"])');
                    const result = [];
                    for (const opt of opts) {
                        if (opt.offsetParent !== null) {
                            result.push({
                                text: opt.textContent.trim().substring(0, 60),
                                classes: opt.className.toString().substring(0, 60),
                            });
                        }
                    }
                    return result;
                }""")

                if options:
                    print(f"  '{search_term}' → {len(options)} options: {[o['text'] for o in options[:5]]}")
                    # Click the FIRST matching option
                    await page.evaluate("""() => {
                        const opts = document.querySelectorAll('[role="option"], [class*="option"]:not([class*="placeholder"])');
                        for (const opt of opts) {
                            if (opt.offsetParent !== null) {
                                opt.click();
                                return;
                            }
                        }
                    }""")
                    tags_added += 1
                    await asyncio.sleep(1)
                else:
                    print(f"  '{search_term}' → no dropdown options")
                    # Press Escape to close any open menu
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(0.5)

            print(f"\n  Total tags added: {tags_added}")

            # Check what tags are now showing
            final_chips = await page.evaluate("""() => {
                const container = document.querySelector('[data-value]');
                if (!container) return {dv: 'none', html: ''};
                return {
                    dv: container.getAttribute('data-value'),
                    html: container.innerHTML.substring(0, 1000),
                };
            }""")
            print(f"  data-value: '{final_chips['dv']}'")

            await page.screenshot(path=str(SCREENSHOTS / "v9_05_tags_done.png"))

            # Save
            save = page.locator('button:has-text("Save changes")').first
            if await save.is_visible(timeout=3000):
                await save.click()
                await asyncio.sleep(4)
                print("  Saved!")

            await page.screenshot(path=str(SCREENSHOTS / "v9_06_final.png"), full_page=True)

        except Exception as e:
            print(f"\nERROR: {e}")
            import traceback; traceback.print_exc()
        finally:
            await browser.close()

    # Verify
    print("\n[VERIFY]")
    import requests
    token = os.getenv("GUMROAD_API_KEY", "")
    r = requests.get("https://api.gumroad.com/v2/products", params={"access_token": token})
    if r.status_code == 200:
        for prod in r.json().get("products", []):
            print(f"  Name: {prod.get('name')}")
            print(f"  Price: {prod.get('formatted_price')}")
            print(f"  PWYW: {prod.get('customizable_price')}")
            print(f"  Covers: {len(prod.get('covers', []))}")
            print(f"  Tags: {prod.get('tags', [])}")
            # Full product data dump for debugging
            import json
            print(f"  Full keys: {list(prod.keys())}")


if __name__ == "__main__":
    asyncio.run(run())
