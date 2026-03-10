#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from platforms.etsy import EtsyPlatform
from platforms.gumroad import GumroadPlatform
from platforms.printful import PrintfulPlatform


def _inspect_adapter(name: str, platform) -> dict:
    has_human = bool(getattr(platform, "_human_browser", None))
    browser_kwargs = {}
    try:
        browser_kwargs = platform._browser_context_kwargs()  # type: ignore[attr-defined]
    except Exception as e:
        browser_kwargs = {"error": str(e)}
    return {
        "platform": name,
        "has_human_browser": has_human,
        "has_storage_state": bool(browser_kwargs.get("storage_state")),
        "has_locale": bool(browser_kwargs.get("locale")),
        "has_timezone": bool(browser_kwargs.get("timezone_id")),
        "has_user_agent": bool(browser_kwargs.get("user_agent")),
        "ok": has_human and "error" not in browser_kwargs,
    }


def run() -> dict:
    checks = [
        _inspect_adapter("etsy", EtsyPlatform()),
        _inspect_adapter("gumroad", GumroadPlatform()),
        _inspect_adapter("printful", PrintfulPlatform()),
    ]
    summary = {
        "total": len(checks),
        "passed": sum(1 for c in checks if c["ok"]),
        "failed": sum(1 for c in checks if not c["ok"]),
    }
    out = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "summary": summary,
    }
    report = PROJECT_ROOT / "reports" / f"BROWSER_ADAPTER_REGRESSIONS_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%MUTC')}.json"
    report.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(report))
    print(json.dumps(summary, ensure_ascii=False))
    return out


def main() -> int:
    result = run()
    return 0 if result["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
