from __future__ import annotations

from typing import Any

from modules.owner_requirements_runtime import get_owner_requirements_runtime


def build_owner_policy_pack(*, refresh: bool = False) -> dict[str, Any]:
    runtime = get_owner_requirements_runtime(refresh=refresh)
    rules = list(runtime.get('rules') or [])
    enabled = [r for r in rules if isinstance(r, dict) and bool(r.get('enabled'))]
    return {
        'schema_version': int(runtime.get('schema_version') or 0),
        'active_rule_count': int(runtime.get('active_rule_count') or 0),
        'flags': dict(runtime.get('flags') or {}),
        'reminders': list(runtime.get('reminders') or [])[:12],
        'enabled_rules': enabled[:12],
        'source_meta': dict(runtime.get('source_meta') or {}),
    }
