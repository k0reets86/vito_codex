#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from vito_tester import STRESS_SCENARIOS, VITOLogReader, VITOTesterClient


async def main() -> int:
    client = VITOTesterClient()
    log_reader = VITOLogReader()
    await client.start()
    log_reader.connect()
    baseline_errors = log_reader.get_error_count()
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenarios": [],
    }
    for scenario in STRESS_SCENARIOS:
        for command in scenario.commands:
            await client.send(command)
            if scenario.interval_s > 0:
                await asyncio.sleep(scenario.interval_s)
        response = await client.wait_response(timeout=scenario.timeout_s, collect_all=True)
        errors_now = log_reader.get_error_count()
        payload["scenarios"].append(
            {
                "scenario_id": scenario.scenario_id,
                "commands": list(scenario.commands),
                "response": response[:1000],
                "new_errors": max(0, errors_now - baseline_errors) if errors_now >= 0 and baseline_errors >= 0 else -1,
            }
        )
        baseline_errors = errors_now if errors_now >= 0 else baseline_errors
        await asyncio.sleep(3)
    await client.send("/status")
    final_status = await client.wait_response(timeout=15)
    payload["final_status"] = final_status[:1000]
    payload["alive"] = "vito" in final_status.lower() or "status" in final_status.lower()
    reports_dir = Path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"VITO_TG_STRESS_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%SUTC')}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)
    await client.stop()
    log_reader.close()
    return 0 if payload["alive"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
