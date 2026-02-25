#!/usr/bin/env python3
"""Generate skill acceptance status report."""
from __future__ import annotations

from datetime import datetime, timezone

from modules.skill_registry import SkillRegistry


def main() -> int:
    reg = SkillRegistry()
    rows = reg.list_skills(limit=500)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = f"/home/vito/vito-agent/reports/SKILL_ACCEPTANCE_{today}.md"
    lines = [f"# Skill Acceptance Report ({today})", ""]
    lines.append("| Name | Status | Acceptance | Risk | Tests | Updated |")
    lines.append("|---|---|---|---|---|---|")
    for r in rows:
        lines.append(
            f"| {r.get('name')} | {r.get('status')} | {r.get('acceptance_status')} | {float(r.get('risk_score',0)):.2f} | {float(r.get('tests_coverage',0)):.2f} | {r.get('updated_at','')} |"
        )
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
