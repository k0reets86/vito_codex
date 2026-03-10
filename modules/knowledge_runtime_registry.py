from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.paths import PROJECT_ROOT

_REGISTRY = PROJECT_ROOT / 'runtime' / 'knowledge_runtime_registry.json'


def load_knowledge_runtime_registry() -> dict[str, Any]:
    try:
        if not _REGISTRY.exists():
            return {'entries': {}, 'updated_at': ''}
        data = json.loads(_REGISTRY.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            data.setdefault('entries', {})
            data.setdefault('updated_at', '')
            return data
    except Exception:
        pass
    return {'entries': {}, 'updated_at': ''}


def save_knowledge_runtime_registry(data: dict[str, Any]) -> None:
    _REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(data or {})
    payload['updated_at'] = datetime.now(timezone.utc).isoformat()
    _REGISTRY.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def _key(query: str, services: list[str] | None = None, task_root_id: str = '') -> str:
    svc = ','.join(sorted({str(x).strip().lower() for x in (services or []) if str(x).strip()}))
    return f"{task_root_id.strip()}|{svc}|{str(query or '').strip().lower()[:180]}"


def record_knowledge_runtime_pack(*, query: str, services: list[str] | None = None, task_root_id: str = '', pack: dict[str, Any]) -> str:
    reg = load_knowledge_runtime_registry()
    entries = reg.setdefault('entries', {})
    key = _key(query, services, task_root_id)
    entries[key] = {
        'query': str(query or ''),
        'services': [str(x).strip().lower() for x in (services or []) if str(x).strip()],
        'task_root_id': str(task_root_id or ''),
        'pack': dict(pack or {}),
        'recorded_at': datetime.now(timezone.utc).isoformat(),
    }
    save_knowledge_runtime_registry(reg)
    return key
