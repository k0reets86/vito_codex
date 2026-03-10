#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.paths import PROJECT_ROOT
from modules.platform_live_validation import validate_owner_grade_repeatability
from modules.platform_repeatability import attach_publish_repeatability


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _validate_kofi() -> dict[str, Any]:
    path = PROJECT_ROOT / "runtime" / "kofi_publish_exact3" / "result.json"
    payload = _read_json(path)
    public_url = ""
    links = list(payload.get("links") or [])
    if links and isinstance(links[0], dict):
        public_url = str(links[0].get("href") or "").strip()
    result = attach_publish_repeatability(
        {
            "platform": "kofi",
            "status": "published" if public_url else "prepared",
            "url": public_url,
            "screenshot_path": str(path),
            "title": "Ko-fi live product",
        },
        platform="kofi",
        mode="owner_grade_validation",
        artifact_flags={
            "title": bool(payload.get("after_has_title")),
            "description": bool(payload.get("after_snip")),
            "price": True,
            "file_or_link": bool(public_url),
        },
        required_artifacts=("title", "description", "price", "file_or_link"),
    )
    ok, errors = validate_owner_grade_repeatability(result)
    return {
        "platform": "kofi",
        "source": str(path),
        "result": result,
        "owner_grade_ok": ok,
        "errors": errors,
    }


def run_validation() -> dict[str, Any]:
    checks = [_validate_kofi()]
    passed = sum(1 for item in checks if item["owner_grade_ok"])
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "summary": {
            "total": len(checks),
            "passed": passed,
            "failed": len(checks) - passed,
            "all_owner_grade_ok": passed == len(checks),
        },
    }


def main() -> int:
    report = run_validation()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%MUTC")
    out = PROJECT_ROOT / "reports" / f"VITO_PLATFORM_OWNER_GRADE_VALIDATION_{ts}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out))
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if report["summary"]["all_owner_grade_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
