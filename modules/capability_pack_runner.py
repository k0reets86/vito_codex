"""Runtime loader for capability packs."""
from __future__ import annotations

import importlib.util
import json
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
        spec_data: dict[str, Any] = {}
        if spec_path.exists():
            try:
                spec_data = json.loads(spec_path.read_text(encoding="utf-8"))
            except Exception:
                spec_data = {}
        if spec_data and not settings.CAPABILITY_PACK_ALLOW_PENDING:
            try:
                if str(spec_data.get("acceptance_status", "pending")).lower() != "accepted":
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
        result = self._normalize_result(name, spec_data, result)
        _record_pack_event(name, result)
        return result

    @staticmethod
    def _normalize_result(name: str, spec_data: dict[str, Any], result: dict[str, Any] | Any) -> dict[str, Any]:
        if not isinstance(result, dict):
            return {
                "status": "error",
                "error": "invalid_capability_result",
                "output": {
                    "capability": name,
                    "verification_ok": False,
                    "details": {"raw_type": type(result).__name__},
                },
            }
        output = result.get("output")
        if not isinstance(output, dict):
            output = {"value": output}
        output.setdefault("capability", str(spec_data.get("name") or name))
        output.setdefault("category", str(spec_data.get("category") or ""))
        output.setdefault("description", str(spec_data.get("description") or ""))
        output.setdefault("required_inputs", list(spec_data.get("inputs") or []))
        output.setdefault("declared_outputs", list(spec_data.get("outputs") or []))
        output.setdefault("verification_ok", str(result.get("status") or "").strip().lower() == "ok")
        output.setdefault("evidence", {})
        output.setdefault("next_actions", [])
        output.setdefault("recovery_hints", [])
        if spec_data:
            output.setdefault(
                "runtime_profile",
                {
                    "acceptance_status": str(spec_data.get("acceptance_status") or "pending"),
                    "risk_score": float(spec_data.get("risk_score") or 0),
                    "tests_coverage": float(spec_data.get("tests_coverage") or 0),
                    "version": str(spec_data.get("version") or ""),
                },
            )
        result["output"] = output
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
