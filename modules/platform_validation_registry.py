"""Persistent registry of latest platform validation outcomes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.paths import PROJECT_ROOT

_REGISTRY = PROJECT_ROOT / 'runtime' / 'platform_validation_registry.json'


def load_platform_validation_registry() -> dict[str, dict[str, Any]]:
    try:
        if not _REGISTRY.exists():
            return {}
        data = json.loads(_REGISTRY.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            return {}
        return {str(k).strip().lower(): dict(v or {}) for k, v in data.items() if str(k).strip()}
    except Exception:
        return {}


def save_platform_validation_registry(data: dict[str, dict[str, Any]]) -> None:
    _REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    _REGISTRY.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def update_platform_validation(service: str, **fields: Any) -> None:
    svc = str(service or '').strip().lower()
    if not svc:
        return
    data = load_platform_validation_registry()
    row = dict(data.get(svc) or {})
    row.update({k: v for k, v in fields.items()})
    row['updated_at'] = datetime.now(timezone.utc).isoformat()
    data[svc] = row
    save_platform_validation_registry(data)


def record_platform_validation_result(item: dict[str, Any]) -> None:
    if not isinstance(item, dict):
        return
    service = str(item.get('platform') or item.get('service') or '').strip().lower()
    if not service:
        return
    update_platform_validation(
        service,
        state=str(item.get('state') or item.get('owner_grade_state') or 'unknown'),
        owner_grade_ok=bool(item.get('owner_grade_ok')),
        blocker=str(item.get('blocker') or ''),
        mode=str(item.get('mode') or ''),
        url=str(item.get('url') or ''),
        source=str(item.get('source') or ''),
        signals=item.get('signals') or {},
    )
