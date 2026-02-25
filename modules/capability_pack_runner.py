"""Runtime loader for capability packs."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


class CapabilityPackRunner:
    def __init__(self, root: str | None = None):
        base = Path(root) if root else Path(__file__).resolve().parent.parent / "capability_packs"
        self.root = base

    def run(self, name: str, input_data: dict[str, Any] | None = None) -> dict[str, Any]:
        pack_dir = self.root / name
        adapter = pack_dir / "adapter.py"
        if not adapter.exists():
            result = {"status": "error", "error": "adapter_not_found"}
            _record_pack_event(name, result)
            return result
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
