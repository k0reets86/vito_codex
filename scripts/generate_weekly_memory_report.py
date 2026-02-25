#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime, timezone

from modules.memory_skill_reports import MemorySkillReporter


def main() -> None:
    reporter = MemorySkillReporter()
    report_path = Path("reports/memory_retention_weekly.md")
    reporter.persist_markdown(
        path=report_path,
        days=7,
        per_skill_limit=8,
    )
    print(f"[{datetime.now(timezone.utc).isoformat()}] Weekly memory report appended to {report_path}")


if __name__ == "__main__":
    main()
