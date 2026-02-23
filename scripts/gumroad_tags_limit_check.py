#!/usr/bin/env python3
"""Check if Gumroad has a tag limit. Also monitor network requests for autocomplete."""

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

        # Intercept XHR/Fetch requests
        requests_log = []
        async def on_request(req):
            if 'tag' in req.url.lower() or 'search' in req.url.lower() or 'autocomplete' in req.url.lower():
                requests_log.append({'url': req.url, 'method': req.method})
        page.on("request", on_request)

        responses_log = []
        async def on_response(resp):
            if 'tag' in resp.url.lower() or 'search' in resp.url.lower() or 'autocomplete' in resp.url.lower():
                try:
                    body = await resp.text()
                    responses_log.append({'url': resp.url, 'status': resp.status, 'body': body[:500]})
                except:
                    responses_log.append({'url': resp.url, 'status': resp.status, 'body': 'failed to read'})
        page.on("response", on_response)

        try:
            print("[1] Loading Share tab...")
            await page.goto("https://gumroad.com/products/wblqda/edit/share", wait_until="networkidle")
            await asyncio.sleep(3)
            if "login" in page.url.lower():
                print("COOKIE EXPIRED"); return

            # Check for tag limit messages anywhere on page
            tag_section = await page.evaluate("""() => {
                const labels = document.querySelectorAll('label');
                for (const l of labels) {
                    if (l.textContent.trim() === 'Tags') {
                        // Get the parent fieldset/section
                        let parent = l.parentElement;
                        for (let i = 0; i < 5; i++) {
                            if (!parent) break;
                            const text = parent.textContent.trim();
                            if (text.length > 100) {
                                // Found a containing section — return its full text
                                return {
                                    level: i,
                                    text: text.substring(0, 500),
                                    tag: parent.tagName,
                                    className: parent.className?.toString().substring(0, 80) || '',
                                };
                            }
                            parent = parent.parentElement;
                        }
                    }
                }
                return null;
            }""")
            print(f"[2] Tags section text:")
            if tag_section:
                print(f"  {tag_section['text'][:300]}")
            else:
                print("  Not found")

            # Check if existing tags are shown as pills/badges below the input
            tag_pills = await page.evaluate("""() => {
                // Look for pill/badge elements near Tags area
                const labels = document.querySelectorAll('label');
                for (const l of labels) {
                    if (l.textContent.trim() !== 'Tags') continue;
                    let parent = l.parentElement;
                    for (let i = 0; i < 5; i++) {
                        if (!parent) break;
                        // Look for any elements that might be tag pills
                        const buttons = parent.querySelectorAll('button');
                        const spans = parent.querySelectorAll('span');
                        const pills = [];
                        for (const btn of buttons) {
                            if (btn.offsetParent !== null && btn.textContent.trim().length > 0 && btn.textContent.trim().length < 30) {
                                pills.push({type: 'button', text: btn.textContent.trim(), classes: btn.className?.toString().substring(0, 60) || ''});
                            }
                        }
                        if (pills.length > 0) return {level: i, pills};
                        parent = parent.parentElement;
                    }
                }
                return null;
            }""")
            print(f"\n[3] Tag pills: {json.dumps(tag_pills, indent=2)}")

            # Scroll to tags and take screenshot
            await page.evaluate("""() => {
                const labels = document.querySelectorAll('label');
                for (const l of labels) {
                    if (l.textContent.trim() === 'Tags') {
                        l.scrollIntoView({behavior: 'instant', block: 'start'});
                        return;
                    }
                }
            }""")
            await asyncio.sleep(1)
            await page.screenshot(path=str(SCREENSHOTS / "tag_limit_01.png"))

            # Click Tags input and type
            print("\n[4] Clicking Tags and typing 'money'...")
            dvs = page.locator('[data-value]')
            tags_dv = dvs.nth(1)
            await tags_dv.click()
            await asyncio.sleep(0.5)
            await page.keyboard.type("money", delay=100)
            await asyncio.sleep(4)  # Extra wait for network

            print(f"\n[5] Network requests with 'tag'/'search'/'autocomplete':")
            for req in requests_log:
                print(f"  REQ: {req['method']} {req['url'][:100]}")
            for resp in responses_log:
                print(f"  RESP: {resp['status']} {resp['url'][:100]}")
                print(f"    Body: {resp['body'][:200]}")

            if not requests_log:
                print("  NO tag-related requests captured!")

            # Let's also check ALL XHR requests in the last few seconds
            print("\n[6] Checking broader network...")
            requests_log2 = []
            async def on_req2(req):
                if req.resource_type in ('xhr', 'fetch'):
                    requests_log2.append({'url': req.url[:100], 'method': req.method})
            page.on("request", on_req2)

            # Clear and type again
            await page.keyboard.press("Control+a")
            await page.keyboard.press("Backspace")
            await asyncio.sleep(0.5)
            await page.keyboard.type("ai", delay=100)
            await asyncio.sleep(3)

            print(f"  XHR/Fetch requests after typing 'ai':")
            for req in requests_log2:
                print(f"    {req['method']} {req['url']}")

            await page.screenshot(path=str(SCREENSHOTS / "tag_limit_02_ai.png"))

            # Check aria-expanded state
            expanded = await page.evaluate("""() => {
                const dvs = document.querySelectorAll('[data-value]');
                const el = dvs[1];
                const input = el ? el.querySelector('input') : null;
                return input ? {
                    ariaExpanded: input.getAttribute('aria-expanded'),
                    value: input.value,
                    disabled: input.disabled,
                    readOnly: input.readOnly,
                } : null;
            }""")
            print(f"\n[7] Input state: {json.dumps(expanded)}")

        except Exception as e:
            print(f"\nERROR: {e}")
            import traceback; traceback.print_exc()
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(run())
