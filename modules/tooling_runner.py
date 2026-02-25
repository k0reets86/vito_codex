"""Safe runtime execution for tooling adapters from ToolingRegistry."""

from __future__ import annotations

from typing import Any

from config.settings import settings
from modules.operator_policy import OperatorPolicy
from modules.tooling_registry import ToolingRegistry


class ToolingRunner:
    def __init__(self, sqlite_path: str | None = None):
        self.registry = ToolingRegistry(sqlite_path=sqlite_path)
        self.policy = OperatorPolicy(sqlite_path=sqlite_path)

    def run(self, adapter_key: str, input_data: dict[str, Any] | None = None, dry_run: bool = True) -> dict[str, Any]:
        input_data = input_data or {}
        rows = self.registry.list_adapters(enabled_only=False, limit=500)
        adapter = next((r for r in rows if r.get("adapter_key") == adapter_key), None)
        if not adapter:
            result = {"status": "error", "error": "adapter_not_found", "adapter_key": adapter_key}
            self._record_event(adapter_key, result)
            return result
        if int(adapter.get("enabled", 0) or 0) != 1:
            result = {"status": "error", "error": "adapter_disabled", "adapter_key": adapter_key}
            self._record_event(adapter_key, result)
            return result

        policy_key = f"tooling:{adapter_key}"
        allowed, reason = self.policy.is_tool_allowed(policy_key)
        if not allowed:
            result = {"status": "error", "error": "policy_blocked", "reason": reason, "adapter_key": adapter_key}
            self._record_event(adapter_key, result)
            return result

        live_allowed = bool(getattr(settings, "TOOLING_RUN_LIVE_ENABLED", False))
        if dry_run or not live_allowed:
            result = {
                "status": "dry_run",
                "adapter_key": adapter_key,
                "protocol": adapter.get("protocol"),
                "endpoint": adapter.get("endpoint"),
                "auth_type": adapter.get("auth_type"),
                "input_preview": {k: str(v)[:120] for k, v in list(input_data.items())[:20]},
                "reason": "dry_run" if dry_run else "live_disabled",
            }
            self._record_event(adapter_key, result)
            return result

        # Live mode is intentionally conservative: return execution plan without invoking external processes.
        result = {
            "status": "prepared",
            "adapter_key": adapter_key,
            "protocol": adapter.get("protocol"),
            "endpoint": adapter.get("endpoint"),
            "notes": "live execution plan prepared; external invocation disabled in this runner",
        }
        self._record_event(adapter_key, result)
        return result

    @staticmethod
    def _record_event(adapter_key: str, result: dict[str, Any]) -> None:
        try:
            from modules.data_lake import DataLake
            status = "success" if result.get("status") in {"dry_run", "prepared", "ok"} else "failed"
            DataLake().record(
                agent="tooling_runner",
                task_type=f"tooling:{adapter_key}",
                status=status,
                output=result,
                error=str(result.get("error", ""))[:300],
                source="tooling_runner",
            )
        except Exception:
            pass
