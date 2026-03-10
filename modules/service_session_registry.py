"""Persistent browser session registry per platform/service."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.paths import PROJECT_ROOT


_REGISTRY_PATH = PROJECT_ROOT / "runtime" / "service_sessions.json"


def load_service_sessions() -> dict[str, dict[str, Any]]:
    try:
        if not _REGISTRY_PATH.exists():
            return {}
        payload = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {}
        return {str(k).strip().lower(): dict(v or {}) for k, v in payload.items() if str(k).strip()}
    except Exception:
        return {}


def save_service_sessions(data: dict[str, dict[str, Any]]) -> None:
    try:
        _REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        _REGISTRY_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def update_service_session(service: str, **fields: Any) -> None:
    svc = str(service or "").strip().lower()
    if not svc:
        return
    data = load_service_sessions()
    row = dict(data.get(svc) or {})
    row.update({k: v for k, v in fields.items() if v not in (None, "")})
    row["updated_at"] = datetime.now(timezone.utc).isoformat()
    data[svc] = row
    save_service_sessions(data)


def clear_service_session(service: str) -> None:
    svc = str(service or "").strip().lower()
    if not svc:
        return
    data = load_service_sessions()
    if svc in data:
        data.pop(svc, None)
        save_service_sessions(data)


def capture_session_snapshot(service: str, *, storage_state_path: str = "", profile_dir: str = "", verified: bool = False) -> None:
    payload: dict[str, Any] = {}
    now = datetime.now(timezone.utc).isoformat()
    if verified:
        payload["verified_at"] = now
    if storage_state_path:
        path = Path(storage_state_path)
        payload["storage_state_path"] = str(path)
        payload["storage_exists"] = path.exists()
        if path.exists():
            try:
                payload["storage_mtime"] = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
            except Exception:
                pass
    if profile_dir:
        payload["profile_dir"] = profile_dir
    update_service_session(service, **payload)
