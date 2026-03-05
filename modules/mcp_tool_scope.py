"""Minimal MCP tool scoping per task family."""

from __future__ import annotations

from typing import Any


TASK_FAMILY_TOOL_SCOPE: dict[str, set[str]] = {
    "research": {"search", "fetch_url", "summarize"},
    "publish": {"create_post", "create_listing", "upload_media", "update_listing"},
    "auth": {"login_status", "capture_session"},
    "analytics": {"fetch_metrics", "list_items"},
    "default": {"search", "fetch_url"},
}


def _normalize_tool_name(name: str) -> str:
    return str(name or "").strip().lower().replace("-", "_")


def _family_for_task(task_type: str) -> str:
    t = str(task_type or "").strip().lower()
    if any(k in t for k in ("research", "trend", "market")):
        return "research"
    if any(k in t for k in ("publish", "listing", "post", "social")):
        return "publish"
    if any(k in t for k in ("auth", "login", "session")):
        return "auth"
    if any(k in t for k in ("analytic", "metric", "report")):
        return "analytics"
    return "default"


def enforce_mcp_tool_scope(task_type: str, adapter_schema: dict[str, Any], input_data: dict[str, Any]) -> tuple[bool, str]:
    schema = dict(adapter_schema or {})
    tools_raw = schema.get("tools") or []
    available = {_normalize_tool_name(t.get("name") if isinstance(t, dict) else t) for t in tools_raw}
    available = {t for t in available if t}
    if not available:
        return True, "scope_skip_no_tools"

    requested = input_data.get("requested_tools")
    req_set = {_normalize_tool_name(x) for x in (requested or []) if _normalize_tool_name(x)}
    family = _family_for_task(str(input_data.get("task_type") or task_type))
    allowed = set(TASK_FAMILY_TOOL_SCOPE.get(family, TASK_FAMILY_TOOL_SCOPE["default"]))

    # requested tools are optional; when absent, adapter itself should use minimal subset.
    if not req_set:
        return True, f"scope_ok_family={family}_implicit"

    unknown = sorted([x for x in req_set if x not in available])
    if unknown:
        return False, f"requested_tools_not_in_schema:{','.join(unknown)}"
    denied = sorted([x for x in req_set if x not in allowed])
    if denied:
        return False, f"requested_tools_out_of_scope:{','.join(denied)}"
    return True, f"scope_ok_family={family}"

