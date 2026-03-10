#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio

from rich.console import Console
from rich.progress import track
from rich.table import Table

from vito_tester import VITOLogReader, VITOTesterClient
from vito_tester.reporting import write_report
from vito_tester.scenarios import filter_scenarios


async def main(priority: str | None = None, category: str | None = None) -> int:
    console = Console()
    scenarios = filter_scenarios(priority=priority, category=category)
    client = VITOTesterClient()
    log_reader = VITOLogReader()
    await client.start()
    log_reader.connect()
    results = []
    table = Table(title="VITO Telegram Test Results")
    table.add_column("ID")
    table.add_column("Категория")
    table.add_column("Тест")
    table.add_column("Статус")
    table.add_column("Время")
    passed = failed = 0
    for scenario in track(scenarios, description="Тестирование..."):
        await asyncio.sleep(2)
        before = log_reader.get_error_count()
        result = await client.run_test(
            test_id=scenario.test_id,
            command=scenario.command,
            expected_keyword=scenario.expected_keyword,
            timeout=scenario.timeout_s,
            inverted=scenario.inverted,
        )
        after = log_reader.get_error_count()
        if after > before:
            result.log_snippet = log_reader.grep_log("ERROR", lines=5)
        results.append((scenario, result))
        if result.success:
            passed += 1
            status = "[green]PASS[/green]"
        else:
            failed += 1
            status = "[red]FAIL[/red]"
        snippet = (result.response[:80] + "...") if len(result.response) > 80 else result.response
        table.add_row(scenario.test_id, scenario.category, scenario.name, status, f"{result.response_time}s")
        if not result.success:
            console.print(f"[red]{scenario.test_id}: {result.error}[/red]")
            if result.log_snippet:
                console.print(f"[dim]{result.log_snippet[:300]}[/dim]")
    report_path = write_report(results=results)
    console.print(table)
    console.print(f"Итого: {passed} PASS / {failed} FAIL / {len(scenarios)} TOTAL")
    console.print(f"Отчет: {report_path}")
    await client.stop()
    log_reader.close()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("priority", nargs="?", default=None)
    parser.add_argument("category", nargs="?", default=None)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.priority, args.category)))
