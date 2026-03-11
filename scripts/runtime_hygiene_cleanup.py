from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.runtime_hygiene import (
    cleanup_project_artifacts,
    cleanup_reports_artifacts,
    cleanup_runtime_db_artifacts,
    cleanup_simulator_artifacts,
    runtime_hygiene_summary,
)


def main() -> None:
    before = runtime_hygiene_summary()
    project = cleanup_project_artifacts(apply=True)
    reports = cleanup_reports_artifacts(keep_latest=120, apply=True)
    runtime_dbs = cleanup_runtime_db_artifacts(apply=True)
    result = cleanup_simulator_artifacts(keep_latest=20, apply=True)
    after = runtime_hygiene_summary()
    print(
        json.dumps(
            {
                "before": before,
                "project_removed_dirs": project.removed_dirs,
                "project_removed_files": project.removed_files,
                "report_removed_files": reports.removed_files,
                "report_kept_files": reports.kept_files,
                "runtime_db_removed_files": runtime_dbs.removed_files,
                "runtime_db_kept_files": runtime_dbs.kept_files,
                "removed_dirs": result.removed_dirs,
                "kept_dirs": result.kept_dirs,
                "after": after,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
