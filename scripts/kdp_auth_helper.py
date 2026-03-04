#!/usr/bin/env python3
"""Amazon KDP auth helper (browser session capture + probe).

Safe flow:
1) Open KDP login in Chromium.
2) Complete login and 2FA manually.
3) Save storage state for reuse by automation.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings


def _is_logged_in_url(url: str) -> bool:
    u = (url or "").lower()
    if "signin" in u or "ap/signin" in u:
        return False
    return any(x in u for x in ("/bookshelf", "/en_us/", "/reports"))


def _chromium_launch_args() -> list[str]:
    # Harden launch for constrained VPS/container environments where zygote/fork can fail.
    args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--renderer-process-limit=1",
    ]
    if bool(getattr(settings, "BROWSER_CONSTRAINED_MODE", True)):
        args.extend(["--no-zygote", "--single-process"])
    return args


async def browser_capture(
    timeout_sec: int,
    storage_path: str,
    headless: bool,
    auto_submit: bool = False,
    linger_sec: int = 0,
) -> int:
    from playwright.async_api import async_playwright

    email = str(getattr(settings, "KDP_EMAIL", "") or "")
    password = str(getattr(settings, "KDP_PASSWORD", "") or "")
    out = Path(storage_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    print("\n=== Amazon KDP Browser Session Capture ===")
    print("1) Откроется страница логина KDP")
    print("2) Войдите вручную и пройдите 2FA")
    print("3) Скрипт сохранит сессию после входа в Bookshelf")
    print(f"Storage state: {out}")
    if not email or not password:
        print("WARNING: KDP_EMAIL/KDP_PASSWORD не заданы, логин будет полностью вручную.")
    if headless:
        print("WARNING: headless=True может ухудшить прохождение защиты Amazon.")

    async def _launch_interactive_browser(playwright_obj):
        try:
            return await playwright_obj.chromium.launch(headless=headless, args=_chromium_launch_args())
        except Exception as e:
            # Some VPS environments fail Chromium headed launch intermittently
            # (thread/resource limits, Ozone/X11 quirks). Fallback keeps auth flow usable.
            print(f"WARN: Chromium launch failed ({e}). Trying Firefox fallback...")
            return await playwright_obj.firefox.launch(headless=headless)

    async with async_playwright() as p:
        browser = await _launch_interactive_browser(p)
        context = await browser.new_context(viewport={"width": 1366, "height": 900})
        page = await context.new_page()
        await page.goto("https://kdp.amazon.com", wait_until="domcontentloaded", timeout=120000)
        await page.wait_for_timeout(2000)

        # Best-effort prefill only
        if email:
            for sel in ("input[type='email']", "input[name='email']", "input[name='ap_email']"):
                try:
                    await page.fill(sel, email)
                    break
                except Exception:
                    continue
        if password:
            for sel in ("input[type='password']", "input[name='password']", "input[name='ap_password']"):
                try:
                    await page.fill(sel, password)
                    break
                except Exception:
                    continue
        if auto_submit:
            # Try to progress login form automatically, leaving only OTP/challenge for owner.
            try:
                for btn in ("input#continue", "input[name='continue']", "button:has-text('Continue')"):
                    try:
                        if await page.locator(btn).count() > 0:
                            await page.click(btn, timeout=1500)
                            await page.wait_for_timeout(900)
                            break
                    except Exception:
                        continue
                for sel in ("input[name='password']", "input[name='ap_password']", "input[type='password']"):
                    try:
                        if await page.locator(sel).count() > 0 and password:
                            await page.fill(sel, password, timeout=1500)
                            break
                    except Exception:
                        continue
                for btn in ("input#signInSubmit", "input[name='signInSubmit']", "button:has-text('Sign in')"):
                    try:
                        if await page.locator(btn).count() > 0:
                            await page.click(btn, timeout=1500)
                            await page.wait_for_timeout(1200)
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        print("Ожидаю успешный вход (bookshelf/reports)...")
        end_ts = asyncio.get_event_loop().time() + max(120, int(timeout_sec))
        ok = False
        while asyncio.get_event_loop().time() < end_ts:
            await page.wait_for_timeout(1500)
            if _is_logged_in_url(page.url):
                ok = True
                break

        if not ok:
            shot = out.with_suffix(".failed.png")
            try:
                await page.screenshot(path=str(shot), full_page=True)
            except Exception:
                pass
            await context.close()
            await browser.close()
            print("ERROR: логин не подтвержден до таймаута.")
            print(f"Debug screenshot: {shot}")
            return 1

        await context.storage_state(path=str(out))
        cookies = await context.cookies()
        cookie_path = out.with_suffix(".cookies.json")
        cookie_path.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
        if int(linger_sec or 0) > 0:
            print(f"INFO: keeping browser open for {int(linger_sec)}s before close...")
            await page.wait_for_timeout(int(linger_sec) * 1000)
        await context.close()
        await browser.close()
        print("OK: KDP сессия сохранена")
        print(f"- storage_state: {out}")
        print(f"- cookies: {cookie_path}")
        return 0


async def auto_login(timeout_sec: int, storage_path: str, otp_code: str = "") -> int:
    """Headless-friendly login with optional OTP from stdin/chat relay."""
    from playwright.async_api import async_playwright

    email = str(getattr(settings, "KDP_EMAIL", "") or "")
    password = str(getattr(settings, "KDP_PASSWORD", "") or "")
    out = Path(storage_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if not email or not password:
        print("ERROR: KDP_EMAIL/KDP_PASSWORD missing in .env")
        return 1

    last_url = ""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=_chromium_launch_args())
            context = await browser.new_context(viewport={"width": 1366, "height": 900})
            page = await context.new_page()
            await page.goto("https://kdp.amazon.com", wait_until="domcontentloaded", timeout=120000)
            await page.wait_for_timeout(1000)
            last_url = page.url
            print(f"STEP: opened {page.url}")

        # Landing page often has no form fields. Follow Sign in entrypoint first.
            if await page.locator("input[name='ap_email'], input[type='email'], input[name='email']").count() == 0:
                moved = False
                for sel in ("a[href='/bookshelf']", "a:has-text('Sign in')"):
                    try:
                        if await page.locator(sel).count() > 0:
                            await page.click(sel, timeout=3000)
                            moved = True
                            break
                    except Exception:
                        continue
                if not moved:
                    try:
                        await page.goto("https://kdp.amazon.com/bookshelf", wait_until="domcontentloaded", timeout=120000)
                        moved = True
                    except Exception:
                        moved = False
                await page.wait_for_timeout(1500)
                last_url = page.url
                print(f"STEP: moved_to_signin {page.url}")

        # Step 1: Email
            email_filled = False
            for sel in ("input[name='email']", "input[name='ap_email']", "input[type='email']"):
                try:
                    if await page.locator(sel).count() > 0:
                        await page.fill(sel, email, timeout=3000)
                        email_filled = True
                        break
                except Exception:
                    continue
            if not email_filled:
                await context.close()
                await browser.close()
                print(f"ERROR: email input not found. current_url={page.url}")
                return 5
            for btn in ("input#continue", "input[name='continue']", "button:has-text('Continue')"):
                try:
                    if await page.locator(btn).count() > 0:
                        await page.click(btn, timeout=2000)
                        break
                except Exception:
                    continue
            await page.wait_for_timeout(1200)
            last_url = page.url
            print(f"STEP: email_submitted {page.url}")

        # Step 2: Password
            pwd_filled = False
            for sel in ("input[name='password']", "input[name='ap_password']", "input[type='password']"):
                try:
                    if await page.locator(sel).count() > 0:
                        await page.fill(sel, password, timeout=3000)
                        pwd_filled = True
                        break
                except Exception:
                    continue
            if not pwd_filled:
                await context.close()
                await browser.close()
                print(f"ERROR: password input not found. current_url={page.url}")
                return 6
            for btn in ("input#signInSubmit", "input[name='signInSubmit']", "button:has-text('Sign in')"):
                try:
                    if await page.locator(btn).count() > 0:
                        await page.click(btn, timeout=2500)
                        break
                except Exception:
                    continue
            await page.wait_for_timeout(1500)
            last_url = page.url
            print(f"STEP: password_submitted {page.url}")

        # Step 3: OTP/MFA (if present)
            otp_selectors = (
                "input[name='otpCode']",
                "input[name='code']",
                "input[name='cvf_input_code']",
                "input#auth-mfa-otpcode",
                "input[type='tel']",
                "input[type='number']",
            )
            otp_submit_buttons = (
                "input#auth-signin-button",
                "input[name='mfaSubmit']",
                "input[name='cvf-submit-otp-button']",
                "button#cvf-submit-otp-button",
                "button:has-text('Sign in')",
                "button:has-text('Verify')",
                "button[type='submit']",
                "input[type='submit']",
            )
            otp_found = False
            for sel in otp_selectors:
                try:
                    if await page.locator(sel).count() > 0:
                        otp_found = True
                        break
                except Exception:
                    continue

            if otp_found:
                if not otp_code:
                    print("OTP_REQUIRED: send code now")
                    try:
                        otp_code = input().strip()
                    except Exception:
                        otp_code = ""
                if not otp_code:
                    await context.close()
                    await browser.close()
                    print("ERROR: OTP code not provided")
                    return 2
                filled = False
                for sel in otp_selectors:
                    try:
                        if await page.locator(sel).count() > 0:
                            await page.fill(sel, otp_code)
                            print(f"STEP: otp_filled selector={sel}")
                            filled = True
                            break
                    except Exception:
                        continue
                if not filled:
                    await context.close()
                    await browser.close()
                    print("ERROR: OTP input not found")
                    return 3
                for btn in otp_submit_buttons:
                    try:
                        await page.click(btn, timeout=2500)
                        print(f"STEP: otp_submitted button={btn} url={page.url}")
                        break
                    except Exception:
                        continue
                await page.wait_for_timeout(2000)

        # Wait for post-login URL
            end_ts = asyncio.get_event_loop().time() + max(60, int(timeout_sec))
            ok = False
            ticks = 0
            while asyncio.get_event_loop().time() < end_ts:
                u = page.url.lower()
                last_url = page.url
                if _is_logged_in_url(u):
                    ok = True
                    break
            # OTP can appear later (after additional checks/challenges)
                otp_late = False
                for sel in otp_selectors:
                    try:
                        if await page.locator(sel).count() > 0:
                            otp_late = True
                            break
                    except Exception:
                        continue
                if otp_late:
                    if not otp_code:
                        print("OTP_REQUIRED: send code now")
                        try:
                            otp_code = input().strip()
                        except Exception:
                            otp_code = ""
                    if otp_code:
                        for sel in otp_selectors:
                            try:
                                if await page.locator(sel).count() > 0:
                                    await page.fill(sel, otp_code, timeout=3000)
                                    print(f"STEP: otp_filled_late selector={sel}")
                                    break
                            except Exception:
                                continue
                        for btn in otp_submit_buttons:
                            try:
                                if await page.locator(btn).count() > 0:
                                    await page.click(btn, timeout=2500)
                                    print(f"STEP: otp_submitted_late button={btn} url={page.url}")
                                    break
                            except Exception:
                                continue
                        await page.wait_for_timeout(1500)

                # Fast-fail when OTP error is visible (invalid/expired) to avoid vague timeout.
                try:
                    err_text = await page.evaluate(
                        """() => {
                          const sels = [
                            '#auth-error-message-box .a-alert-content',
                            '.a-alert-content',
                            '#cvf-error-message',
                            '.cvf-widget-alert-message'
                          ];
                          for (const s of sels) {
                            const el = document.querySelector(s);
                            if (el && el.textContent) return el.textContent.trim();
                          }
                          return '';
                        }"""
                    )
                except Exception:
                    err_text = ""
                low_err = str(err_text or "").lower()
                if low_err and any(t in low_err for t in ("incorrect", "invalid", "expired", "wrong", "невер", "истек")):
                    shot = out.with_suffix(".otp_rejected.png")
                    try:
                        await page.screenshot(path=str(shot), full_page=True)
                    except Exception:
                        pass
                    await context.close()
                    await browser.close()
                    print(f"ERROR: otp_rejected message={err_text[:300]} debug={shot}")
                    return 7
            # Handle intermediate continue/challenge buttons if visible
                for btn in (
                    "input#auth-signin-button",
                    "button:has-text('Continue')",
                    "input[name='continue']",
                    "input[type='submit']",
                    "button[type='submit']",
                ):
                    try:
                        if await page.locator(btn).count() > 0:
                            await page.click(btn, timeout=800)
                    except Exception:
                        pass
                ticks += 1
                if ticks % 5 == 0:
                    print(f"WAIT: url={page.url}")
                if ticks % 15 == 0:
                    try:
                        dbg = out.with_suffix(".wait.png")
                        await page.screenshot(path=str(dbg), full_page=True)
                        print(f"DEBUG_SCREENSHOT: {dbg}")
                    except Exception:
                        pass
                await page.wait_for_timeout(1200)

            if not ok:
                shot = out.with_suffix(".auto.failed.png")
                try:
                    await page.screenshot(path=str(shot), full_page=True)
                except Exception:
                    pass
                await context.close()
                await browser.close()
                print(f"ERROR: login not confirmed. debug={shot}")
                return 4

            await context.storage_state(path=str(out))
            await context.close()
            await browser.close()
            print(f'{{"ok": true, "storage_state": "{out}"}}')
            return 0
    except Exception as e:
        print(f"ERROR: auto_login_exception={e} url={last_url}")
        return 9


async def probe_session(storage_path: str, headless: bool) -> int:
    from playwright.async_api import async_playwright

    state = Path(storage_path)
    if not state.exists():
        print(f"ERROR: storage_state not found: {state}")
        return 1

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, args=_chromium_launch_args())
        context = await browser.new_context(storage_state=str(state), viewport={"width": 1280, "height": 720})
        page = await context.new_page()
        await page.goto("https://kdp.amazon.com/bookshelf", wait_until="domcontentloaded", timeout=120000)
        await page.wait_for_timeout(1500)
        ok = _is_logged_in_url(page.url)
        title = await page.title()
        await context.close()
        await browser.close()
        print(json.dumps({"ok": ok, "url": page.url, "title": title}, ensure_ascii=False))
        return 0 if ok else 2


async def inventory_snapshot(storage_path: str, headless: bool) -> int:
    """Read KDP bookshelf using saved session and extract a lightweight inventory snapshot."""
    from playwright.async_api import async_playwright

    state = Path(storage_path)
    if not state.exists():
        print(f"ERROR: storage_state not found: {state}")
        return 1

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, args=_chromium_launch_args())
        context = await browser.new_context(storage_state=str(state), viewport={"width": 1366, "height": 900})
        page = await context.new_page()
        await page.goto("https://kdp.amazon.com/bookshelf", wait_until="domcontentloaded", timeout=120000)
        await page.wait_for_timeout(2500)

        url = page.url
        title = await page.title()
        ok = _is_logged_in_url(url)
        if not ok:
            await context.close()
            await browser.close()
            print(json.dumps({"ok": False, "url": url, "title": title, "products_count": 0, "items": []}, ensure_ascii=False))
            return 2

        items = []
        try:
            items = await page.evaluate(
                """() => {
                    const bad = new Set([
                      'bookshelf', 'reports', 'marketing', 'help', 'settings', 'sign out', 'sign in',
                      'kindle direct publishing', 'kdp', 'dashboard', 'create', 'new'
                    ]);
                    const out = [];
                    const seen = new Set();
                    const pushText = (raw) => {
                      const t = String(raw || '').replace(/\\s+/g, ' ').trim();
                      if (!t) return;
                      const low = t.toLowerCase();
                      if (t.length < 3 || t.length > 140) return;
                      if (bad.has(low)) return;
                      if (/^[0-9.,$\\-\\s]+$/.test(t)) return;
                      if (seen.has(low)) return;
                      seen.add(low);
                      out.push(t);
                    };
                    const selectors = [
                      "[data-testid*='book']",
                      "[data-testid*='title']",
                      "a[href*='/title/']",
                      "a[href*='/book/']",
                      "h2", "h3"
                    ];
                    for (const sel of selectors) {
                      const nodes = Array.from(document.querySelectorAll(sel));
                      for (const n of nodes) {
                        pushText(n.textContent || '');
                        if (out.length >= 40) break;
                      }
                      if (out.length >= 40) break;
                    }
                    return out;
                }"""
            )
        except Exception:
            items = []

        payload = {
            "ok": True,
            "url": url,
            "title": title,
            "products_count": len(items),
            "items": items[:20],
        }
        await context.close()
        await browser.close()
        print(json.dumps(payload, ensure_ascii=False))
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Amazon KDP auth helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_capture = sub.add_parser("browser-capture", help="Manual login + 2FA + save storage state")
    p_capture.add_argument("--timeout-sec", type=int, default=600)
    p_capture.add_argument("--storage-path", default=str(getattr(settings, "KDP_STORAGE_STATE_FILE", "runtime/kdp_storage_state.json")))
    p_capture.add_argument("--headless", action="store_true")
    p_capture.add_argument("--auto-submit", action="store_true", help="Autofill email/password and click login steps before OTP.")
    p_capture.add_argument("--linger-sec", type=int, default=0, help="Keep browser visible for N seconds after successful capture.")

    p_probe = sub.add_parser("probe", help="Check saved KDP session")
    p_probe.add_argument("--storage-path", default=str(getattr(settings, "KDP_STORAGE_STATE_FILE", "runtime/kdp_storage_state.json")))
    p_probe.add_argument("--headless", action="store_true")

    p_inv = sub.add_parser("inventory", help="Extract KDP bookshelf inventory snapshot")
    p_inv.add_argument("--storage-path", default=str(getattr(settings, "KDP_STORAGE_STATE_FILE", "runtime/kdp_storage_state.json")))
    p_inv.add_argument("--headless", action="store_true")

    p_auto = sub.add_parser("auto-login", help="Headless login using env creds and optional OTP code")
    p_auto.add_argument("--timeout-sec", type=int, default=300)
    p_auto.add_argument("--storage-path", default=str(getattr(settings, "KDP_STORAGE_STATE_FILE", "runtime/kdp_storage_state.json")))
    p_auto.add_argument("--otp-code", default="")

    args = parser.parse_args()
    if args.cmd == "browser-capture":
        return asyncio.run(
            browser_capture(
                int(args.timeout_sec),
                str(args.storage_path),
                bool(args.headless),
                bool(args.auto_submit),
                int(getattr(args, "linger_sec", 0) or 0),
            )
        )
    if args.cmd == "probe":
        return asyncio.run(probe_session(str(args.storage_path), bool(args.headless)))
    if args.cmd == "inventory":
        return asyncio.run(inventory_snapshot(str(args.storage_path), bool(args.headless)))
    if args.cmd == "auto-login":
        return asyncio.run(auto_login(int(args.timeout_sec), str(args.storage_path), str(args.otp_code or "")))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
