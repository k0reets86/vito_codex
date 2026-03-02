from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class CancelState:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path or "/home/vito/vito-agent/runtime/cancel_state.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"cancelled": False})

    def _read(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"cancelled": False}

    def _write(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def is_cancelled(self) -> bool:
        return bool(self._read().get("cancelled"))

    def cancel(self, reason: str | None = None) -> None:
        data = {"cancelled": True, "reason": reason or "owner_cancelled"}
        self._write(data)

    def clear(self) -> None:
        self._write({"cancelled": False})
