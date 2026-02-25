"""Runtime loader for capability packs."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from config.settings import settings


class CapabilityPackRunner:
    def __init__(self, root: str | None = None):
        base = Path(root) if root else Path(__file__).resolve().parent.parent / "capability_packs"
        self.root = base

    def run(self, name: str, input_data: dict[str, Any] | None = None) -> dict[str, Any]:
        pack_dir = self.root / name
        spec_path = pack_dir / "spec.json"
        adapter = pack_dir / "adapter.py"
        if not adapter.exists():
            result = {"status": "error", "error": "adapter_not_found"}
            _record_pack_event(name, result)
            return result
        if spec_path.exists() and not settings.CAPABILITY_PACK_ALLOW_PENDING:
            try:
                import json
                spec = json.loads(spec_path.read_text(encoding="utf-8"))
                if str(spec.get("acceptance_status", "pending")).lower() != "accepted":
                    result = {"status": "error", "error": "pack_not_accepted"}
                    _record_pack_event(name, result)
                    return result
            except Exception:
                pass
        spec = importlib.util.spec_from_file_location(f"cap_pack_{name}", adapter)
        if not spec or not spec.loader:
            result = {"status": "error", "error": "load_failed"}
            _record_pack_event(name, result)
            return result
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if not hasattr(module, "run"):
            result = {"status": "error", "error": "run_not_defined"}
            _record_pack_event(name, result)
            return result
        result = module.run(input_data or {})
        _record_pack_event(name, result)
        return result


def _record_pack_event(name: str, result: dict[str, Any]) -> None:
    try:
        from modules.data_lake import DataLake
        status = "success" if result.get("status") == "ok" else "failed"
        DataLake().record(
            agent="capability_pack",
            task_type=f"cap_pack:{name}",
            status=status,
            output=result,
            source="capability_pack",
        )
    except Exception:
        pass
