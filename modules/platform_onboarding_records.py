from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.paths import root_path


class PlatformOnboardingRecords:
    def __init__(self, base_dir: str | Path | None = None):
        self.base_dir = Path(base_dir) if base_dir else Path(root_path("runtime", "platform_onboarding"))
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def write_report(self, platform_id: str, payload: dict[str, Any]) -> str:
        path = self.base_dir / f"{self._safe_id(platform_id)}_report.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)

    def write_result(self, platform_id: str, payload: dict[str, Any]) -> str:
        path = self.base_dir / f"{self._safe_id(platform_id)}_result.json"
        wrapped = {"saved_at": datetime.now(timezone.utc).isoformat(), **payload}
        path.write_text(json.dumps(wrapped, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)

    @staticmethod
    def _safe_id(platform_id: str) -> str:
        raw = str(platform_id or "").strip().lower() or "unknown_platform"
        return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in raw)
