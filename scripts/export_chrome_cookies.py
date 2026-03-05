#!/usr/bin/env python3
"""Export Chrome cookies into JSON files compatible with browser_session_import.py.

Run on the SAME machine where Chrome profile is logged in (usually your Windows PC).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SERVICE_DOMAINS: dict[str, list[str]] = {
    "amazon_kdp": [".kdp.amazon.com", ".amazon.com"],
    "etsy": [".etsy.com"],
    "gumroad": [".gumroad.com"],
    "kofi": [".ko-fi.com"],
    "printful": [".printful.com"],
    "twitter": [".x.com", ".twitter.com"],
    "reddit": [".reddit.com"],
    "threads": [".threads.net"],
    "instagram": [".instagram.com"],
    "facebook": [".facebook.com"],
    "pinterest": [".pinterest.com"],
    "youtube": [".youtube.com", ".google.com"],
    "linkedin": [".linkedin.com"],
    "tiktok": [".tiktok.com"],
}


def _cookie_to_json(c) -> dict:
    return {
        "name": str(c.name),
        "value": str(c.value),
        "domain": str(c.domain),
        "path": str(c.path or "/"),
        "secure": bool(c.secure),
        "httpOnly": False,
        "expires": int(c.expires) if getattr(c, "expires", None) else None,
        "sameSite": None,
    }


def _load_for_domain(domain: str):
    # browser_cookie3 uses local OS decryption (DPAPI/Keychain/etc).
    import browser_cookie3  # lazy import to keep module importable in CI/tests

    return browser_cookie3.chrome(domain_name=domain)


def export_service(service: str, out_dir: Path) -> dict:
    domains = SERVICE_DOMAINS.get(service, [])
    if not domains:
        return {"ok": False, "service": service, "error": "unsupported_service"}

    rows: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    errors: list[str] = []
    for d in domains:
        try:
            jar = _load_for_domain(d)
            for c in jar:
                row = _cookie_to_json(c)
                key = (row["domain"], row["path"], row["name"])
                if key in seen:
                    continue
                seen.add(key)
                rows.append(row)
        except Exception as e:
            errors.append(f"{d}:{e}")

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{service}.cookies.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "service": service,
        "cookies": len(rows),
        "file": str(out),
        "errors": errors,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--service", default="", help="single service key")
    ap.add_argument("--all", action="store_true", help="export all services")
    ap.add_argument("--out-dir", default="cookies_export", help="output directory")
    args = ap.parse_args()

    try:
        import browser_cookie3  # noqa: F401
    except Exception as e:
        print(json.dumps({"ok": False, "error": "browser_cookie3_missing", "detail": str(e)}, ensure_ascii=False))
        return 2

    out_dir = Path(args.out_dir).expanduser().resolve()
    services: list[str]
    if args.all:
        services = list(SERVICE_DOMAINS.keys())
    else:
        svc = str(args.service or "").strip().lower()
        if not svc:
            print(json.dumps({"ok": False, "error": "service_required", "services": sorted(SERVICE_DOMAINS.keys())}, ensure_ascii=False))
            return 1
        services = [svc]

    results = [export_service(s, out_dir) for s in services]
    ok = all(bool(r.get("ok")) for r in results)
    print(json.dumps({"ok": ok, "results": results, "out_dir": str(out_dir)}, ensure_ascii=False, indent=2))
    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
