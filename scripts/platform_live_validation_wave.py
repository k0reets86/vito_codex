#!/usr/bin/env python3
"""Run a mixed public/editor live validation wave for current platform objects."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from modules.platform_validation_registry import record_platform_validation_result
RUNTIME = ROOT / "runtime"
REPORTS = ROOT / "reports"


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%MUTC")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else {"raw": data}


def _fetch(url: str) -> tuple[int, str, str]:
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=25)
    return r.status_code, r.url, r.text


def _extract_title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return re.sub(r"\s+", " ", (m.group(1).strip() if m else "")).strip()


def _check_gumroad() -> dict[str, Any]:
    url = "https://vitoai.gumroad.com/l/zrvfrg"
    status_code, final_url, html = _fetch(url)
    title = _extract_title(html)
    has_image = 'property="og:image"' in html.lower()
    has_description = "practical digital kit" in html.lower()
    ok = status_code == 200 and "creator funnel swipe file kit" in title.lower() and has_image and has_description
    return {
        "platform": "gumroad",
        "mode": "public",
        "url": final_url,
        "status_code": status_code,
        "title": title,
        "signals": {
            "has_image_meta": has_image,
            "has_expected_description": has_description,
        },
        "owner_grade_ok": ok,
        "state": "owner_grade" if ok else "partial",
    }


def _check_kofi() -> dict[str, Any]:
    url = "https://ko-fi.com/s/c6c9031adb"
    status_code, final_url, html = _fetch(url)
    title = _extract_title(html)
    blocked = status_code == 403 and "just a moment" in html.lower()
    return {
        "platform": "kofi",
        "mode": "public",
        "url": final_url,
        "status_code": status_code,
        "title": title,
        "signals": {
            "cloudflare_blocked": blocked,
        },
        "owner_grade_ok": False,
        "state": "blocked" if blocked else "partial",
    }


def _check_pinterest() -> dict[str, Any]:
    url = "https://www.pinterest.com/pin/1134203487424108921/"
    status_code, final_url, html = _fetch(url)
    title = _extract_title(html)
    has_etsy_link = "etsy.com/listing" in html.lower()
    has_desc = "description" in html.lower()
    ok = status_code == 200 and has_etsy_link and has_desc
    return {
        "platform": "pinterest",
        "mode": "public",
        "url": final_url,
        "status_code": status_code,
        "title": title,
        "signals": {
            "has_etsy_link": has_etsy_link,
            "has_description_markers": has_desc,
        },
        "owner_grade_ok": ok,
        "state": "owner_grade" if ok else "partial",
    }


def _check_twitter() -> dict[str, Any]:
    url = "https://x.com/bot_vito/status/2030767497083793839"
    status_code, final_url, html = _fetch(url)
    title = _extract_title(html)
    # X public HTML is JS-heavy; treat 200 + full app shell only as partial proof.
    has_app_shell = "api.x.com" in html.lower() and "viewport-fit=cover" in html.lower()
    return {
        "platform": "twitter",
        "mode": "public",
        "url": final_url,
        "status_code": status_code,
        "title": title,
        "signals": {
            "app_shell_loaded": has_app_shell,
        },
        "owner_grade_ok": False,
        "state": "partial" if status_code == 200 and has_app_shell else "blocked",
    }


def _check_etsy() -> dict[str, Any]:
    path = RUNTIME / "etsy_owner_grade_probe.json"
    data = _load_json(path) or {}
    ok = bool(
        data.get("ok")
        and data.get("body_has_instant_download")
        and data.get("body_has_materials")
        and data.get("body_has_category")
    )
    # Keep partial until file/media proof is stronger.
    return {
        "platform": "etsy",
        "mode": "editor_probe",
        "source": str(path),
        "signals": data,
        "owner_grade_ok": False,
        "state": "partial" if ok else "blocked",
    }


def _check_kdp() -> dict[str, Any]:
    path = RUNTIME / "kdp_owner_grade_probe.json"
    data = _load_json(path) or {}
    blocked = "amazon.com/ap/signin" in str(data.get("final_url") or "")
    return {
        "platform": "amazon_kdp",
        "mode": "bookshelf_probe",
        "source": str(path),
        "signals": data,
        "owner_grade_ok": False,
        "state": "blocked" if blocked else "partial",
    }


def _check_printful() -> dict[str, Any]:
    path = RUNTIME / "linked_platform_current_probe.json"
    data = _load_json(path) or {}
    probe = dict(data.get("printful", {}).get("probe") or {})
    title = str(probe.get("title") or "")
    ok = "my products | printful" in title.lower()
    return {
        "platform": "printful",
        "mode": "dashboard_probe",
        "source": str(path),
        "signals": {
            "url": probe.get("url"),
            "title": title,
        },
        "owner_grade_ok": False,
        "state": "partial" if ok else "blocked",
    }


def main() -> int:
    checks = [
        _check_gumroad(),
        _check_kofi(),
        _check_pinterest(),
        _check_twitter(),
        _check_etsy(),
        _check_kdp(),
        _check_printful(),
    ]
    for item in checks:
        record_platform_validation_result(item)
    summary = {
        "total": len(checks),
        "owner_grade": sum(1 for c in checks if c["state"] == "owner_grade"),
        "partial": sum(1 for c in checks if c["state"] == "partial"),
        "blocked": sum(1 for c in checks if c["state"] == "blocked"),
    }
    out = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "summary": summary,
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    report = REPORTS / f"VITO_PLATFORM_LIVE_VALIDATION_WAVE_{_ts()}.json"
    report.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(report))
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
