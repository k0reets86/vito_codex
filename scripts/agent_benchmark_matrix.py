#!/usr/bin/env python3
"""Generate Phase M benchmark matrix for all 23 agents."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.agent_benchmark_matrix import build_benchmark_matrix
from scripts.mega_agent_audit import run_megatest


async def run_benchmark_matrix() -> dict:
    megatest = await run_megatest()
    matrix = build_benchmark_matrix(megatest)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "megatest": {
            "total_agents": megatest.get("total_agents", 0),
            "combat_ready_agents": megatest.get("combat_ready_agents", 0),
            "combat_readiness_percent": megatest.get("combat_readiness_percent", 0.0),
        },
        **matrix,
    }


def main() -> int:
    import asyncio

    report = asyncio.run(run_benchmark_matrix())
    reports_dir = ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%MUTC")
    path = reports_dir / f"VITO_AGENT_BENCHMARK_MATRIX_{ts}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
