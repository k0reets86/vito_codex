from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .client import TestResult
from .scenarios import TestScenario


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SUTC")


def write_report(
    *,
    results: Iterable[tuple[TestScenario, TestResult]],
    report_prefix: str = "VITO_TG_TEST_REPORT",
    output_dir: str | Path = "reports",
) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    rows = []
    passed = failed = 0
    for scenario, result in results:
        row = {
            "scenario": asdict(scenario),
            "result": asdict(result),
        }
        rows.append(row)
        if result.success:
            passed += 1
        else:
            failed += 1
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "failed": failed,
        "total": passed + failed,
        "results": rows,
    }
    path = output_path / f"{report_prefix}_{utc_stamp()}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
