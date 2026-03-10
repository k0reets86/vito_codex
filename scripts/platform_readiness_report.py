#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.platform_readiness import assess_platform_readiness

REPORTS = ROOT / "reports"


def main() -> int:
    checks = assess_platform_readiness()
    out = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "summary": {
            "total": len(checks),
            "can_validate_now": sum(1 for c in checks if c["can_validate_now"]),
            "blocked": sum(1 for c in checks if c["blocker"]),
            "owner_grade": sum(1 for c in checks if c["owner_grade_state"] == "owner_grade"),
        },
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"VITO_PLATFORM_READINESS_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%MUTC')}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)
    print(json.dumps(out["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
