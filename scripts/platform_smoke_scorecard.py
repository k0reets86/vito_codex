#!/usr/bin/env python3
"""Generate platform smoke scorecard from runtime evidence."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.platform_scorecard import PlatformScorecard


PLATFORMS = ["gumroad", "etsy", "wordpress", "twitter", "kofi", "printful"]


def main() -> int:
    sc = PlatformScorecard()
    rows = sc.score(PLATFORMS, days=30)
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_days": 30,
        "platforms": rows,
    }
    report_dir = Path("/home/vito/vito-agent/reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    p = report_dir / "PLATFORM_SMOKE_SCORECARD_2026-02-25.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(p))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
