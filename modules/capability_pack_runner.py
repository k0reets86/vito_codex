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
            return {"status": "error", "error": "adapter_not_found"}
        spec = importlib.util.spec_from_file_location(f"cap_pack_{name}", adapter)
        if not spec or not spec.loader:
            return {"status": "error", "error": "load_failed"}
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if not hasattr(module, "run"):
            return {"status": "error", "error": "run_not_defined"}
        return module.run(input_data or {})
