"""Browser recovery and selectorless preflight decisions."""

from __future__ import annotations

from typing import Any


def looks_like_selector(key: str) -> bool:
    text = str(key or "").strip()
    return any(ch in text for ch in "#.[>:=@") or text.startswith(("input", "textarea", "select", "//"))


def build_form_fill_preflight(data: dict[str, Any]) -> dict[str, Any]:
    fields = dict(data or {})
    selector_keys = [k for k in fields if looks_like_selector(k)]
    generic_keys = [k for k in fields if k not in selector_keys]
    return {
        "selector_keys": selector_keys,
        "generic_keys": generic_keys,
        "selector_mapping_required": bool(generic_keys and not selector_keys),
        "next_actions": ["map_generic_fields_to_selectors", "capture_page_form_schema"] if generic_keys and not selector_keys else [],
    }


def build_browser_recovery(service: str, mode: str, reason: str) -> dict[str, Any]:
    return {
        "service": str(service or "").strip().lower(),
        "mode": str(mode or "").strip().lower(),
        "reason": str(reason or "").strip(),
        "retry_strategy": "screenshot_first_retry",
        "escalation_path": ["account_manager", "quality_judge"],
        "block_conditions": ["challenge_detected", "auth_interrupt", "profile_completion_required"],
    }
