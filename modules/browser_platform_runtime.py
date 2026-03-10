from __future__ import annotations

from pathlib import Path
from typing import Any

from agents.base_agent import TaskResult
from config.paths import PROJECT_ROOT
from modules.execution_facts import ExecutionFacts


def resolve_storage_state(path_value: str | None, default_rel: str) -> Path:
    raw = str(path_value or default_rel).strip() or default_rel
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


async def browser_auth_probe(
    *,
    browser_agent,
    service: str,
    url: str,
    storage_state_path: Path | None = None,
) -> bool:
    if not browser_agent:
        return False
    result = await browser_agent.execute_task(task_type="browse", url=url, service=service)
    return bool(result and result.success)


async def browser_publish_form(
    *,
    browser_agent,
    service: str,
    url: str,
    form_data: dict[str, Any],
    success_status: str = "prepared",
    title_field: str = "title",
    link_field: str = "url",
) -> dict[str, Any]:
    if not browser_agent:
        return {"platform": service, "status": "no_browser"}
    result: TaskResult = await browser_agent.execute_task(
        task_type="form_fill",
        url=url,
        data=form_data,
        service=service,
    )
    success = bool(result and result.success)
    output = result.output if result else {}
    if not isinstance(output, dict):
        output = {"raw_output": output}
    screenshot_path = output.get("screenshot_path", "")
    current_url = output.get("url", url)
    title = str(form_data.get(title_field, "")).strip()
    if success:
        ExecutionFacts().record(
            action="platform:publish",
            status=success_status,
            detail=f"{service} browser publish title={title[:120]}",
            evidence=current_url or screenshot_path,
            source=f"{service}.publish",
            evidence_dict={
                "platform": service,
                "status": success_status,
                "url": current_url,
                "screenshot_path": screenshot_path,
                "title": title,
            },
        )
    return {
        "platform": service,
        "status": success_status if success else "failed",
        link_field: current_url,
        "title": title,
        "screenshot_path": screenshot_path,
        "output": output,
        "recovery_hints": [] if success else [f"verify_{service}_selectors", f"rerun_{service}_browser_flow"],
    }


async def browser_extract_analytics(*, browser_agent, service: str, url: str) -> dict[str, Any]:
    if not browser_agent:
        return {"platform": service, "status": "no_browser", "raw_data": None}
    result = await browser_agent.execute_task(task_type="extract_text", url=url, selector="body", service=service)
    return {
        "platform": service,
        "status": "ok" if result and result.success else "failed",
        "raw_data": result.output if result else None,
    }
