#!/usr/bin/env python3
"""Generate final scorecard report for VITO."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.final_scorecard import FinalScorecard
from modules.playbook_registry import PlaybookRegistry


def main() -> int:
    try:
        PlaybookRegistry().ensure_bootstrap(limit=5000)
    except Exception:
        pass
    data = FinalScorecard().calculate()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%MUTC")
    reports = ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    jp = reports / f"VITO_FINAL_SCORECARD_{ts}.json"
    mp = reports / f"VITO_FINAL_SCORECARD_{ts}.md"
    jp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# VITO Final Scorecard ({ts})",
        f"- Average: **{data['avg']}/10**",
        "",
        "## Blocks",
    ]
    for b in data["blocks"]:
        lines.append(f"- {b['name']}: **{b['score']}/10** ({b['note']})")
    lines += ["", "## Metrics"]
    for k, v in data["metrics"].items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Platform Readiness"]
    for p in data["platform_scorecard"]:
        lines.append(
            f"- {p['platform']}: score={p['readiness_score']} "
            f"(ok={p['success_count_30d']}, evidence={p['evidence_count_30d']}, fail={p['fail_count_30d']})"
        )
    mp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(str(mp))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
