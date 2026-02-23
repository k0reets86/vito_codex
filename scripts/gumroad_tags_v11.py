#!/usr/bin/env python3
"""V11: Fix tags — do NOT Ctrl+A/Backspace (removes chips). Just click+type+select.
Also: save after each tag to test if multi-select persists across saves."""

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

# Tags to search in Gumroad autocomplete (popular ones)
TAG_SEARCHES = ["ai", "passive income", "chatgpt", "ebook", "side hustle"]


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
            # STEP 1: Load Share tab
            # ==========================================
            print("[1] Loading Share tab...")
            await page.goto("https://gumroad.com/products/wblqda/edit/share", wait_until="networkidle")
            await asyncio.sleep(3)
            if "login" in page.url.lower():
                print("COOKIE EXPIRED — ask owner to refresh /tmp/gumroad_cookie.txt")
                return

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

            # ==========================================
            # STEP 2: Identify Tags vs Category [data-value]
            # ==========================================
            all_dv = await page.evaluate("""() => {
                const dvs = document.querySelectorAll('[data-value]');
                return Array.from(dvs).map((d, i) => ({
                    i,
                    dataValue: d.getAttribute('data-value'),
                    parentText: (d.closest('fieldset')?.querySelector('label')?.textContent ||
                                 d.parentElement?.parentElement?.querySelector('label')?.textContent ||
                                 d.parentElement?.textContent || '').trim().substring(0, 80),
                    visible: d.offsetParent !== null,
                }));
            }""")
            print(f"[2] All [data-value] elements ({len(all_dv)}):")
            for dv in all_dv:
                print(f"    [{dv['i']}] val='{dv['dataValue']}' parent='{dv['parentText'][:60]}'")

            # Find the Tags one (second [data-value], or the one whose label contains "Tags")
            tags_idx = None
            for dv in all_dv:
                parent = dv.get('parentText', '').lower()
                if 'tag' in parent and 'categ' not in parent:
                    tags_idx = dv['i']
                    break
            if tags_idx is None and len(all_dv) >= 2:
                tags_idx = 1  # Default to second

            if tags_idx is None:
                print("ERROR: Could not find Tags [data-value]")
                return

            print(f"\n  Tags [data-value] index: {tags_idx}")

            # Mark the Tags container with a custom attribute
            await page.evaluate(f"""() => {{
                const dvs = document.querySelectorAll('[data-value]');
                if (dvs[{tags_idx}]) dvs[{tags_idx}].setAttribute('data-vito-tags', 'true');
            }}""")

            tags_container = page.locator('[data-vito-tags="true"]').first

            # ==========================================
            # STEP 3: Check current state — how many tags already exist?
            # ==========================================
            initial_state = await page.evaluate(f"""() => {{
                const dvs = document.querySelectorAll('[data-value]');
                const el = dvs[{tags_idx}];
                if (!el) return {{ error: 'not found' }};

                // Check for multi-value chips
                const multiValues = el.querySelectorAll('[class*="multiValue"]');
                const singleValue = el.querySelector('[class*="singleValue"]');

                // Check the actual data-value
                const dv = el.getAttribute('data-value');

                // Check all inner content
                const innerText = el.textContent.trim().substring(0, 200);

                return {{
                    dataValue: dv,
                    multiValueCount: multiValues.length,
                    multiValueTexts: Array.from(multiValues).map(mv => mv.textContent.trim()),
                    hasSingleValue: !!singleValue,
                    singleValueText: singleValue ? singleValue.textContent.trim() : '',
                    innerText: innerText,
                }};
            }}""")
            print(f"  Initial state: {json.dumps(initial_state, indent=2)}")

            # ==========================================
            # STEP 4: Add tags one by one (NO Ctrl+A/Backspace!)
            # ==========================================
            print("\n[3] Adding tags (no clearing between tags)...")
            tags_added = 0

            for i, search_term in enumerate(TAG_SEARCHES):
                print(f"\n  --- Tag {i+1}: '{search_term}' ---")

                # Click the tags container to focus input
                await tags_container.click()
                await asyncio.sleep(0.5)

                # DO NOT clear! Just type the search term directly
                # The input should be empty after previous selection
                await page.keyboard.type(search_term, delay=80)
                await asyncio.sleep(3)  # Wait for server-side autocomplete

                # Screenshot for first tag
                if i == 0:
                    await page.screenshot(path=str(SCREENSHOTS / "v11_01_first_tag_dropdown.png"))

                # Check dropdown options
                options = await page.evaluate("""() => {
                    const opts = document.querySelectorAll('[role="option"]');
                    const result = [];
                    for (const opt of opts) {
                        if (opt.offsetParent !== null) {
                            result.push(opt.textContent.trim().substring(0, 60));
                        }
                    }
                    return result;
                }""")

                if options:
                    print(f"    Options: {options[:3]}")
                    # Click first option
                    await page.evaluate("""() => {
                        const opts = document.querySelectorAll('[role="option"]');
                        for (const opt of opts) {
                            if (opt.offsetParent !== null) {
                                opt.click();
                                return;
                            }
                        }
                    }""")
                    tags_added += 1
                    await asyncio.sleep(1)

                    # Check state after this tag
                    state = await page.evaluate(f"""() => {{
                        const dvs = document.querySelectorAll('[data-value]');
                        const el = dvs[{tags_idx}];
                        if (!el) return 'not found';
                        const dv = el.getAttribute('data-value');
                        const multiValues = el.querySelectorAll('[class*="multiValue"]');
                        return {{
                            dataValue: dv,
                            chipCount: multiValues.length,
                            chips: Array.from(multiValues).map(mv => mv.textContent.trim()),
                        }};
                    }}""")
                    print(f"    After select: {json.dumps(state)}")
                else:
                    print(f"    No options found")
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(0.3)

            # ==========================================
            # STEP 5: Save
            # ==========================================
            print(f"\n[4] Saving... (tags added: {tags_added})")
            await page.screenshot(path=str(SCREENSHOTS / "v11_02_before_save.png"))

            save = page.locator('button:has-text("Save changes")').first
            if await save.is_visible(timeout=3000):
                await save.click()
                await asyncio.sleep(4)
                print("  Saved!")
            else:
                print("  Save button not visible!")

            # ==========================================
            # STEP 6: Reload and verify
            # ==========================================
            print("\n[5] Reloading to verify...")
            await page.goto("https://gumroad.com/products/wblqda/edit/share", wait_until="networkidle")
            await asyncio.sleep(3)

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

            # Check tags after reload
            after_reload = await page.evaluate("""() => {
                const dvs = document.querySelectorAll('[data-value]');
                const results = [];
                for (let i = 0; i < dvs.length; i++) {
                    const el = dvs[i];
                    const multiValues = el.querySelectorAll('[class*="multiValue"]');
                    const singleValue = el.querySelector('[class*="singleValue"]');
                    results.push({
                        i,
                        dataValue: el.getAttribute('data-value'),
                        chipCount: multiValues.length,
                        chips: Array.from(multiValues).map(mv => mv.textContent.trim()),
                        singleValue: singleValue ? singleValue.textContent.trim() : '',
                    });
                }
                return results;
            }""")
            print("  After reload:")
            for r in after_reload:
                print(f"    [{r['i']}] dv='{r['dataValue']}' chips={r['chips']} single='{r['singleValue']}'")

            await page.screenshot(path=str(SCREENSHOTS / "v11_03_after_reload.png"))

        except Exception as e:
            print(f"\nERROR: {e}")
            import traceback; traceback.print_exc()
        finally:
            await browser.close()

    # Verify via API
    print("\n[VERIFY via API]")
    import requests
    token = os.getenv("GUMROAD_API_KEY", "")
    r = requests.get("https://api.gumroad.com/v2/products", params={"access_token": token})
    if r.status_code == 200:
        for prod in r.json().get("products", []):
            print(f"  Tags: {prod.get('tags', [])}")
            print(f"  Categories: {prod.get('categories', [])}")


if __name__ == "__main__":
    asyncio.run(run())
