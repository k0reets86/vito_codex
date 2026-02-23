#!/usr/bin/env python3
"""Debug: dump tag input element and cover DOM structure."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SESSION_COOKIE = Path("/tmp/gumroad_cookie.txt").read_text().strip() if Path("/tmp/gumroad_cookie.txt").exists() else ""
SHARE_URL = "https://gumroad.com/products/wblqda/edit/share"
EDIT_URL = "https://gumroad.com/products/wblqda/edit"


async def run():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
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

        # === SHARE TAB: debug tags ===
        print("[SHARE TAB] Loading...")
        await page.goto(SHARE_URL, wait_until="networkidle")
        await asyncio.sleep(3)
        if "login" in page.url.lower():
            print("COOKIE EXPIRED"); await browser.close(); return

        # Find everything near "Tags" label
        tags_area = await page.evaluate("""() => {
            const result = [];
            const all = document.querySelectorAll('*');
            for (const el of all) {
                if (el.children.length === 0 && el.textContent.trim() === 'Tags'
                    && el.offsetParent !== null) {
                    // Found Tags label
                    result.push({type: 'label', tag: el.tagName, text: 'Tags'});

                    // Look at siblings and children of parent
                    const parent = el.parentElement;
                    if (parent) {
                        const children = parent.querySelectorAll('*');
                        for (const c of children) {
                            if (c === el) continue;
                            result.push({
                                type: 'sibling-child',
                                tag: c.tagName,
                                text: c.textContent.trim().substring(0, 80),
                                ph: c.placeholder || '',
                                contentEditable: c.contentEditable || '',
                                role: c.getAttribute('role') || '',
                                ariaLabel: c.getAttribute('aria-label') || '',
                                classes: c.className ? c.className.toString().substring(0, 80) : '',
                                inputType: c.type || '',
                                visible: c.offsetParent !== null,
                            });
                        }
                    }

                    // Also check next siblings of label
                    let sib = el.nextElementSibling;
                    for (let i = 0; i < 5 && sib; i++) {
                        result.push({
                            type: 'next-sibling',
                            tag: sib.tagName,
                            text: sib.textContent.trim().substring(0, 80),
                            ph: sib.placeholder || '',
                            contentEditable: sib.contentEditable || '',
                            classes: sib.className ? sib.className.toString().substring(0, 80) : '',
                        });
                        sib = sib.nextElementSibling;
                    }
                    break;
                }
            }
            return result;
        }""")
        print(f"\nTags area elements ({len(tags_area)}):")
        for el in tags_area:
            print(f"  {el}")

        # Specifically look for the "Begin typing to add a tag..." element
        begin_typing = await page.evaluate("""() => {
            const all = document.querySelectorAll('*');
            for (const el of all) {
                if (el.textContent.includes('Begin typing to add a tag')
                    && el.offsetParent !== null
                    && el.getBoundingClientRect().height < 60) {
                    return {
                        tag: el.tagName,
                        text: el.textContent.trim().substring(0, 100),
                        ph: el.placeholder || 'NONE',
                        contentEditable: el.contentEditable || 'NONE',
                        role: el.getAttribute('role') || 'NONE',
                        classes: el.className ? el.className.toString().substring(0, 100) : 'NONE',
                        type: el.type || 'NONE',
                        tagName: el.tagName,
                        inputMode: el.inputMode || 'NONE',
                        children: el.children.length,
                        innerHTML: el.innerHTML.substring(0, 200),
                        outerHTML: el.outerHTML.substring(0, 500),
                    };
                }
            }
            return null;
        }""")
        print(f"\n'Begin typing' element:")
        print(f"  {begin_typing}")

        # === PRODUCT TAB: debug cover ===
        print("\n\n[PRODUCT TAB] Loading...")
        await page.goto(EDIT_URL, wait_until="networkidle")
        await asyncio.sleep(3)

        # Get full page headings
        headings = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('h2')).map(h => ({
                text: h.textContent.trim(),
                visible: h.offsetParent !== null,
                y: h.getBoundingClientRect().y,
            }));
        }""")
        print(f"Page h2 headings: {headings}")

        # Scroll to Cover
        await page.evaluate("""() => {
            const h2s = document.querySelectorAll('h2');
            for (const h2 of h2s) {
                if (h2.textContent.trim() === 'Cover') {
                    h2.scrollIntoView({behavior: 'instant', block: 'start'});
                    return true;
                }
            }
            return false;
        }""")
        await asyncio.sleep(1)

        # Exhaustive search: go up from Cover h2 and dump each level
        for level in range(1, 8):
            info = await page.evaluate(f"""() => {{
                const h2s = document.querySelectorAll('h2');
                for (const h2 of h2s) {{
                    if (h2.textContent.trim() !== 'Cover') continue;
                    let el = h2;
                    for (let i = 0; i < {level}; i++) {{
                        el = el.parentElement;
                        if (!el) return null;
                    }}
                    return {{
                        level: {level},
                        tag: el.tagName,
                        classes: el.className ? el.className.toString().substring(0, 80) : '',
                        childCount: el.children.length,
                        btnCount: el.querySelectorAll('button').length,
                        imgCount: el.querySelectorAll('img').length,
                        fiCount: el.querySelectorAll('input[type="file"]').length,
                        text: el.textContent.trim().substring(0, 200),
                    }};
                }}
                return null;
            }}""")
            if info:
                print(f"  Level {level}: {info['tag']} children={info['childCount']} btns={info['btnCount']} imgs={info['imgCount']} fis={info['fiCount']} classes={info['classes'][:40]} text={info['text'][:60]}")

        await browser.close()


asyncio.run(run())
