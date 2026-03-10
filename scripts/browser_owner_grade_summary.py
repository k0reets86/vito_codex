#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.safe_browser_diagnostics import run_diagnostics
from scripts.browser_adapter_regressions import run as run_regressions


def run_summary() -> dict:
    diagnostics = run_diagnostics(["etsy", "gumroad", "printful"])
    regressions = run_regressions()
    checks = []
    for service, data in diagnostics["services"].items():
        reg = next((item for item in regressions["checks"] if item["platform"] == service), {})
        owner_grade_ok = bool(
            data.get("persistent_profile_dir")
            and data.get("screenshot_first_default")
            and data.get("anti_bot_humanize")
            and reg.get("ok")
        )
        checks.append(
            {
                "platform": service,
                "diagnostics": data,
                "regression": reg,
                "owner_grade_browser_ok": owner_grade_ok,
            }
        )
    out = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "summary": {
            "total": len(checks),
            "owner_grade_ok": sum(1 for c in checks if c["owner_grade_browser_ok"]),
            "failed": sum(1 for c in checks if not c["owner_grade_browser_ok"]),
        },
    }
    report = PROJECT_ROOT / "reports" / f"BROWSER_OWNER_GRADE_SUMMARY_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%MUTC')}.json"
    report.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(report))
    print(json.dumps(out["summary"], ensure_ascii=False))
    return out


def main() -> int:
    result = run_summary()
    return 0 if result["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
