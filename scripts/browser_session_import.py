#!/usr/bin/env python3
"""Import browser cookies JSON into Playwright storage_state for platform browser auth.

Usage examples:
  python3 scripts/browser_session_import.py --service amazon_kdp --cookies-file runtime/owner_input/amazon.cookies.json --verify
  python3 scripts/browser_session_import.py --service etsy --cookies-file runtime/owner_input/etsy.cookies.json --storage-path runtime/etsy_storage_state.json --verify
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings


SERVICE_VERIFY_URLS: dict[str, str] = {
    "amazon_kdp": "https://kdp.amazon.com/bookshelf",
    "etsy": "https://www.etsy.com/your/shops/me/tools/listings/create",
    "kofi": "https://ko-fi.com/manage",
    "printful": "https://www.printful.com/dashboard",
    "gumroad": "https://gumroad.com/products",
    "twitter": "https://x.com/home",
    "reddit": "https://www.reddit.com/",
}


def _default_storage_path(service: str) -> str:
    if service == "amazon_kdp":
        return str(getattr(settings, "KDP_STORAGE_STATE_FILE", "runtime/kdp_storage_state.json") or "runtime/kdp_storage_state.json")
    if service == "etsy":
        return str(getattr(settings, "ETSY_STORAGE_STATE_FILE", "runtime/etsy_storage_state.json") or "runtime/etsy_storage_state.json")
    if service == "kofi":
        return str(getattr(settings, "KOFI_STORAGE_STATE_FILE", "runtime/kofi_storage_state.json") or "runtime/kofi_storage_state.json")
    if service == "printful":
        return str(getattr(settings, "PRINTFUL_STORAGE_STATE_FILE", "runtime/printful_storage_state.json") or "runtime/printful_storage_state.json")
    if service == "gumroad":
        return str(getattr(settings, "GUMROAD_STORAGE_STATE_FILE", "runtime/gumroad_storage_state.json") or "runtime/gumroad_storage_state.json")
    if service == "twitter":
        return str(getattr(settings, "TWITTER_STORAGE_STATE_FILE", "runtime/twitter_storage_state.json") or "runtime/twitter_storage_state.json")
    if service == "reddit":
        return str(getattr(settings, "REDDIT_STORAGE_STATE_FILE", "runtime/reddit_storage_state.json") or "runtime/reddit_storage_state.json")
    raise ValueError(f"unsupported service: {service}")


def _extract_cookie_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        if isinstance(payload.get("cookies"), list):
            return [x for x in payload.get("cookies", []) if isinstance(x, dict)]
        if isinstance(payload.get("entries"), list):
            return [x for x in payload.get("entries", []) if isinstance(x, dict)]
    return []


def _norm_same_site(raw: Any) -> str | None:
    v = str(raw or "").strip().lower()
    if v in {"lax", "strict", "none"}:
        return v.capitalize()
    return None


def _to_int_exp(raw: Any) -> int | None:
    if raw is None:
        return None
    try:
        f = float(raw)
        if f <= 0:
            return None
        return int(f)
    except Exception:
        return None


def _normalize_cookie(c: dict[str, Any]) -> dict[str, Any] | None:
    name = str(c.get("name") or "").strip()
    value = str(c.get("value") or "")
    domain = str(c.get("domain") or "").strip()
    if not domain and c.get("hostOnly") and c.get("host"):
        domain = str(c.get("host") or "").strip()
    path = str(c.get("path") or "/")
    if not name or not domain:
        return None

    out: dict[str, Any] = {
        "name": name,
        "value": value,
        "domain": domain,
        "path": path,
        "secure": bool(c.get("secure", False)),
        "httpOnly": bool(c.get("httpOnly", False)),
    }

    same_site = _norm_same_site(c.get("sameSite"))
    if same_site:
        out["sameSite"] = same_site

    exp = _to_int_exp(c.get("expires"))
    if exp is None:
        exp = _to_int_exp(c.get("expirationDate"))
    if exp is not None:
        out["expires"] = exp

    return out


async def _write_storage_state(cookies: list[dict[str, Any]], storage_path: Path) -> None:
    from playwright.async_api import async_playwright

    storage_path.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context()
        await context.add_cookies(cookies)
        await context.storage_state(path=str(storage_path))
        await context.close()
        await browser.close()
    # Keep a backup to survive accidental overwrite/cleanup.
    try:
        backup_path = storage_path.with_suffix(".backup.json")
        backup_path.write_text(storage_path.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception:
        pass


async def _verify(service: str, storage_path: Path) -> tuple[bool, dict[str, Any]]:
    from playwright.async_api import async_playwright

    if not storage_path.exists():
        return False, {"error": "storage_missing"}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context(storage_state=str(storage_path), viewport={"width": 1280, "height": 720})
        page = await context.new_page()

        url = SERVICE_VERIFY_URLS.get(service, "")
        if not url:
            await context.close()
            await browser.close()
            return False, {"error": "verify_url_not_defined"}
        await page.goto(url, wait_until="domcontentloaded", timeout=120000)
        await page.wait_for_timeout(1200)
        u = (page.url or "").lower()
        bad_markers = ("signin", "/sign", "login", "challenge", "captcha")
        ok = not any(m in u for m in bad_markers)
        if service == "amazon_kdp":
            ok = ok and any(x in u for x in ("/bookshelf", "/en_us/", "/reports", "kdp.amazon.com"))
        if service == "twitter":
            ok = ok and ("x.com" in u or "twitter.com" in u)
        if service == "reddit":
            ok = ok and "reddit.com" in u

        title = await page.title()
        await context.close()
        await browser.close()
        return ok, {"ok": ok, "url": page.url, "title": title}


def main() -> int:
    ap = argparse.ArgumentParser(description="Import browser cookies into Playwright storage_state")
    ap.add_argument("--service", required=True, choices=sorted(list(SERVICE_VERIFY_URLS.keys())))
    ap.add_argument("--cookies-file", required=True)
    ap.add_argument("--storage-path", default="")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    cookies_file = Path(args.cookies_file)
    if not cookies_file.is_absolute():
        cookies_file = PROJECT_ROOT / cookies_file
    if not cookies_file.exists():
        print(json.dumps({"ok": False, "error": "cookies_file_missing", "path": str(cookies_file)}, ensure_ascii=False))
        return 1

    storage_raw = str(args.storage_path or _default_storage_path(args.service))
    storage_path = Path(storage_raw)
    if not storage_path.is_absolute():
        storage_path = PROJECT_ROOT / storage_path

    try:
        payload = json.loads(cookies_file.read_text(encoding="utf-8"))
    except Exception as e:
        print(json.dumps({"ok": False, "error": "cookies_parse_error", "detail": str(e)}, ensure_ascii=False))
        return 2

    items = _extract_cookie_list(payload)
    normalized = []
    for c in items:
        nc = _normalize_cookie(c)
        if nc:
            normalized.append(nc)

    if not normalized:
        print(json.dumps({"ok": False, "error": "no_valid_cookies"}, ensure_ascii=False))
        return 3

    try:
        asyncio.run(_write_storage_state(normalized, storage_path))
    except Exception as e:
        print(json.dumps({"ok": False, "error": "storage_write_failed", "detail": str(e)}, ensure_ascii=False))
        return 4

    out: dict[str, Any] = {
        "ok": True,
        "service": args.service,
        "cookies_imported": len(normalized),
        "storage_state": str(storage_path),
    }

    if args.verify:
        try:
            ok, meta = asyncio.run(_verify(args.service, storage_path))
            out["verify"] = meta
            if not ok:
                print(json.dumps(out, ensure_ascii=False))
                return 5
        except Exception as e:
            out["verify"] = {"ok": False, "error": "verify_failed", "detail": str(e)}
            print(json.dumps(out, ensure_ascii=False))
            return 6

    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
