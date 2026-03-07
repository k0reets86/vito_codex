from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from config.paths import root_path
from modules.task_lineage import derive_artifact_map, generate_task_root_id


class OwnerTaskState:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path or root_path("runtime", "owner_task_state.json"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"active": None, "history": []})

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("active", None)
                data.setdefault("history", [])
                return data
        except Exception:
            pass
        return {"active": None, "history": []}

    def _write(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def get_active(self) -> dict[str, Any] | None:
        return self._read().get("active")

    def set_active(
        self,
        text: str,
        source: str = "owner",
        intent: str = "goal_request",
        force: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        payload = self._read()
        if payload.get("active") and not force:
            return False
        active = {
            "text": str(text or "").strip()[:2000],
            "source": str(source or "owner")[:80],
            "intent": str(intent or "")[:80],
            "status": "active",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if isinstance(metadata, dict):
            for key, value in metadata.items():
                if value in (None, ""):
                    continue
                active[str(key)[:80]] = value if isinstance(value, (int, float, bool)) else str(value)[:500]
        task_root_id = str(active.get("task_root_id") or "").strip() or generate_task_root_id(text)
        active["task_root_id"] = task_root_id
        artifact_ids = derive_artifact_map(task_root_id)
        active.setdefault("project_id", artifact_ids.get("project_id", ""))
        active.setdefault("listing_work_id", artifact_ids.get("listing_id", ""))
        active.setdefault("content_work_id", artifact_ids.get("content_id", ""))
        active.setdefault("seo_work_id", artifact_ids.get("seo_id", ""))
        active.setdefault("publish_work_id", artifact_ids.get("publish_id", ""))
        payload["active"] = active
        self._write(payload)
        return True

    def enrich_active(self, **metadata: Any) -> bool:
        payload = self._read()
        active = payload.get("active")
        if not isinstance(active, dict):
            return False
        changed = False
        for key, value in metadata.items():
            if value in (None, ""):
                continue
            norm_key = str(key or "").strip()[:80]
            norm_val = value if isinstance(value, (int, float, bool)) else str(value)[:500]
            if active.get(norm_key) == norm_val:
                continue
            active[norm_key] = norm_val
            changed = True
        if not changed:
            return False
        active["updated_at"] = datetime.now(timezone.utc).isoformat()
        payload["active"] = active
        self._write(payload)
        return True

    def complete(self, note: str = "") -> None:
        payload = self._read()
        active = payload.get("active")
        if active:
            active["status"] = "completed"
            active["closed_at"] = datetime.now(timezone.utc).isoformat()
            if note:
                active["note"] = str(note)[:500]
            history = payload.get("history", [])
            history.append(active)
            payload["history"] = history[-100:]
        payload["active"] = None
        self._write(payload)

    def cancel(self, note: str = "") -> None:
        payload = self._read()
        active = payload.get("active")
        if active:
            active["status"] = "cancelled"
            active["closed_at"] = datetime.now(timezone.utc).isoformat()
            if note:
                active["note"] = str(note)[:500]
            history = payload.get("history", [])
            history.append(active)
            payload["history"] = history[-100:]
        payload["active"] = None
        self._write(payload)
